#!/usr/bin/env python3
"""
Analyse la bibliotheque locale avec Essentia (modeles TensorFlow discogs-effnet)
pour extraire BPM, energie (RMS/dynamic complexity), danceability, mood
(happy/sad/aggressive/relaxed/party) et top-3 genres par morceau.

A executer dans le venv WSL (~/essentia-env). Ne modifie aucun fichier audio :
ecrit uniquement un JSON de metadonnees, sauvegarde incrementalement.

Usage : python3 analyze_essentia.py [--limit N]
"""
import os
import sys
import json
import glob
import numpy as np
from essentia.standard import (
    MonoLoader, TensorflowPredictEffnetDiscogs, TensorflowPredict2D,
    RhythmExtractor2013, RMS, DynamicComplexity,
)

MODELS_DIR = os.path.expanduser("~/kalbassfm-analysis/models")
ROOTS = [
    "/mnt/c/Users/ph.dufourcq/Music/00_AZURACAST/New_prog/1_morning",
    "/mnt/c/Users/ph.dufourcq/Music/00_AZURACAST/New_prog/2_afternoon",
    "/mnt/c/Users/ph.dufourcq/Music/00_AZURACAST/New_prog/3_evening",
    "/mnt/c/Users/ph.dufourcq/Music/00_AZURACAST/New_prog/4_night",
]
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata.json")

LIMIT = None
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])

GENRE_LABELS = json.load(
    open(os.path.join(MODELS_DIR, "genre_discogs400-discogs-effnet-1.json"))
)["classes"]

embedding_model = TensorflowPredictEffnetDiscogs(
    graphFilename=os.path.join(MODELS_DIR, "discogs-effnet-bs64-1.pb"),
    output="PartitionedCall:1",
)


def make_head(name):
    return TensorflowPredict2D(
        graphFilename=os.path.join(MODELS_DIR, f"{name}-discogs-effnet-1.pb"),
        input="model/Placeholder",
        output="model/Softmax",
    )


genre_model = TensorflowPredict2D(
    graphFilename=os.path.join(MODELS_DIR, "genre_discogs400-discogs-effnet-1.pb"),
    input="serving_default_model_Placeholder",
    output="PartitionedCall:0",
)
dance_model = make_head("danceability")
mood_happy_model = make_head("mood_happy")
mood_sad_model = make_head("mood_sad")
mood_aggressive_model = make_head("mood_aggressive")
mood_relaxed_model = make_head("mood_relaxed")
mood_party_model = make_head("mood_party")


def analyze(path):
    audio16 = MonoLoader(filename=path, sampleRate=16000, resampleQuality=4)()
    embeddings = embedding_model(audio16)

    genre_probs = genre_model(embeddings).mean(axis=0)
    top_idx = np.argsort(genre_probs)[::-1][:3]
    top_genres = [[GENRE_LABELS[i], float(genre_probs[i])] for i in top_idx]

    dance = float(dance_model(embeddings).mean(axis=0)[0])
    mood_happy = float(mood_happy_model(embeddings).mean(axis=0)[0])
    mood_sad = float(mood_sad_model(embeddings).mean(axis=0)[0])
    mood_aggressive = float(mood_aggressive_model(embeddings).mean(axis=0)[0])
    mood_relaxed = float(mood_relaxed_model(embeddings).mean(axis=0)[0])
    mood_party = float(mood_party_model(embeddings).mean(axis=0)[0])

    audio44 = MonoLoader(filename=path, sampleRate=44100)()
    bpm, _, _, _, _ = RhythmExtractor2013(method="multifeature")(audio44)
    rms = float(RMS()(audio44))
    dyn_complexity, _ = DynamicComplexity()(audio44)

    return {
        "path": path,
        "bpm": float(bpm),
        "rms": rms,
        "dynamic_complexity": float(dyn_complexity),
        "danceability": dance,
        "mood": {
            "happy": mood_happy,
            "sad": mood_sad,
            "aggressive": mood_aggressive,
            "relaxed": mood_relaxed,
            "party": mood_party,
        },
        "genres": top_genres,
    }


def normalize_path(path):
    """Normalise un chemin WSL (/mnt/c/...) ou Windows (C:\\...) vers une forme
    Windows comparable, pour que la verification "deja analyse" fonctionne
    quel que soit le format sous lequel un chemin a ete stocke precedemment."""
    return os.path.normcase(path.replace("/mnt/c", "C:").replace("/", "\\"))


def main():
    files = []
    for root in ROOTS:
        files += glob.glob(os.path.join(root, "**", "*.mp3"), recursive=True)
    files.sort()
    if LIMIT:
        files = files[:LIMIT]
    print(f"{len(files)} fichiers trouves.")

    results = []
    if os.path.exists(OUTPUT):
        results = json.load(open(OUTPUT, encoding="utf-8"))
    done_paths = {normalize_path(r["path"]) for r in results}

    for i, path in enumerate(files):
        if normalize_path(path) in done_paths:
            continue
        try:
            r = analyze(path)
            r["path"] = path.replace("/mnt/c", "C:").replace("/", "\\")
            results.append(r)
            print(
                f"[{i + 1}/{len(files)}] OK {os.path.basename(path)} "
                f"bpm={r['bpm']:.0f} genre={r['genres'][0][0]} energy_rms={r['rms']:.3f}"
            )
        except Exception as e:
            print(f"[{i + 1}/{len(files)}] ERREUR {os.path.basename(path)}: {e}")
        if (i + 1) % 20 == 0:
            json.dump(results, open(OUTPUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    json.dump(results, open(OUTPUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Termine. {len(results)} morceaux analyses -> {OUTPUT}")


if __name__ == "__main__":
    main()
