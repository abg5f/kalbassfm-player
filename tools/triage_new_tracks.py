#!/usr/bin/env python3
"""
Pipeline d'integration des nouveaux telechargements deposes dans _incoming :

1. Nettoie les tags ID3 / nom de fichier / cover (reprend clean_local_tracks.py)
2. Detecte les doublons (artiste+titre normalises) contre ce qui existe deja
   dans New_prog -> deplace vers _incoming/_duplicates/ et ignore
3. Analyse Essentia (energie, bpm, genre, mood, danceability)
4. Classe le morceau dans un des 9 BACS de la grille (classify_bins.py :
   genre d'abord, energie ensuite, seuils auto-calibres)
5. Depose le fichier nettoye dans New_prog/<bac>/ sous son nom propre --
   PAS de prefixe d'ordre : l'ordonnancement est le travail d'AzuraCast
   (rotation continue ponderee, cf. tools/apply_rotation.py). Seuls les
   nouveaux morceaux ont besoin d'etre envoyes sur AzuraCast -- mais pas
   par ce script (cf. etape 7).
6. Ajoute le resultat a metadata.json
7. Inscrit le lot dans pending_review.json -- ET S'ARRETE LA. Ce script
   CLASSE, il ne juge pas : depuis la separation du 2026-09-05, c'est
   analyse_new_tracks.py (analyse.bat) qui dit si un morceau est trop
   energique / trop repetitif / trop loin de la house, puis envoie sur
   AzuraCast ce qui passe. Tant qu'il n'a pas tourne, RIEN n'est en ligne.

La table api/bpm-table.json (jeu "devine le BPM" du chat live) n'est PLUS
regeneree ici : elle doit rester alignee sur metadata.json, or un verdict de
l'analyse peut encore en retirer un morceau -- et le jeu repond UNIQUEMENT
sur les morceaux qu'il y trouve. C'est donc analyse_new_tracks.py, en fin de
pipeline, qui la regenere et rappelle de la commiter/pusher.

Les fichiers illisibles/en erreur sont deplaces dans _incoming/_failed/ et
n'interrompent pas le traitement des autres.

Ouvre automatiquement triage_report.html dans le navigateur (auto-refresh
2s) pour suivre l'avancement en direct : morceaux traites, repartition par
bac, doublons ignores, echecs.

A executer dans le venv WSL (~/essentia-env), ou via triage.bat :
    source ~/essentia-env/bin/activate
    python3 "/mnt/c/Users/ph.dufourcq/Documents/0_Claude Code/3_Radiofm/tools/triage_new_tracks.py"
"""
import os
import re
import sys
import json
import html
import shutil
import subprocess
import time as time_module

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)

import analyze_essentia  # noqa: E402  (modeles Essentia charges a l'import)
import clean_local_tracks as clt  # noqa: E402  (fonctions clean() / itunes_lookup())
from classify_bins import (  # noqa: E402  (source de verite unique de la grille)
    NEW_BINS, top_genre, compute_energies, compute_cutoffs, classify_bin,
)
import azuracast_upload  # noqa: E402  (files d'attente + envoi, partages avec l'analyse)

INCOMING = r"C:\Users\ph.dufourcq\Music\00_AZURACAST\_incoming".replace("\\", "/").replace("C:", "/mnt/c")
FAILED = os.path.join(INCOMING, "_failed")
DUPLICATES = os.path.join(INCOMING, "_duplicates")

# Score de similarite artiste+titre (0-1) au-dela duquel un morceau est
# considere comme un doublon d'un morceau deja present dans New_prog.
DUPLICATE_THRESHOLD = 0.75

NEW_PROG_WSL = "/mnt/c/Users/ph.dufourcq/Music/00_AZURACAST/New_prog"
SLOT_FOLDERS = {b: f"{NEW_PROG_WSL}/{b}" for b in NEW_BINS}

METADATA_PATH = os.path.join(TOOLS_DIR, "metadata.json")
REPORT_PATH = os.path.join(TOOLS_DIR, "triage_report.html")
def wsl_to_windows(path):
    return path.replace("/mnt/c", "C:").replace("/", "\\")


