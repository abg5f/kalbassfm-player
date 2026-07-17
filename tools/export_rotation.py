#!/usr/bin/env python3
"""
*** SUPERSEDED (2026-07-16) — NE PLUS UTILISER ***
Remplace par la grille "horloge a bacs ponderes" : plus aucun prefixe d'ordre
NNN_ dans les noms de fichiers, l'ordonnancement est delegue a AzuraCast
(playlists Shuffled + poids + separation artiste). Conserve pour l'historique.

Applique l'ordre calcule par build_rotation.py directement dans New_prog :
renomme les fichiers en place (prefixe 001_, 002_, ...) pour figer le nouvel
ordre de lecture. New_prog est la bibliotheque de reference, il n'y a plus
de copie depuis un dossier source separe.

Renommage en 2 phases (vers un nom temporaire puis le nom final) pour eviter
les collisions quand l'ordre change. Met a jour metadata.json avec les
nouveaux chemins a la fin (sinon metadata.json devient perime des le premier
renommage et casse les prochains runs).

Usage : python export_rotation.py
"""
import os
import re
import csv
import json
import uuid

BASE = os.path.dirname(os.path.abspath(__file__))
PLAYLISTS_DIR = os.path.join(BASE, "playlists")
METADATA_PATH = os.path.join(BASE, "metadata.json")

SLOTS = ["1_morning", "2_afternoon", "3_evening", "4_night"]

PREFIX_RE = re.compile(r"^\d{3}_")


def strip_prefix(filename):
    return PREFIX_RE.sub("", filename)


def apply_slot(slot_name, path_updates):
    csv_path = os.path.join(PLAYLISTS_DIR, f"{slot_name}.csv")
    if not os.path.exists(csv_path):
        print(f"{slot_name} : pas de CSV trouve, ignore.")
        return

    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Deduplique par chemin source : deux lignes ne doivent jamais renommer
    # le meme fichier (sinon la 2e echoue silencieusement et laisse un
    # fichier temporaire orphelin).
    seen_src = set()
    for row in rows:
        src = row["chemin"]
        if src in seen_src:
            print(f"  DOUBLON dans le CSV, ligne ignoree : {src}")
            row["chemin"] = None
        seen_src.add(src)

    # Phase 1 : renommage vers des noms temporaires (evite les collisions)
    temp_paths = []
    for row in rows:
        src = row["chemin"]
        if not src or not os.path.exists(src):
            if src:
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
        path_updates[row["chemin"]] = dest
        applied += 1

    print(f"{slot_name} : {applied} fichiers reordonnes.")


def sync_metadata(path_updates):
    if not path_updates or not os.path.exists(METADATA_PATH):
        return
    with open(METADATA_PATH, encoding="utf-8") as f:
        metadata = json.load(f)
    updated = 0
    for d in metadata:
        if d["path"] in path_updates:
            d["path"] = path_updates[d["path"]]
            updated += 1
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=1)
    print(f"metadata.json resynchronise : {updated} chemins mis a jour.")


def check_orphans():
    orphans = []
    root = r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog"
    for slot in SLOTS:
        folder = os.path.join(root, slot)
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if fname.startswith("_tmp_"):
                orphans.append(os.path.join(folder, fname))
    if orphans:
        print(f"\n[ATTENTION] {len(orphans)} fichier(s) bloque(s) en nom temporaire :")
        for o in orphans:
            print(f"  {o}")


def main():
    path_updates = {}
    for slot in SLOTS:
        apply_slot(slot, path_updates)
    sync_metadata(path_updates)
    check_orphans()


if __name__ == "__main__":
    main()
