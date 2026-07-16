#!/usr/bin/env python3
"""
Nettoyage complet de tools/metadata.json :
1. Normalise tous les chemins au format Windows (C:\\...), qu'ils aient ete
   stockes en WSL (/mnt/c/...) ou Windows -- evite les doublons caches par
   un simple melange de formats.
2. Deduplique par chemin normalise (garde une seule entree par fichier reel).
3. Pour les chemins qui ne correspondent plus a un fichier existant, tente
   une reparation (recherche du fichier reel par nom sans le prefixe NNN_
   dans New_prog) avant de conclure qu'une entree est orpheline. Les entrees
   vraiment irrecuperables sont seulement SIGNALEES, jamais supprimees
   automatiquement (lecon retenue d'une perte de donnees precedente).

Usage : python normalize_and_dedup_metadata.py
"""
import os
import re
import json

BASE = os.path.dirname(os.path.abspath(__file__))
METADATA_PATH = os.path.join(BASE, "metadata.json")
NEW_PROG = r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog"

PREFIX_RE = re.compile(r"^\d{3}_")


def normalize(path):
    return os.path.normcase(path.replace("/mnt/c", "C:").replace("/", "\\"))


def strip_prefix(name):
    return PREFIX_RE.sub("", name)


def main():
    with open(METADATA_PATH, encoding="utf-8") as f:
        metadata = json.load(f)
    print(f"Entrees chargees : {len(metadata)}")

    # -- 1. Normalisation + dedup par chemin --
    by_path = {}
    for d in metadata:
        d["path"] = d["path"].replace("/mnt/c", "C:").replace("/", "\\")
        key = normalize(d["path"])
        by_path[key] = d  # la derniere occurrence l'emporte (donnees equivalentes)

    deduped = list(by_path.values())
    print(f"Apres dedup par chemin : {len(deduped)} (retire {len(metadata) - len(deduped)} doublons)")

    # -- 2. Index des fichiers reels pour reparation --
    index = {}
    for slot in os.listdir(NEW_PROG):
        folder = os.path.join(NEW_PROG, slot)
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if fname.lower().endswith(".mp3"):
                key = strip_prefix(fname).lower()
                index.setdefault(key, []).append(os.path.join(folder, fname))

    already_claimed = {normalize(d["path"]) for d in deduped if os.path.exists(d["path"])}
    for cands in index.values():
        cands[:] = [c for c in cands if normalize(c) not in already_claimed]

    repaired, unresolved, ambiguous = 0, [], 0
    for d in deduped:
        if os.path.exists(d["path"]):
            continue
        key = strip_prefix(os.path.basename(d["path"])).lower()
        candidates = index.get(key, [])
        if not candidates:
            unresolved.append(d["path"])
            continue
        if len(candidates) > 1:
            ambiguous += 1
        chosen = candidates.pop(0)
        d["path"] = chosen
        repaired += 1

    print(f"Chemins repares : {repaired} (dont {ambiguous} avec plusieurs candidats identiques)")

    if unresolved:
        print(f"\n[ATTENTION] {len(unresolved)} entree(s) IRRECUPERABLE(S) -- CONSERVEES telles quelles, pas supprimees :")
        for p in unresolved[:30]:
            print(f"  - {p}")
        if len(unresolved) > 30:
            print(f"  ... et {len(unresolved) - 30} de plus")

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=1)

    real_files = sum(
        1 for slot in os.listdir(NEW_PROG) if os.path.isdir(os.path.join(NEW_PROG, slot))
        for fname in os.listdir(os.path.join(NEW_PROG, slot)) if fname.lower().endswith(".mp3")
    )
    print(f"\nFinal : {len(deduped)} entrees dans metadata.json, {real_files} fichiers reels dans New_prog.")


if __name__ == "__main__":
    main()
