#!/usr/bin/env python3
"""
Applique l'ordre calcule par build_rotation.py directement dans New_prog :
renomme les fichiers en place (prefixe 001_, 002_, ...) pour figer le nouvel
ordre de lecture. New_prog est la bibliotheque de reference, il n'y a plus
de copie depuis un dossier source separe.

Renommage en 2 phases (vers un nom temporaire puis le nom final) pour eviter
les collisions quand l'ordre change.

Usage : python export_rotation.py
"""
import os
import re
import csv
import uuid

BASE = os.path.dirname(os.path.abspath(__file__))
PLAYLISTS_DIR = os.path.join(BASE, "playlists")

SLOTS = ["1_morning", "2_afternoon", "3_evening", "4_night"]

PREFIX_RE = re.compile(r"^\d{3}_")


def strip_prefix(filename):
    return PREFIX_RE.sub("", filename)


def apply_slot(slot_name):
    csv_path = os.path.join(PLAYLISTS_DIR, f"{slot_name}.csv")
    if not os.path.exists(csv_path):
        print(f"{slot_name} : pas de CSV trouve, ignore.")
        return

    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Phase 1 : renommage vers des noms temporaires (evite les collisions)
    temp_paths = []
    for row in rows:
        src = row["chemin"]
        if not os.path.exists(src):
            print(f"  MANQUANT : {src}")
            temp_paths.append(None)
            continue
        tmp = os.path.join(os.path.dirname(src), f"_tmp_{uuid.uuid4().hex}.mp3")
        os.rename(src, tmp)
        temp_paths.append(tmp)

    # Phase 2 : renommage vers les noms finaux (position + nom nettoye)
    applied = 0
    for row, tmp in zip(rows, temp_paths):
        if tmp is None:
            continue
        pos = int(row["position"])
        clean_name = strip_prefix(os.path.basename(row["chemin"]))
        dest = os.path.join(os.path.dirname(tmp), f"{pos:03d}_{clean_name}")
        os.rename(tmp, dest)
        applied += 1

    print(f"{slot_name} : {applied} fichiers reordonnes.")


def main():
    for slot in SLOTS:
        apply_slot(slot)


if __name__ == "__main__":
    main()
