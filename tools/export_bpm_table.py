#!/usr/bin/env python3
"""
Genere api/bpm-table.json (artiste+titre -> BPM) a partir de tools/metadata.json
et des tags ID3 reels des fichiers locaux, pour le jeu "devine le BPM" du chat
live (api/chat.js). Le BPM est deja calcule par Essentia (analyze_essentia.py)
mais reste en local -- ce script l'associe a l'artiste/titre EXACTS que
AzuraCast affichera (memes tags ID3, lus par mutagen comme dans
clean_local_tracks.py), pour un matching fiable au runtime.

Appele automatiquement a la fin de triage_new_tracks.py (donc aussi par
triage.bat) : la table suivait mal les sessions de triage lancees en WSL sans
passer par le .bat, et le jeu devenait muet sur les morceaux recents -- panne
constatee deux fois (2026-07-28 : 749 entrees pour 995 morceaux ; 2026-09-04 :
899 pour 1231). Reste lancable a la main apres coup :

    python tools/export_bpm_table.py [--force]

RIEN N'EST DEPLOYE TANT QUE api/bpm-table.json N'EST PAS COMMITE ET PUSHE :
le jeu lit la table embarquee dans la fonction Vercel, pas le disque local.
"""
import os
import re
import sys
import json

from mutagen import File as MFile

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
METADATA_PATH = os.path.join(TOOLS_DIR, "metadata.json")
OUTPUT_PATH = os.path.join(os.path.dirname(TOOLS_DIR), "api", "bpm-table.json")

# Garde-fou : refuse de reecrire la table si elle perdait plus de la moitie de
# ses entrees. Une chute pareille ne vient jamais de la bibliotheque mais de
# l'environnement (chemins non resolus, disque non monte) -- et ecraserait une
# table saine par une table vide, en rendant le jeu muet partout.
MIN_KEEP_RATIO = 0.5

WIN_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")


def resolve_path(path):
    r"""metadata.json stocke des chemins Windows ("C:\Users\..."), mais ce script
    tourne aussi dans le venv WSL (appel en fin de triage_new_tracks.py). Sans
    conversion, os.path.exists() serait faux pour TOUS les morceaux et la table
    repartirait a zero."""
    if os.name == "nt":
        return path
    m = WIN_DRIVE_RE.match(path)
    if m:
        return "/mnt/" + m.group(1).lower() + "/" + m.group(2).replace("\\", "/")
    return path


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


def previous_count():
    if not os.path.exists(OUTPUT_PATH):
        return 0
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            return len(json.load(f))
    except Exception:
        return 0


def main(force=False):
    """Retourne True si la table a ete reecrite, False si le garde-fou a bloque."""
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
        path = resolve_path(path)
        if not os.path.exists(path):
            skipped_missing_file += 1
            continue
        artist, title = read_artist_title(path)
        if not artist or not title:
            skipped_no_tags += 1
            continue
        table.append({"artist": artist, "title": title, "bpm": round(float(bpm), 1)})

    before = previous_count()
    if before and len(table) < before * MIN_KEEP_RATIO and not force:
        print(
            f"[ABANDON] {len(table)} morceau(x) exportables contre {before} dans la "
            f"table actuelle — {OUTPUT_PATH} n'est PAS reecrit.\n"
            f"  Cause probable : les fichiers de metadata.json sont introuvables "
            f"depuis cet environnement ({skipped_missing_file} manquants).\n"
            f"  Relancer avec --force si la bibliotheque a reellement fondu."
        )
        return False

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, indent=1)

    print(f"{len(table)} morceau(x) exporte(s) vers {OUTPUT_PATH}")
    print(f"  ignores (fichier introuvable) : {skipped_missing_file}")
    print(f"  ignores (tags artist/title manquants) : {skipped_no_tags}")
    print(f"  total metadata.json : {len(entries)}")
    if len(table) != before:
        print(f"  (table precedente : {before} entrees)")
    return True


if __name__ == "__main__":
    main(force="--force" in sys.argv)
