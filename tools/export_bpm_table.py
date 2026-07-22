#!/usr/bin/env python3
"""
Genere api/bpm-table.json (artiste+titre -> BPM) a partir de tools/metadata.json
et des tags ID3 reels des fichiers locaux, pour le jeu "devine le BPM" du chat
live (api/chat.js). Le BPM est deja calcule par Essentia (analyze_essentia.py)
mais reste en local -- ce script l'associe a l'artiste/titre EXACTS que
AzuraCast affichera (memes tags ID3, lus par mutagen comme dans
clean_local_tracks.py), pour un matching fiable au runtime.

A relancer (puis commit/push) apres chaque session de triage qui ajoute des
morceaux a la bibliotheque -- la table n'est pas regeneree automatiquement.

Usage : python tools/export_bpm_table.py
"""
import os
import json

from mutagen import File as MFile

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
METADATA_PATH = os.path.join(TOOLS_DIR, "metadata.json")
OUTPUT_PATH = os.path.join(os.path.dirname(TOOLS_DIR), "api", "bpm-table.json")


def read_artist_title(path):
    try:
        audio = MFile(path, easy=True)
    except Exception:
        return None, None
    if not audio or audio.tags is None:
        return None, None
    title_vals = audio.tags.get('title')
    artist_vals = audio.tags.get('artist')
    title = title_vals[0].strip() if title_vals else ''
    artist = artist_vals[0].strip() if artist_vals else ''
    return artist or None, title or None


def main():
    with open(METADATA_PATH, encoding="utf-8") as f:
        entries = json.load(f)

    table = []
    skipped_missing_file = 0
    skipped_no_tags = 0

    for entry in entries:
        path = entry.get("path")
        bpm = entry.get("bpm")
        if not path or bpm is None:
            continue
        if not os.path.exists(path):
            skipped_missing_file += 1
            continue
        artist, title = read_artist_title(path)
        if not artist or not title:
            skipped_no_tags += 1
            continue
        table.append({"artist": artist, "title": title, "bpm": round(float(bpm), 1)})

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, indent=1)

    print(f"{len(table)} morceau(x) exporte(s) vers {OUTPUT_PATH}")
    print(f"  ignores (fichier introuvable) : {skipped_missing_file}")
    print(f"  ignores (tags artist/title manquants) : {skipped_no_tags}")
    print(f"  total metadata.json : {len(entries)}")


if __name__ == "__main__":
    main()
