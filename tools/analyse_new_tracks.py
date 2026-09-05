#!/usr/bin/env python3
"""Filtre d'ANALYSE : juger les morceaux classes, puis mettre en ligne ce qui passe.

Seconde moitie du pipeline d'ingestion, separee du triage le 2026-09-05. La
repartition est nette :

    triage_new_tracks.py   CLASSE  — tags, doublons, Essentia, le bon bac.
                                     Ne juge rien, n'envoie rien.
    analyse_new_tracks.py  JUGE    — trop energique ? trop repetitif ? trop
                                     loin de la house ? — puis ENVOIE sur
                                     AzuraCast ce qui a passe le verdict.

POURQUOI L'ENVOI EST ICI ET PAS DANS LE TRIAGE : un morceau qui part sur le
serveur peut passer a l'antenne dans les minutes qui suivent. Si le triage
envoyait tout, un titre juge trop dur le lendemain aurait deja tourne. En
gardant l'envoi de ce cote du verdict, RIEN n'atteint la radio sans avoir ete
note — c'est la seule garantie qui compte.

AUCUNE RE-ANALYSE : les descripteurs Essentia sont deja dans metadata.json,
ecrits par le triage. Ce script relit des nombres, il ne touche pas au signal
audio — donc pas de venv WSL, pas de modeles a charger, quelques secondes.

TROIS SORTS POSSIBLES (memes verdicts que track_gate.py / review_energy.py,
meme formule de score — elle vit dans track_gate.py et nulle part ailleurs) :

    keep     -> envoye sur AzuraCast.
    review   -> envoye AUSSI, mais signale : a ecouter a l'occasion. Avec
                --strict, il est mis de cote comme un reject.
    reject   -> range dans New_prog/_a_revoir/ avec le motif du verdict,
                RETIRE de metadata.json (l'y laisser fausserait la calibration
                des percentiles, qui doit decrire ce qui PASSE a l'antenne) et
                jamais envoye. Rien n'est supprime : le mp3 attend une ecoute.

DRY-RUN PAR DEFAUT, comme sync_library.py et review_energy.py : sans --apply,
le script affiche les verdicts et ecrit le rapport HTML sans rien deplacer ni
envoyer. analyse.bat enchaine les deux (rapport, puis confirmation).

Usage :
    python analyse_new_tracks.py                 # verdicts seuls (dry-run)
    python analyse_new_tracks.py --apply         # applique et met en ligne
    python analyse_new_tracks.py --apply --strict  # ecarte aussi les "a ecouter"
    python analyse_new_tracks.py --requeue FICHIER.mp3   # remet un titre en file
"""
import argparse
import html
import json
import os
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)

import azuracast_upload  # noqa: E402  (files d'attente + envoi, partages avec le triage)
import track_gate  # noqa: E402  (source de verite unique de la formule de score)

METADATA_PATH = os.path.join(TOOLS_DIR, "metadata.json")
REPORT_PATH = os.path.join(TOOLS_DIR, "analyse_report.html")

