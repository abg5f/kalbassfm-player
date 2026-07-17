#!/usr/bin/env python3
"""
*** SUPERSEDED (2026-07-16) — NE PLUS UTILISER ***
Remplace par la grille "horloge a bacs ponderes" (classify_bins.py +
migrate_grid.py) : l'ordonnancement est desormais delegue a AzuraCast
(playlists Shuffled + poids + separation artiste), plus aucun ordre n'est
calcule localement. Conserve uniquement pour l'historique.

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
import math
import random
from collections import deque, defaultdict

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

GENRE_WINDOW = 4    # pas 2 fois le meme sous-genre exact dans les 4 derniers morceaux
ARTIST_WINDOW = 8   # pas 2 fois le meme artiste dans les 8 derniers morceaux
ENERGY_BUCKET = 0.04  # granularite du tri energie (le BPM ne departage qu'a l'interieur d'un meme palier)

# Mini-mouvements : au lieu d'une seule rampe lineaire du debut a la fin du
# creneau, on superpose une onde qui cree des respirations (petites montees/
# descentes) sur la trajectoire globale, façon set DJ plutot qu'une ligne
# droite. L'amplitude est reduite pres des bords du creneau pour ne pas
# perturber la valeur de depart/fin (utile pour la jonction de boucle).
MOVEMENTS_PER_SLOT = 4
MOVEMENT_AMPLITUDE = 0.12

# Quota minoritaire : une famille qui represente moins de MINORITY_THRESHOLD
# du creneau doit apparaitre au moins une fois par quart de creneau (au lieu
# d'etre livree au hasard de la selection par plus-grande-famille-eligible,
# qui tend a la reserver pour la fin).
MINORITY_THRESHOLD = 0.15
QUARTERS = 4

# Regroupe les sous-genres Discogs en familles de style plus larges, pour forcer
# un vrai changement d'ambiance (pas juste de sous-genre) : au-dela de
# FAMILY_MAX_STREAK morceaux consecutifs de la meme famille, le suivant doit
# obligatoirement en changer (ex. 2 House d'affilee max avant de passer a autre
# chose, meme si les sous-genres House different).
FAMILY_MAX_STREAK = 2

FAMILY_KEYWORDS = [
    ("Techno", ["techno"]),
    ("Garage", ["garage", "bassline"]),
    ("House", ["house"]),
    ("Disco/Funk", ["disco", "funk", "soul"]),
    ("Reggae/Dub", ["reggae", "dub", "dancehall", "ska"]),
    ("Jungle/DnB", ["jungle", "drum n bass", "drum & bass", "drum and bass", "dnb", "d&b", "d n b"]),
]


def target_energy(i, n, start, end):
    """Cible d'energie a la position i : rampe globale start->end, avec une
    onde de mini-mouvements superposee (attenuee pres des bords du creneau)."""
    t = i / max(n - 1, 1)
    base = start + (end - start) * t
    taper = 1 - abs(2 * t - 1) * 0.3
    wave = MOVEMENT_AMPLITUDE * math.sin(t * MOVEMENTS_PER_SLOT * math.pi) * taper
    return max(0.0, min(1.0, base + wave))


def style_family(genre):
    g = genre.lower()
    for family, keywords in FAMILY_KEYWORDS:
        if any(k in g for k in keywords):
            return family
    return genre  # sous-genre rare/inconnu : traite comme sa propre famille


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
    """Construit l'ordre de lecture. La contrainte de famille de style est geree
    en priorite (algorithme type "task scheduler" : toujours piocher dans la
    famille eligible la plus fournie) pour etaler une famille dominante sur
    toute la duree plutot que de la laisser s'accumuler en fin de liste une
    fois les familles minoritaires epuisees. A l'interieur de la famille
    retenue, l'energie reste le premier critere de tri (par palier) ; le BPM
    ne sert qu'a departager les morceaux d'un meme palier d'energie, pour
    eviter les sauts de tempo brusques d'un morceau a l'autre."""
    start, end = curve
    n = len(slot_tracks)
    ordered = []
    recent_genres = deque(maxlen=GENRE_WINDOW)
    recent_artists = deque(maxlen=ARTIST_WINDOW)
    family_streak, family_streak_len = None, 0

    buckets = {}
    for t in slot_tracks:
        buckets.setdefault(style_family(t["genre"]), []).append(t)

    minority_families = {fam for fam, items in buckets.items() if len(items) / n < MINORITY_THRESHOLD}
    quarter_size = max(1, -(-n // QUARTERS))  # division entiere arrondie au superieur
    minority_quota = {fam: -(-len(buckets[fam]) // QUARTERS) for fam in minority_families}
    minority_used = defaultdict(int)
    current_quarter = 0

    for i in range(n):
        quarter = min(i // quarter_size, QUARTERS - 1)
        if quarter != current_quarter:
            current_quarter = quarter
            minority_used.clear()
        remaining_in_quarter = quarter_size - (i % quarter_size)

        target = target_energy(i, n, start, end)

        eligible = [
            fam for fam, items in buckets.items()
            if items and (fam != family_streak or family_streak_len < FAMILY_MAX_STREAK)
        ]
        if not eligible:
            # Plus aucune alternative : toutes les familles restantes sont en
            # cooldown, seule celle du streak a encore des morceaux.
            eligible = [fam for fam, items in buckets.items() if items]

        # Quota minoritaire : si une famille rare n'a pas encore rempli son
        # quota pour ce quart de creneau et qu'il reste peu de place avant la
        # fin du quart, on la priorise avant qu'elle ne soit definitivement
        # ratee pour ce quart.
        urgent = [
            fam for fam in eligible
            if fam in minority_families
            and minority_used[fam] < minority_quota.get(fam, 0)
            and remaining_in_quarter <= (minority_quota[fam] - minority_used[fam]) * 2
        ]
        chosen_family = urgent[0] if urgent else max(eligible, key=lambda f: len(buckets[f]))
        family_pool = buckets[chosen_family]

        filtered = [t for t in family_pool if t["genre"] not in recent_genres and (t["artist"] == "?" or t["artist"] not in recent_artists)]
        if not filtered:
            filtered = [t for t in family_pool if t["genre"] not in recent_genres]
        if not filtered:
            filtered = family_pool

        last_bpm = ordered[-1]["bpm"] if ordered else None

        def sort_key(t):
            energy_bucket = round(abs(t["energy"] - target) / ENERGY_BUCKET)
            bpm_gap = abs(t["bpm"] - last_bpm) if last_bpm is not None else 0
            return (energy_bucket, bpm_gap)

        filtered = sorted(filtered, key=sort_key)
        pick = random.choice(filtered[:max(1, len(filtered) // 3)])

        family_pool.remove(pick)
        ordered.append(pick)
        recent_genres.append(pick["genre"])
        if pick["artist"] != "?":
            recent_artists.append(pick["artist"])
        if chosen_family in minority_families:
            minority_used[chosen_family] += 1

        if chosen_family == family_streak:
            family_streak_len += 1
        else:
            family_streak, family_streak_len = chosen_family, 1

    ordered = enforce_family_limit(ordered)
    return enforce_family_limit(fix_wrap_seam(ordered))


def enforce_family_limit(ordered, max_passes=5):
    """Garde-fou final : repare toute sequence de plus de FAMILY_MAX_STREAK
    morceaux consecutifs de la meme famille. Peut survenir en fin de creneau
    (plus aucune autre famille disponible) ou apres la rotation de
    fix_wrap_seam (qui peut recoller deux segments jamais verifies ensemble).
    Cherche un remplacant dans les deux sens (une violation en toute fin de
    liste n'a rien "apres" avec quoi echanger) ; plusieurs passes rattrapent
    une eventuelle violation reintroduite ailleurs par un echange arriere."""
    if len(ordered) <= FAMILY_MAX_STREAK:
        return ordered
    n = len(ordered)

    for _ in range(max_passes):
        fams = [style_family(t["genre"]) for t in ordered]
        fixed_any = False
        i = FAMILY_MAX_STREAK
        while i < n:
            if all(fams[i - o] == fams[i] for o in range(1, FAMILY_MAX_STREAK + 1)):
                swapped = False
                for dist in range(1, n):
                    for j in (i + dist, i - dist):
                        if 0 <= j < n and fams[j] != fams[i]:
                            ordered[i], ordered[j] = ordered[j], ordered[i]
                            fams[i], fams[j] = fams[j], fams[i]
                            swapped = True
                            fixed_any = True
                            break
                    if swapped:
                        break
                if not swapped:
                    break  # toute la liste est de la meme famille : cas degenere
                continue  # re-verifie la meme position, l'echange a pu ne pas suffire
            i += 1
        if not fixed_any:
            break

    return ordered


def fix_wrap_seam(ordered):
    """AzuraCast boucle la playlist en continu : le dernier morceau enchaine
    directement sur le premier. Si cette jonction viole la contrainte de
    famille (ou rejoue le meme artiste), on fait pivoter la liste jusqu'a une
    coupure propre existante plutot que de casser l'ordonnancement deja calcule."""
    if len(ordered) < 3:
        return ordered

    def seam_ok(last, first):
        if style_family(last["genre"]) == style_family(first["genre"]):
            return False
        if last["artist"] != "?" and last["artist"] == first["artist"]:
            return False
        return True

    if seam_ok(ordered[-1], ordered[0]):
        return ordered

    for shift in range(1, len(ordered)):
        if seam_ok(ordered[shift - 1], ordered[shift]):
            return ordered[shift:] + ordered[:shift]

    return ordered  # aucune coupure propre trouvee (cas degenere) : inchange


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