class Report:
    """Genere/rafraichit un rapport HTML de suivi (triage_report.html)."""

    def __init__(self, total):
        self.total = total
        self.start = time_module.time()
        self.slots = {s: [] for s in SLOT_FOLDERS}
        self.duplicates = []
        self.failures = []
        self.awaiting = 0
        self.done = 0

    def add_success(self, slot, artist, title, bpm, genre, energy):
        self.slots[slot].append((artist or "?", title or "?", bpm, genre, energy))
        self.done += 1
        self.render()

    def add_duplicate(self, filename, match):
        self.duplicates.append((filename, os.path.basename(match)))
        self.done += 1
        self.render()

    def add_failure(self, filename, error):
        self.failures.append((filename, str(error)))
        self.done += 1
        self.render()

    def set_awaiting(self, count):
        """Morceaux classes en attente du verdict d'analyse — pas encore en ligne."""
        self.awaiting = count
        self.render()

    def render(self, finished=False):
        elapsed = time_module.time() - self.start
        max_count = max([len(v) for v in self.slots.values()] + [1])
        pct = int(100 * self.done / self.total) if self.total else 100

        slot_blocks = ""
        for slot, tracks in self.slots.items():
            bar_width = int(240 * len(tracks) / max_count) if max_count else 0
            track_rows = "".join(
                f"<tr><td>{html.escape(a)}</td><td>{html.escape(t)}</td>"
                f"<td>{bpm:.0f}</td><td>{html.escape(g)}</td><td>{e:.2f}</td></tr>"
                for a, t, bpm, g, e in tracks
            )
            slot_blocks += f"""
<div class="slot">
  <div class="slot-header"><span>{slot}</span><span>{len(tracks)}</span></div>
  <div class="bar"><div class="bar-fill" style="width:{bar_width}px"></div></div>
  <table><tr><th>Artiste</th><th>Titre</th><th>BPM</th><th>Genre</th><th>Energie</th></tr>{track_rows}</table>
</div>"""

        dup_rows = "".join(
            f"<tr><td>{html.escape(f)}</td><td>{html.escape(m)}</td></tr>" for f, m in self.duplicates
        )
        fail_rows = "".join(
            f"<tr><td>{html.escape(f)}</td><td>{html.escape(e)}</td></tr>" for f, e in self.failures
        )

        status_label = "Termine" if finished else "En cours..."
        refresh_tag = "" if finished else '<meta http-equiv="refresh" content="2">'

        doc = f"""<!doctype html>
<html><head><meta charset="utf-8">{refresh_tag}
<title>KALBASSFM - Triage</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#111318; color:#e8e8e8; padding:24px; }}
  h1 {{ margin:0 0 4px; font-size:20px; }}
  .status {{ font-size:15px; margin-bottom:4px; color:{"#4caf50" if finished else "#e0b23c"}; }}
  .progress {{ background:#222; border-radius:6px; overflow:hidden; height:10px; width:100%; max-width:480px; margin-bottom:20px; }}
  .progress-fill {{ background:#4caf50; height:100%; width:{pct}%; transition: width .3s; }}
  .slot {{ margin-bottom:22px; }}
  .slot-header {{ display:flex; justify-content:space-between; max-width:480px; font-weight:600; margin-bottom:4px; }}
  .bar {{ background:#222; border-radius:4px; overflow:hidden; height:12px; margin-bottom:8px; }}
  .bar-fill {{ background:#5b8def; height:100%; }}
  table {{ border-collapse: collapse; font-size:12px; margin-bottom:4px; }}
  td, th {{ border:1px solid #2a2d34; padding:3px 8px; text-align:left; }}
  th {{ background:#1c1f26; }}
  h3 {{ font-size:14px; margin:18px 0 4px; }}
</style></head>
<body>
<h1>KALBASSFM - Triage des nouveaux morceaux</h1>
<div class="status">{status_label} — {self.done}/{self.total} traites — {elapsed:.0f}s</div>
<div class="progress"><div class="progress-fill"></div></div>
<p>Doublons ignores : {len(self.duplicates)} | Echecs : {len(self.failures)} | En attente du verdict d'analyse : {self.awaiting}</p>
{slot_blocks}
<h3>Doublons ignores ({len(self.duplicates)})</h3>
<table><tr><th>Fichier</th><th>Correspond a</th></tr>{dup_rows}</table>
<h3>Echecs classement ({len(self.failures)})</h3>
<table><tr><th>Fichier</th><th>Erreur</th></tr>{fail_rows}</table>
</body></html>"""
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(doc)

    def open_in_browser(self):
        win_path = wsl_to_windows(REPORT_PATH)
        subprocess.run(f'cmd.exe /c start "" "{win_path}"', shell=True, check=False)


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


def unique_target(folder, name):
    """Evite d'ecraser un fichier existant (doublon de nom) : suffixe _2, _3..."""
    base, ext = os.path.splitext(name)
    candidate = os.path.join(folder, name)
    i = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base}_{i}{ext}")
        i += 1
    return candidate


_ART_TOOLS = []  # cache : [] = pas encore teste, [None] = indisponible