NEW_PROG = os.getenv("KALBASS_NEW_PROG",
                     r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog")
INCOMING = r"C:\Users\ph.dufourcq\Music\00_AZURACAST\_incoming"
# Purgatoire : ni un bac de rotation, ni la poubelle. Le motif de chaque
# verdict est journalise a cote, pour pouvoir trancher sans relancer l'analyse.
HOLD_FOLDER = os.path.join(NEW_PROG, "_a_revoir")
HOLD_LOG = os.path.join(HOLD_FOLDER, "_verdicts.txt")

LOCAL = azuracast_upload.to_current_platform


# --------------------------------------------------------------------------- metadata

def load_metadata():
    if os.path.exists(METADATA_PATH):
        with open(METADATA_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    return []


def save_metadata(rows):
    with open(METADATA_PATH, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)


def key_of(path):
    """Cle de rapprochement file d'attente <-> metadata.json.

    Le nom de fichier seul : le triage ecrit des chemins Windows, mais un
    morceau range a la main dans un autre bac garderait son nom. Comparer les
    chemins entiers ferait perdre sa trace a chaque deplacement -- exactement
    le bug corrige dans review_energy.py (commit 31f5e1a).
    """
    return os.path.basename((path or "").replace("\\", "/")).lower()


# --------------------------------------------------------------------------- verdicts

def judge(queue, metadata, ref, strict):
    """Note chaque morceau en attente. Retourne (rows, introuvables).

    `rows` : [{slot, path, record, verdict, score, reasons, held}] dans
    l'ordre de la file. `held` dit si le morceau est mis de cote (reject, ou
    review en mode strict) plutot qu'envoye.
    """
    by_key = {key_of(r.get("path")): r for r in metadata}
    rows, orphans = [], []
    for entry in queue:
        record = by_key.get(key_of(entry.get("path")))
        if record is None:
            # Plus dans metadata.json : sorti a la main entre les deux etapes.
            orphans.append(entry)
            continue
        verdict = track_gate.audit_descriptors(record, ref)
        held = verdict["verdict"] == "reject" or (strict and verdict["verdict"] == "review")
        rows.append({
            "slot": entry.get("slot"),
            "path": record.get("path") or entry.get("path"),
            "record": record,
            "verdict": verdict["verdict"],
            "score": verdict["score"],
            "reasons": verdict["reasons"],
            "held": held,
        })
    return rows, orphans


def hold(row, metadata):
    """Range un morceau ecarte dans _a_revoir/, journalise le motif, sort de metadata."""
    src = LOCAL(row["path"])
    os.makedirs(LOCAL(HOLD_FOLDER), exist_ok=True)
    dest = os.path.join(LOCAL(HOLD_FOLDER), os.path.basename(src))
    base, ext = os.path.splitext(dest)
    i = 2
    while os.path.exists(dest):
        dest = f"{base}_{i}{ext}"
        i += 1
    if os.path.exists(src):
        shutil.move(src, dest)
    else:
        print(f"  [ATTENTION] fichier introuvable, deplacement saute : {src}")
    with open(LOCAL(HOLD_LOG), "a", encoding="utf-8") as fh:
        fh.write(f"{os.path.basename(dest)}\t{row['verdict']}\t{row['score']}\t"
                 f"{', '.join(row['reasons']) or '-'}\n")
    # Retire de metadata.json : la reference des percentiles ne doit decrire
    # que ce qui passe a l'antenne (cf. track_gate.py refresh).
    wanted = key_of(row["path"])
    return [r for r in metadata if key_of(r.get("path")) != wanted]


# --------------------------------------------------------------------------- rapport

def render_report(rows, orphans, applied, uploaded, failures):
    held = [r for r in rows if r["held"]]
    passed = [r for r in rows if not r["held"]]
    review = [r for r in passed if r["verdict"] == "review"]

    def table(items, extra=""):
        return "".join(
            f"<tr><td>{html.escape(os.path.basename(r['path']))}</td>"
            f"<td>{html.escape(r['slot'] or '?')}</td>"
            f"<td>{r['verdict']}</td><td>{r['score']}</td>"
            f"<td>{html.escape(', '.join(r['reasons']) or '-')}</td></tr>"
            for r in items
        ) or f'<tr><td colspan="5">aucun{extra}</td></tr>'

    mode = "APPLIQUE" if applied else "SIMULATION — rien n'a ete deplace ni envoye"
    doc = f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>KALBASSFM - Analyse</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#111318; color:#e8e8e8; padding:24px; }}
  h1 {{ margin:0 0 4px; font-size:20px; }}
  .status {{ font-size:15px; margin-bottom:16px; color:{"#4caf50" if applied else "#e0b23c"}; }}
  table {{ border-collapse: collapse; font-size:12px; margin-bottom:12px; }}
  td, th {{ border:1px solid #2a2d34; padding:3px 8px; text-align:left; }}
  th {{ background:#1c1f26; }}
  h3 {{ font-size:14px; margin:18px 0 4px; }}
</style></head>
<body>
<h1>KALBASSFM - Analyse des nouveaux morceaux</h1>
<div class="status">{mode}</div>
<p>Juges : {len(rows)} | Ecartes : {len(held)} | A ecouter : {len(review)} |
   Envoyes : {uploaded} | Echecs envoi : {len(failures)} | Orphelins : {len(orphans)}</p>

<h3>Ecartes &mdash; New_prog/_a_revoir/ ({len(held)})</h3>
<table><tr><th>Fichier</th><th>Bac</th><th>Verdict</th><th>Score</th><th>Motif</th></tr>{table(held)}</table>

<h3>A ecouter, mais en ligne ({len(review)})</h3>
<table><tr><th>Fichier</th><th>Bac</th><th>Verdict</th><th>Score</th><th>Motif</th></tr>{table(review)}</table>

<h3>Passes sans reserve ({len(passed) - len(review)})</h3>
<table><tr><th>Fichier</th><th>Bac</th><th>Verdict</th><th>Score</th><th>Motif</th></tr>{table([r for r in passed if r['verdict'] != 'review'])}</table>
</body></html>"""
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write(doc)


def open_in_browser():
    win = azuracast_upload.to_windows(REPORT_PATH)
    if sys.platform.startswith("win"):
        os.startfile(win)  # noqa: S606
    else:
        subprocess.run(f'cmd.exe /c start "" "{win}"', shell=True, check=False)


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="deplacer et envoyer reellement (sinon simulation)")
    ap.add_argument("--strict", action="store_true",
                    help='mettre aussi de cote les "a ecouter" (review)')
    ap.add_argument("--requeue", metavar="FICHIER",
                    help="remet un morceau de _a_revoir/ dans la file d'attente")
    args = ap.parse_args()

    if args.requeue:
        return requeue(args.requeue)

    queue = azuracast_upload.load_pending_review()
    if not queue:
        print("Aucun morceau en attente de verdict — lance triage.bat d'abord.")
        return

    ref = track_gate.load_reference()
    metadata = load_metadata()
    print(f"{len(queue)} morceau(x) a juger — seuils : review >= "
          f"{ref['verdict']['review']}, reject >= {ref['verdict']['reject']}"
          f"{' (mode strict)' if args.strict else ''}\n")

    rows, orphans = judge(queue, metadata, ref, args.strict)
    for entry in orphans:
        print(f"[ORPHELIN] {os.path.basename(entry.get('path', '?'))} — plus dans "
              f"metadata.json, retire de la file.")

    for row in rows:
        motif = ", ".join(row["reasons"]) or "score global"
        marque = "ECARTE " if row["held"] else ("a ecouter" if row["verdict"] == "review" else "ok      ")
        print(f"[{marque}] {row['score']:.3f}  {os.path.basename(row['path'])}  ({motif})")

    held = [r for r in rows if r["held"]]
    passed = [r for r in rows if not r["held"]]
    print(f"\n{len(passed)} a envoyer, {len(held)} a mettre de cote.")

    if not args.apply:
        render_report(rows, orphans, False, 0, [])
        print(f"\nSIMULATION — rien n'a bouge. Rapport : {REPORT_PATH}")
        print("Relance avec --apply pour appliquer et mettre en ligne.")
        open_in_browser()
        return

    # ── Mise de cote ─────────────────────────────────────────────────────────
    for row in held:
        print(f"[ECARTE] -> _a_revoir : {os.path.basename(row['path'])}")
        metadata = hold(row, metadata)
    if held:
        save_metadata(metadata)

    # ── Envoi AzuraCast ──────────────────────────────────────────────────────
    uploaded, failures = 0, []
    still_queued = []
    print("\nConnexion SFTP AzuraCast...")
    transport, sftp = azuracast_upload.open_sftp()
    if sftp is None:
        # Rien n'est perdu : les morceaux juges bons restent en file et
        # repasseront au prochain run. Les ecartes, eux, sont deja ranges.
        still_queued = [{"slot": r["slot"], "path": r["path"]} for r in passed]
        print(f"SFTP indisponible — {len(still_queued)} morceau(x) restent en "
              f"attente d'envoi, relance ce script quand la connexion revient.")
        pending = azuracast_upload.load_pending_uploads()
    else:
        pending = azuracast_upload.retry_pending_uploads(sftp)
        try:
            for row in passed:
                name = os.path.basename(row["path"])
                try:
                    print(f"[SFTP] Envoi -> /{row['slot']}/{name}")
                    azuracast_upload.upload(sftp, row["slot"], row["path"])
                    uploaded += 1
                except azuracast_upload.RemoteAlreadyExists:
                    print(f"[SFTP] Deja sur le serveur, ignore : {name}")
                    uploaded += 1
                except Exception as e:
                    print(f"[SFTP] Echec envoi {name}: {e}")
                    failures.append((name, str(e)))
                    pending.append({"slot": row["slot"], "path": row["path"]})
        finally:
            sftp.close()
            transport.close()

    azuracast_upload.save_pending_uploads(pending)
    azuracast_upload.save_pending_review(still_queued)
    render_report(rows, orphans, True, uploaded, failures)

    print(f"\n{uploaded} morceau(x) en ligne, {len(held)} ecarte(s), "
          f"{len(pending)} en attente d'envoi.")

    # ── Table BPM du chat live ───────────────────────────────────────────────
    # metadata.json a pu changer (morceaux ecartes) : api/bpm-table.json doit
    # suivre, le jeu "devine le BPM" ne repondant que sur ce qu'il y trouve.
    # C'est ici, en FIN de pipeline, que metadata atteint son etat definitif --
    # la regenerer des le triage aurait embarque des morceaux qu'un verdict
    # retire ensuite.
    if uploaded or held:
        print("\n=== Mise a jour de la table BPM (jeu chat live) ===")
        try:
            import export_bpm_table
            written = export_bpm_table.main()
        except Exception as e:
            written = False
            print(f"[ERREUR] regeneration de la table BPM impossible : {e}")
            print("  -> relancer a la main : python tools/export_bpm_table.py")
        if written:
            print("\n>>> A FAIRE : commit + push de api/bpm-table.json.\n"
                  "    Sans push, le jeu BPM reste muet en ligne sur ces morceaux.")


def requeue(name):
    """Renvoie dans _incoming/ un morceau ecarte a tort, pour un second passage.

    Utile apres un `track_gate.py refresh` qui a deplace les seuils : le titre
    juge trop dur hier peut passer aujourd'hui. Le retour se fait par
    _incoming/ et non par son bac, parce que le hold l'a sorti de
    metadata.json : seul le triage sait recalculer ses descripteurs. C'est
    aussi lui qui lui redonnera un bac -- celui d'origine n'est plus connu une
    fois la ligne de _verdicts.txt ecrite.
    """
    src = os.path.join(LOCAL(HOLD_FOLDER), os.path.basename(name))
    if not os.path.exists(src):
        sys.exit(f"{os.path.basename(name)} introuvable dans {LOCAL(HOLD_FOLDER)}.")
    dest_dir = LOCAL(INCOMING)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(src))
    if os.path.exists(dest):
        sys.exit(f"{os.path.basename(dest)} est deja dans _incoming/ — rien a faire.")
    shutil.move(src, dest)
    print(f"{os.path.basename(dest)} -> _incoming/")
    print("Relance triage.bat : il le re-analysera, lui redonnera un bac et le "
          "remettra en file d'attente de verdict.")


if __name__ == "__main__":
    main()
