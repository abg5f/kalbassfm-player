#!/usr/bin/env python3
"""
Deduplique tools/metadata.json par chemin (path) : garde une seule entree par
fichier reel. A utiliser quand plusieurs process (triage_new_tracks.py +
analyze_essentia.py) ont analyse les memes fichiers en parallele.

Usage : python dedup_metadata.py
"""
import os
import json

BASE = os.path.dirname(os.path.abspath(__file__))
METADATA_PATH = os.path.join(BASE, "metadata.json")

with open(METADATA_PATH, encoding="utf-8") as f:
    metadata = json.load(f)

seen = {}
for entry in metadata:
    seen[entry["path"]] = entry  # la derniere occurrence l'emporte

deduped = list(seen.values())

# Retire aussi les entrees dont le fichier n'existe plus sur le disque
existing = [d for d in deduped if os.path.exists(d["path"])]
missing = len(deduped) - len(existing)

with open(METADATA_PATH, "w", encoding="utf-8") as f:
    json.dump(existing, f, ensure_ascii=False, indent=1)

print(f"avant: {len(metadata)}  apres dedup: {len(deduped)}  fichiers manquants retires: {missing}  final: {len(existing)}")