def _artwork_tools():
    """fix_artwork.py si Pillow est installe dans l'environnement, sinon None.

    Le triage tourne dans le venv WSL Essentia, ou Pillow n'est pas garanti :
    l'absence degrade la detection, elle ne casse pas le pipeline.
    """
    if not _ART_TOOLS:
        try:
            import fix_artwork
            _ART_TOOLS.append(fix_artwork)
        except Exception as e:
            print(f"    [info] detection des logos de site desactivee ({e})")
            _ART_TOOLS.append(None)
    return _ART_TOOLS[0]


def is_site_logo(img_bytes):
    """True si la cover embarquee est une banniere de site connue."""
    fa = _artwork_tools()
    if not fa:
        return False
    try:
        import io
        from PIL import Image
        return fa.dhash(Image.open(io.BytesIO(img_bytes))) in fa.load_blocklist()
    except Exception:
        return False


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

    # Une cover presente ne veut pas dire une cover valable : les sites de
    # telechargement (heydj.pro, ClapCrate.com...) embarquent leur banniere.
    # bad_art_hashes.txt liste leurs empreintes, alimente par fix_artwork.py.
    try:
        tags = ID3(new_path)
        apics = tags.getall("APIC")
        has_cover = bool(apics)
        if has_cover and is_site_logo(apics[0].data):
            print("    cover = logo de site -> remplacement")
            has_cover = False
    except Exception:
        has_cover = False

    if not has_cover and (title or artist):
        time.sleep(clt.ITUNES_DELAY_SEC)
        img_bytes, _ = clt.itunes_lookup(artist, title)
        if not img_bytes and _artwork_tools():
            img_bytes, _ = _artwork_tools().lookup_deezer(artist, title)
        if img_bytes:
            try:
                t = ID3(new_path)
                t.delall("APIC")
                t.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=img_bytes))
                t.save()
            except Exception as e:
                print(f"    cover non embarquee : {e}")

    return new_path, artist, title


def sym_overlap(a, b):
    if not a or not b:
        return 0.0
    return (clt.overlap(a, b) + clt.overlap(b, a)) / 2


def build_duplicate_index():
    """Scanne New_prog et retourne [(tokens_artiste, tokens_titre, chemin), ...]."""
    from mutagen import File as MFile

    index = []
    for folder in SLOT_FOLDERS.values():
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if not fname.lower().endswith(".mp3"):
                continue
            path = os.path.join(folder, fname)
            try:
                audio = MFile(path, easy=True)
                artist = (audio.tags.get("artist") or [""])[0] if audio and audio.tags else ""
                title = (audio.tags.get("title") or [""])[0] if audio and audio.tags else ""
            except Exception:
                artist, title = "", ""
            index.append((clt.tokens(artist), clt.tokens(title), path))
    return index


def find_duplicate(artist, title, index):
    a_tokens, t_tokens = clt.tokens(artist), clt.tokens(title)
    if not a_tokens and not t_tokens:
        return None
    best_path, best_score = None, 0.0
    for cand_a, cand_t, path in index:
        score = (sym_overlap(a_tokens, cand_a) + sym_overlap(t_tokens, cand_t)) / 2
        if score > best_score:
            best_score, best_path = score, path
    return best_path if best_score >= DUPLICATE_THRESHOLD else None


def process_file(path, existing_metadata, cutoffs, dup_index, report):
    print(f"[TAGS] {os.path.basename(path)}")
    cleaned_path, artist, title = clean_tags_and_filename(path)

    dup_path = find_duplicate(artist, title, dup_index)
    if dup_path:
        print(f"[DOUBLON] {os.path.basename(cleaned_path)} ~ {os.path.basename(dup_path)} -> ignore")
        os.makedirs(DUPLICATES, exist_ok=True)
        dest = os.path.join(DUPLICATES, os.path.basename(cleaned_path))
        shutil.move(cleaned_path, dest)
        report.add_duplicate(os.path.basename(dest), dup_path)
        return None

    print(f"[ANALYSE] {os.path.basename(cleaned_path)}")
    result = analyze_essentia.analyze(cleaned_path)

    (rms_lo, rms_hi), (bpm_lo, bpm_hi) = energy_bounds(existing_metadata)
    norm_rms = norm_clip(result["rms"], rms_lo, rms_hi)
    norm_bpm = norm_clip(result["bpm"], bpm_lo, bpm_hi)
    energy = 0.5 * norm_rms + 0.3 * norm_bpm + 0.2 * result["mood"]["party"]

    slot = classify_bin(top_genre(result["genres"]), energy, result["mood"], cutoffs, result["bpm"])
    dest_dir = SLOT_FOLDERS[slot]
    os.makedirs(dest_dir, exist_ok=True)
    # Nom propre, sans prefixe d'ordre : l'ordonnancement est delegue a AzuraCast.
    dest_path = unique_target(dest_dir, os.path.basename(cleaned_path))
    shutil.move(cleaned_path, dest_path)

    # Stocke le chemin au format Windows dans metadata.json : coherent avec
    # analyze_essentia.py et migrate_grid.py, evite les doublons causes par
    # un melange de formats WSL (/mnt/c/...) et Windows (C:\...) dans le JSON.
    result["path"] = wsl_to_windows(dest_path)
    print(
        f"[OK] -> {slot} (energie={energy:.2f} bpm={result['bpm']:.0f} "
        f"genre={result['genres'][0][0]})"
    )
    dup_index.append((clt.tokens(artist), clt.tokens(title), dest_path))
    report.add_success(slot, artist, title, result["bpm"], result["genres"][0][0], energy)

    # Aucun envoi SFTP dans ce script : le morceau est classe, il attend son
    # verdict. C'est analyse_new_tracks.py qui l'enverra — ou le mettra de cote.
    return result, slot, dest_path


