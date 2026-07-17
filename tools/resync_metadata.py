#!/usr/bin/env python3
"""Resynchronise les chemins de metadata.json avec les fichiers reels sur disque.

Le triage/export renumerote les fichiers (prefixe NNN_) sans toujours mettre a
jour metadata.json pour les morceaux deja connus -> chemins obsoletes. Ce
script rapproche chaque entree de son fichier reel par nom SANS prefixe :

  1. chemin exact valide                     -> conserve tel quel
  2. nom unique sur le disque                -> chemin mis a jour
  3. nom ambigu (doublons physiques)         -> appariement 1:1 deterministe ;
     les fichiers disque en surplus sont des doublons physiques (rapportes)
  4. entree sans aucun fichier correspondant -> supprimee (--apply)
  5. fichier disque absent de metadata       -> liste dans orphans_report.txt
     (a deposer dans _incoming pour re-triage une fois la nouvelle grille en place)

Usage :
    python resync_metadata.py            # dry-run : rapport seul
    python resync_metadata.py --apply    # ecrit metadata.json repare

Ne touche JAMAIS aux fichiers audio — seul metadata.json est modifie.
"""
import json
import os
import re
import sys

NEW_PROG = r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog"
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
METADATA = os.path.join(TOOLS_DIR, "metadata.json")
ORPHANS_REPORT = os.path.join(TOOLS_DIR, "orphans_report.txt")

PREFIX_RE = re.compile(r"^\d{3}_")
AUDIO_EXTS = (".mp3", ".wav", ".flac", ".aiff", ".m4a", ".ogg")


def stripped_key(path):
    return PREFIX_RE.sub("", os.path.basename(path)).lower()


def main():
    apply_mode = "--apply" in sys.argv

    # Inventaire disque : nom sans prefixe -> chemins (tries pour determinisme)
    disk = {}
    total_disk = 0
    for slot in sorted(os.listdir(NEW_PROG)):
        folder = os.path.join(NEW_PROG, slot)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith(AUDIO_EXTS):
                continue
            total_disk += 1
            disk.setdefault(stripped_key(name), []).append(os.path.join(folder, name))

    with open(METADATA, encoding="utf-8") as f:
        tracks = json.load(f)
    print(f"{len(tracks)} entrees metadata, {total_disk} fichiers sur disque")

    # Les chemins deja valides reservent leur fichier en premier
    available = {k: list(v) for k, v in disk.items()}
    kept = updated = removed = 0
    repaired = []
    lost_entries = []

    for t in tracks:
        p = t.get("path", "")
        if os.path.isfile(p):
            k = stripped_key(p)
            if p in available.get(k, []):
                available[k].remove(p)
            kept += 1
            repaired.append(t)

    for t in tracks:
        p = t.get("path", "")
        if os.path.isfile(p):
            continue
        k = stripped_key(p)
        cands = available.get(k, [])
        if cands:
            new_path = cands.pop(0)   # appariement 1:1 deterministe (listes triees)
            t["path"] = new_path
            updated += 1
            repaired.append(t)
        else:
            removed += 1
            lost_entries.append(p)

    # Fichiers disque restants : soit doublons physiques (leur nom existe dans
    # metadata mais toutes les entrees sont servies), soit jamais analyses.
    meta_keys = {stripped_key(t["path"]) for t in repaired}
    duplicates = []
    orphans = []
    for k, paths in available.items():
        for p in paths:
            (duplicates if k in meta_keys else orphans).append(p)

    print(f"\n  chemins deja valides          : {kept}")
    print(f"  chemins repares               : {updated}")
    print(f"  entrees supprimees (perdues)  : {removed}")
    print(f"  doublons physiques sur disque : {len(duplicates)} (non touches — nettoyage manuel, TODO connu)")
    print(f"  fichiers jamais analyses      : {len(orphans)} -> {os.path.basename(ORPHANS_REPORT)}")

    if lost_entries:
        print("\nEntrees supprimees (fichier disparu) :")
        for p in lost_entries[:10]:
            print(f"  - {os.path.basename(p)}")
        if len(lost_entries) > 10:
            print(f"  ... et {len(lost_entries) - 10} autres")

    with open(ORPHANS_REPORT, "w", encoding="utf-8") as f:
        f.write("# Fichiers presents sur disque mais absents de metadata.json.\n")
        f.write("# A deposer dans _incoming puis relancer triage.bat (une fois la\n")
        f.write("# nouvelle grille en place) pour les analyser et les classer.\n")
        for p in sorted(orphans):
            f.write(p + "\n")
        f.write("\n# Doublons physiques (nom deja servi par une entree metadata) :\n")
        for p in sorted(duplicates):
            f.write("# DOUBLON  " + p + "\n")

    if not apply_mode:
        print("\nDRY-RUN termine — metadata.json inchange. Relancer avec --apply pour reparer.")
        return

    with open(METADATA, "w", encoding="utf-8") as f:
        json.dump(repaired, f, ensure_ascii=False, indent=1)
    print(f"\nmetadata.json repare : {len(repaired)} entrees, toutes avec un fichier existant.")

    broken = [t["path"] for t in repaired if not os.path.isfile(t["path"])]
    print("Verification finale : " + ("OK, zero chemin casse." if not broken else f"{len(broken)} chemins casses !"))


if __name__ == "__main__":
    main()
