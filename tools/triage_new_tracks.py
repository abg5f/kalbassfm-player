#!/usr/bin/env python3
"""
Pipeline d'integration des nouveaux telechargements deposes dans _incoming :

1. Nettoie les tags ID3 / nom de fichier / cover (reprend clean_local_tracks.py)
2. Analyse Essentia (energie, bpm, genre, mood, danceability)
3. Classe le morceau dans le creneau (morning/afternoon/evening/night) dont
   la courbe d'energie cible est la plus proche
4. Deplace le fichier nettoye dans le dossier du creneau correspondant
   (bibliotheque source, PAS New_prog)
5. Ajoute le resultat a metadata.json
6. Regenere automatiquement New_prog (build_rotation.py + export_rotation.py)

Les fichiers illisibles/en erreur sont deplaces dans _incoming/_failed/ et
n'interrompent pas le traitement des autres.

A executer dans le venv WSL (~/essentia-env) :
    source ~/essentia-env/bin/activate
    python3 "/mnt/c/Users/ph.dufourcq/Documents/0_Claude Code/3_Radiofm/tools/triage_new_tracks.py"
"""
import os
import sys
import json
import shutil
import subprocess

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)

import analyze_essentia  # noqa: E402  (modeles Essentia charges a l'import)
import clean_local_tracks as clt  # noqa: E402  (fonctions clean() / itunes_lookup())

INCOMING = r"C:\Users\ph.dufourcq\Music\00_AZURACAST\_incoming".replace("\\", "/").replace("C:", "/mnt/c")
FAILED = os.path.join(INCOMING, "_failed")

SLOT_FOLDERS = {
    "1_morning": "/mnt/c/Users/ph.dufourcq/Music/00_AZURACAST/New_prog/1_morning",
    "2_afternoon": "/mnt/c/Users/ph.dufourcq/Music/00_AZURACAST/New_prog/2_afternoon",
    "3_evening": "/mnt/c/Users/ph.dufourcq/Music/00_AZURACAST/New_prog/3_evening",
    "4_night": "/mnt/c/Users/ph.dufourcq/Music/00_AZURACAST/New_prog/4_night",
}

# Doit rester coherent avec ENERGY_CURVES dans build_rotation.py
ENERGY_CURVES = {
    "1_morning": (0.20, 0.60),
    "2_afternoon": (0.45, 0.75),
    "3_evening": (0.55, 0.90),
    "4_night": (0.65, 0.25),
}

METADATA_PATH = os.path.join(TOOLS_DIR, "metadata.json")
BUILD_ROTATION = os.path.join(TOOLS_DIR, "build_rotation.py")
EXPORT_ROTATION = os.path.join(TOOLS_DIR, "export_rotation.py")


def load_metadata():
    if os.path.exists(METADATA_PATH):
        with open(METADATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_metadata(data):
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def energy_bounds(existing):
    rms_vals = [d["rms"] for d in existing] or [0.0, 1.0]
    bpm_vals = [d["bpm"] for d in existing] or [60.0, 180.0]
    return (min(rms_vals), max(rms_vals)), (min(bpm_vals), max(bpm_vals))


def norm_clip(value, lo, hi):
    if hi - lo < 1e-9:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def classify_slot(energy):
    def midpoint(curve):
        return (curve[0] + curve[1]) / 2
    return min(ENERGY_CURVES, key=lambda slot: abs(energy - midpoint(ENERGY_CURVES[slot])))


def clean_tags_and_filename(path):
    """Nettoie tags/nom de fichier in place, retourne le nouveau chemin."""
    from mutagen import File as MFile
    from mutagen.id3 import ID3, APIC
    import time

    audio = MFile(path, easy=True)
    title = artist = ""
    if audio and audio.tags is not None:
        changed = False
        for tag in ("title", "artist", "album"):
            vals = audio.tags.get(tag)
            if not vals:
                continue
            new = clt.clean(vals[0])
            if tag == "title":
                title = new
            if tag == "artist":
                artist = new
            if new and new != vals[0]:
                audio.tags[tag] = new
                changed = True
        if changed:
            audio.save()

    stem, ext = os.path.splitext(path)
    dirname, basename = os.path.split(stem)
    new_stem = clt.clean(basename)
    new_path = path
    if new_stem and new_stem != basename:
        candidate = os.path.join(dirname, new_stem + ext)
        if not os.path.exists(candidate):
            os.rename(path, candidate)
            new_path = candidate

    try:
        tags = ID3(new_path)
        has_cover = bool(tags.getall("APIC"))
    except Exception:
        has_cover = False

    if not has_cover and (title or artist):
        time.sleep(clt.ITUNES_DELAY_SEC)
        img_bytes, _ = clt.itunes_lookup(artist, title)
        if img_bytes:
            try:
                t = ID3(new_path)
                t.delall("APIC")
                t.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=img_bytes))
                t.save()
            except Exception as e:
                print(f"    cover non embarquee : {e}")

    return new_path


def to_wsl_path(windows_or_wsl_path):
    return windows_or_wsl_path.replace("\\", "/").replace("C:", "/mnt/c")


def process_file(path, existing_metadata):
    print(f"[TAGS] {os.path.basename(path)}")
    cleaned_path = clean_tags_and_filename(path)

    print(f"[ANALYSE] {os.path.basename(cleaned_path)}")
    result = analyze_essentia.analyze(cleaned_path)

    (rms_lo, rms_hi), (bpm_lo, bpm_hi) = energy_bounds(existing_metadata)
    norm_rms = norm_clip(result["rms"], rms_lo, rms_hi)
    norm_bpm = norm_clip(result["bpm"], bpm_lo, bpm_hi)
    energy = 0.5 * norm_rms + 0.3 * norm_bpm + 0.2 * result["mood"]["party"]

    slot = classify_slot(energy)
    dest_dir = SLOT_FOLDERS[slot]
    dest_path = os.path.join(dest_dir, os.path.basename(cleaned_path))
    shutil.move(cleaned_path, dest_path)

    result["path"] = dest_path
    print(
        f"[OK] -> {slot} (energie={energy:.2f} bpm={result['bpm']:.0f} "
        f"genre={result['genres'][0][0]})"
    )
    return result


def main():
    os.makedirs(FAILED, exist_ok=True)
    files = [
        os.path.join(INCOMING, f)
        for f in sorted(os.listdir(INCOMING))
        if f.lower().endswith(".mp3") and os.path.isfile(os.path.join(INCOMING, f))
    ]
    if not files:
        print("Aucun fichier a traiter dans _incoming.")
        return

    print(f"{len(files)} fichier(s) a traiter.\n")
    metadata = load_metadata()
    ok_count = 0

    for path in files:
        try:
            result = process_file(path, metadata)
            metadata.append(result)
            save_metadata(metadata)
            ok_count += 1
        except Exception as e:
            print(f"[ERREUR] {os.path.basename(path)}: {e}")
            try:
                shutil.move(path, os.path.join(FAILED, os.path.basename(path)))
            except Exception:
                pass

    print(f"\n{ok_count}/{len(files)} morceaux integres.")

    if ok_count:
        print("\nRegeneration de New_prog...")
        cmd = (
            'cmd.exe /c "cd /d "C:\\Users\\ph.dufourcq\\Documents\\0_Claude Code\\3_Radiofm\\tools" '
            '&& python build_rotation.py && python export_rotation.py"'
        )
        subprocess.run(cmd, shell=True, check=False)


if __name__ == "__main__":
    main()