def main():
    # Pas d'argparse : ce script est lance par triage.bat sans argument. Les
    # anciens drapeaux --no-gate / --gate-strict n'ont plus cours ici, le
    # verdict d'antenne ayant demenage dans analyse_new_tracks.py.
    os.makedirs(FAILED, exist_ok=True)
    files = [
        os.path.join(INCOMING, f)
        for f in sorted(os.listdir(INCOMING))
        if f.lower().endswith(".mp3") and os.path.isfile(os.path.join(INCOMING, f))
    ]
    if not files:
        print("Aucun fichier a traiter dans _incoming.")
        waiting = azuracast_upload.load_pending_review()
        if waiting:
            print(f"{len(waiting)} morceau(x) attendent leur verdict "
                  f"-> lance analyse.bat pour les juger et les mettre en ligne.")
        return

    print(f"{len(files)} fichier(s) a traiter.")
    print("Indexation de New_prog pour la detection de doublons...")
    dup_index = build_duplicate_index()
    print(f"  -> {len(dup_index)} morceaux existants indexes.")

    metadata = load_metadata()
    # Seuils de classification auto-calibres sur la bibliotheque existante
    # (percentiles par famille de genre, cf. classify_bins.py).
    cutoffs = compute_cutoffs(metadata, compute_energies(metadata))
    report = Report(len(files))
    report.render()
    report.open_in_browser()

    # -- Classement local, et rien d'autre -----------------------------------
    # Lancement toujours manuel (pas de cron) : on ecoute les morceaux bruts
    # dans _incoming avant de declencher ce script. Ce qui en sort est range
    # dans le bon bac ET inscrit dans metadata.json, mais n'est PAS en ligne :
    # aucune connexion SFTP n'est ouverte de tout le run.
    ok_count = 0
    dup_count = 0
    newly_classified = []  # [{"slot":..., "path":...}] -> file d'attente du verdict

    for path in files:
        try:
            outcome = process_file(path, metadata, cutoffs, dup_index, report)
            if outcome is None:
                dup_count += 1
                continue
            result, slot, dest_path = outcome
            metadata.append(result)
            save_metadata(metadata)
            newly_classified.append(
                {"slot": slot, "path": azuracast_upload.to_windows(dest_path)}
            )
            ok_count += 1
            report.set_awaiting(len(newly_classified))
        except Exception as e:
            print(f"[ERREUR] {os.path.basename(path)}: {e}")
            report.add_failure(os.path.basename(path), e)
            try:
                shutil.move(path, os.path.join(FAILED, os.path.basename(path)))
            except Exception:
                pass

    print(f"{ok_count}/{len(files)} morceaux classes localement, "
          f"{dup_count} doublon(s) ignore(s).")

    # -- Passage de relais a l'analyse ---------------------------------------
    # On FUSIONNE avec la file existante au lieu de l'ecraser : deux triages
    # d'affilee sans analyse entre les deux ne doivent pas faire disparaitre le
    # premier lot. Il serait alors local, absent du serveur, et sync_library.py
    # proposerait de l'ecarter (cas A) alors qu'il attend simplement son tour.
    queue = azuracast_upload.load_pending_review()
    known = {e["path"] for e in queue}
    queue.extend(e for e in newly_classified if e["path"] not in known)
    azuracast_upload.save_pending_review(queue)
    report.render(finished=True)

    if queue:
        print(f"{len(queue)} morceau(x) en attente de verdict "
              f"({os.path.basename(azuracast_upload.PENDING_REVIEW_PATH)}).")
        print(">>> ETAPE SUIVANTE : analyse.bat — juge (trop energique ? trop")
        print("    repetitif ? trop loin de la house ?), envoie sur AzuraCast ce")
        print("    qui passe, regenere la table BPM du chat live.")
        print("    Tant qu'il n'a pas tourne, ces morceaux ne sont PAS a l'antenne.")


if __name__ == "__main__":
    main()
