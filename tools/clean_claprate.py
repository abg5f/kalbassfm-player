#!/usr/bin/env python3
"""
Retire les morceaux avec CLAPRATE.COM des métadonnées et optionnellement supprime
les fichiers audio et leurs covers suspectes.

Usage :
    python clean_claprate.py            # dry-run : affiche ce qui sera retiré
    python clean_claprate.py --apply    # supprime effectivement
"""
import os
import sys
import json
import io
from mutagen import File as MFile
from mutagen.id3 import ID3

# Force UTF-8 output on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
METADATA_PATH = os.path.join(TOOLS_DIR, "metadata.json")
APPLY = "--apply" in sys.argv
DELETE_FILES = "--delete-files" in sys.argv


def check_claprate(path):
    """Retourne True si le fichier contient 'claprate' dans les tags."""
    try:
        audio = MFile(path, easy=True)
        if not audio or audio.tags is None:
            return False

        for tag_name in ("artist", "title", "album", "comment"):
            values = audio.tags.get(tag_name, [])
            for val in values:
                if val and "claprate" in val.lower():
                    return True
        return False
    except Exception:
        return False


def main():
    with open(METADATA_PATH, encoding="utf-8") as f:
        metadata = json.load(f)

    print(f"Total d'entrees metadata : {len(metadata)}\n")

    claprate_entries = []
    for entry in metadata:
        path = entry.get("path")
        if not path:
            continue
        if not os.path.exists(path):
            continue

        # Vérifie les tags ID3
        if check_claprate(path):
            claprate_entries.append((path, entry))

    if not claprate_entries:
        print("[OK] Aucun fichier CLAPRATE.COM trouvé.")
        return

    print(f"[!] {len(claprate_entries)} morceau(x) CLAPRATE.COM detecte(s) :\n")
    for path, entry in claprate_entries:
        artist = (entry.get("genres") or [["?", 0]])[0][0]
        print(f"  - {os.path.basename(path)}")
        print(f"    Chemin : {path}")
        try:
            audio = MFile(path, easy=True)
            if audio and audio.tags:
                print(f"    Artiste : {(audio.tags.get('artist') or ['?'])[0]}")
                print(f"    Titre : {(audio.tags.get('title') or ['?'])[0]}")
        except Exception:
            pass
        print()

    if not APPLY:
        print(f"\nDRY-RUN terminé. Relancez avec --apply pour supprimer ces {len(claprate_entries)} entree(s) de metadata.json")
        if not DELETE_FILES:
            print("           et avec --delete-files pour aussi supprimer les fichiers audio.")
        return

    # Supprime les entrées de metadata.json
    cleaned = [e for e in metadata if e.get("path") not in {p for p, _ in claprate_entries}]
    removed_count = len(metadata) - len(cleaned)

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=1)

    print(f"[OK] metadata.json nettoye : {removed_count} entree(s) supprimee(s)")
    print(f"  Avant : {len(metadata)} | Apres : {len(cleaned)}")

    # Optionnellement supprime les fichiers audio
    if DELETE_FILES:
        deleted = 0
        for path, _ in claprate_entries:
            try:
                os.remove(path)
                print(f"  [OK] Supprime : {os.path.basename(path)}")
                deleted += 1
            except Exception as e:
                print(f"  [ERR] Erreur suppression {os.path.basename(path)} : {e}")
        print(f"\n[OK] {deleted} fichier(s) audio supprime(s)")
    else:
        print("\nNote : les fichiers audio sont toujours sur disque. Relancez avec --delete-files pour les supprimer aussi.")


if __name__ == "__main__":
    main()
