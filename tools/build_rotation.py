#!/usr/bin/env python3
"""
Construit un ordre de lecture par creneau (morning/afternoon/evening/night) a
partir de metadata.json (sortie de analyze_essentia.py), pour casser la
redondance de style facon FIP/Radio Meuh :
- alterne les genres et les artistes (pas de repetition dans une fenetre glissante)
- suit une courbe d'energie cible propre a chaque creneau

Ne deplace/modifie aucun fichier audio. Produit par creneau :
- playlists/<slot>.m3u  (ordre de lecture, chemins absolus)
- playlists/<slot>.csv  (position, energie, genre, artiste, titre - pour relecture)

Usage : python build_rotation.py
"""
import os
import csv
import json
import random
from collections import deque

from mutagen import File as MFile

BASE = os.path.dirname(os.path.abspath(__file__))
METADATA_PATH = os.path.join(BASE, "metadata.json")
OUT_DIR = os.path.join(BASE, "playlists")

SLOTS = {
    "1_morning": r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog\1_morning",
    "2_afternoon": r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog\2_afternoon",
    "3_evening": r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog\3_evening",
    "4_night": r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog\4_night",
}

# Courbe d'energie cible par creneau : (debut, fin) sur une echelle 0-1.
# A ajuster librement selon l'ambiance voulue (ex. night = peak party -> (0.3, 0.9)).
ENERGY_CURVES = {
    "1_morning": (0.20, 0.60),    # reveil en douceur, monte progressivement
    "2_afternoon": (0.45, 0.75),  # plateau modere-haut
    "3_evening": (0.55, 0.90),    # montee vers un pic
    "4_night": (0.65, 0.25),      # descente chill en fin de soiree
}

GENRE_WINDOW = 4    # pas 2 fois le meme genre top-level dans les 4 derniers morceaux
ARTIST_WINDOW = 8   # pas 2 fois le meme artiste dans les 8 derniers morceaux
ENERGY_TOLERANCE = 0.15  # tolerance initiale autour de la cible, elargie si pool vide


def top_genre(genres):
    if not genres:
        return "Unknown"
    # Discogs renvoie "Categorie---Sous-genre" ; sur une bibliotheque electronique
    # la categorie est quasi toujours "Electronic", on prend donc le sous-genre
    # (plus discriminant) quand il existe.
    parts = genres[0][0].split("---")
    return (parts[1] if len(parts) > 1 else parts[0]).strip()


def read_artist_title(path):
    try:
        audio = MFile(path, easy=True)
        artist = (audio.tags.get("artist") or ["?"])[0] if audio and audio.tags else "?"
        title = (audio.tags.get("title") or [os.path.splitext(os.path.basename(path))[0]])[0] if audio and audio.tags else os.path.splitext(os.path.basename(path))[0]
        return artist, title
    except Exception:
        return "?", os.path.splitext(os.path.basename(path))[0]


def normalize(values):
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def load_tracks():
    with open(METADATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    rms_vals = [d["rms"] for d in data]
    bpm_vals = [d["bpm"] for d in data]
    norm_rms = normalize(rms_vals)
    norm_bpm = normalize(bpm_vals)

    tracks = []
    for d, nr, nb in zip(data, norm_rms, norm_bpm):
        energy = 0.5 * nr + 0.3 * nb + 0.2 * d["mood"]["party"]
        artist, title = read_artist_title(d["path"])
        # Normalise le chemin (WSL a pu ecrire des slashes /)
        win_path = d["path"].replace("/mnt/c", "C:").replace("/", "\\")
        tracks.append({
            "path": win_path,
            "genre": top_genre(d["genres"]),
            "artist": artist,
            "title": title,
            "energy": energy,
            "bpm": d["bpm"],
        })
    return tracks


def build_order(slot_tracks, curve):
    start, end = curve
    n = len(slot_tracks)
    pool = list(slot_tracks)
    ordered = []
    recent_genres = deque(maxlen=GENRE_WINDOW)
    recent_artists = deque(maxlen=ARTIST_WINDOW)

    for i in range(n):
        target = start + (end - start) * (i / max(n - 1, 1))
        tolerance = ENERGY_TOLERANCE
        candidates = []
        while not candidates and tolerance < 1.5:
            candidates = [
                t for t in pool
                if abs(t["energy"] - target) <= tolerance
                and t["genre"] not in recent_genres
                and (t["artist"] == "?" or t["artist"] not in recent_artists)
            ]
            if not candidates:
                # relache d'abord la contrainte artiste, puis genre, puis energie
                candidates = [t for t in pool if abs(t["energy"] - target) <= tolerance and t["genre"] not in recent_genres]
            if not candidates:
                candidates = [t for t in pool if abs(t["energy"] - target) <= tolerance]
            tolerance += 0.1

        if not candidates:
            candidates = pool

        candidates.sort(key=lambda t: abs(t["energy"] - target))
        pick = random.choice(candidates[:max(1, len(candidates) // 3)])
        pool.remove(pick)
        ordered.append(pick)
        recent_genres.append(pick["genre"])
        if pick["artist"] != "?":
            recent_artists.append(pick["artist"])

    return ordered


def write_outputs(slot_name, ordered):
    os.makedirs(OUT_DIR, exist_ok=True)
    m3u_path = os.path.join(OUT_DIR, f"{slot_name}.m3u")
    csv_path = os.path.join(OUT_DIR, f"{slot_name}.csv")

    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for t in ordered:
            f.write(f"#EXTINF:-1,{t['artist']} - {t['title']}\n")
            f.write(t["path"] + "\n")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["position", "energie", "bpm", "genre", "artiste", "titre", "chemin"])
        for i, t in enumerate(ordered, 1):
            w.writerow([i, f"{t['energy']:.3f}", f"{t['bpm']:.0f}", t["genre"], t["artist"], t["title"], t["path"]])

    print(f"{slot_name} : {len(ordered)} morceaux -> {m3u_path} / {csv_path}")


def main():
    tracks = load_tracks()
    print(f"{len(tracks)} morceaux charges depuis {METADATA_PATH}")

    for slot_name, folder in SLOTS.items():
        folder_norm = os.path.normcase(folder)
        slot_tracks = [t for t in tracks if os.path.normcase(t["path"]).startswith(folder_norm)]
        if not slot_tracks:
            print(f"{slot_name} : aucun morceau trouve, ignore.")
            continue
        ordered = build_order(slot_tracks, ENERGY_CURVES[slot_name])
        write_outputs(slot_name, ordered)


if __name__ == "__main__":
    main()
