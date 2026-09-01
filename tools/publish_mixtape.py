#!/usr/bin/env python3
"""
Mixtape mensuelle : programmation à l'antenne + publication en podcast.

Le geste mensuel, en une commande. La banque de mixtapes vit dans le dossier
`Mixtapes/` du média AzuraCast (déposée en SFTP, comme le reste) ; ce script en
pioche une, la met à la programmation et la publie sur le flux RSS.

Deux stockages distincts, c'est voulu et inévitable :
  - média station (`Mixtapes/`)  -> ce que l'AutoDJ diffuse à l'antenne
  - stockage podcast             -> ce que le flux RSS sert en téléchargement
`playlist_media_id` est en lecture seule côté API AzuraCast (champ "never") : un
épisode ne peut pas *référencer* un média station, il faut lui en donner un.
Le script réutilise donc le fichier local si on le lui passe (`--local`), sinon
il retélécharge depuis le serveur.

Usage :
    python publish_mixtape.py                     # liste la banque, ne fait rien
    python publish_mixtape.py --pick 3 \
        --date 2026-09-05 --start 20:00 \
        --title "Sunset Session" \
        --local "C:\\...\\sunset.mp3"              # dry-run détaillé
    python publish_mixtape.py --pick 3 ... --apply # exécute

Options utiles :
    --file <nom>    choisir par nom de fichier plutôt que par numéro
    --end HH:MM     fin de fenêtre explicite (par défaut : début + durée + 10 min)
    --desc "..."    description de l'épisode
"""
import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from azuracast_config import AZURACAST_API_KEY  # noqa: E402

BASE = "https://kalbassfm.duckdns.org"
STATION = "kalbassfm"
BANK_DIR = "Mixtapes"
PLAYLIST_NAME = "mixtape_onair"
PODCAST_TITLE = "KALBASSFM Mixtapes"

# Les playlists de la grille plafonnent à 15. Au-dessus, la mixtape gagne
# quasi certainement le premier tirage de sa fenêtre (cf. note sur l'heure
# exacte de démarrage en fin de script).
ONAIR_WEIGHT = 40

# Taille d'un morceau d'upload. Confortablement sous la limite nginx de
# l'instance (413 constaté sur un envoi d'un seul bloc de 149 Mo).
CHUNK_SIZE = 5 * 1024 * 1024


# --------------------------------------------------------------------------- API

def call(method, path, body=None):
    url = path if path.startswith("http") else f"{BASE}/api/station/{STATION}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-API-Key", AZURACAST_API_KEY)
    req.add_header("Accept", "application/json")
    # AzuraCast refuse les requêtes sans User-Agent crédible (anti-crawler).
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:600]


def upload_media(podcast_id, episode_id, filepath, progress=True):
    """Upload découpé en chunks (protocole Flow.js), comme l'interface AzuraCast.

    Envoyer le fichier en un seul corps multipart se heurte à la limite
    `client_max_body_size` de nginx : **HTTP 413** dès ~50 Mo, alors qu'une
    mixtape d'une heure en 320 kbps pèse ~150 Mo (constaté le 2026-08-08).
    L'endpoint attend un `requestBodies/FlowFileUpload` : les champs `flow*`
    accompagnent chaque morceau, et le serveur réassemble le fichier quand le
    dernier arrive. Seule la réponse au dernier chunk porte l'épisode complet.
    """
    filepath = Path(filepath)
    total = filepath.stat().st_size
    total_chunks = max(1, -(-total // CHUNK_SIZE))  # division entière par excès
    identifier = f"{total}-{uuid.uuid4().hex}"
    ctype = mimetypes.guess_type(filepath.name)[0] or "application/octet-stream"
    url = f"{BASE}/api/station/{STATION}/podcast/{podcast_id}/episode/{episode_id}/media"

    last = (0, None)
    with open(filepath, "rb") as fh:
        for n in range(1, total_chunks + 1):
            chunk = fh.read(CHUNK_SIZE)
            fields = {
                "flowChunkNumber": str(n),
                "flowChunkSize": str(CHUNK_SIZE),
                "flowCurrentChunkSize": str(len(chunk)),
                "flowTotalSize": str(total),
                "flowIdentifier": identifier,
                "flowFilename": filepath.name,
                "flowRelativePath": filepath.name,
                "flowTotalChunks": str(total_chunks),
            }
            boundary = uuid.uuid4().hex
            parts = []
            for key, value in fields.items():
                parts.append(f"--{boundary}\r\n"
                             f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                             f"{value}\r\n".encode())
            parts.append((f"--{boundary}\r\n"
                          f'Content-Disposition: form-data; name="file"; '
                          f'filename="{filepath.name}"\r\n'
                          f"Content-Type: {ctype}\r\n\r\n").encode())
            body = b"".join(parts) + chunk + f"\r\n--{boundary}--\r\n".encode()

            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("X-API-Key", AZURACAST_API_KEY)
            req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    last = (r.status, json.loads(r.read() or b"null"))
            except urllib.error.HTTPError as e:
                return e.code, (f"chunk {n}/{total_chunks} : "
                                f"{e.read().decode(errors='replace')[:600]}")
            if progress:
                print(f"\r    chunk {n}/{total_chunks}", end="", flush=True)
    if progress:
        print()
    return last


def die(msg):
    print(f"\n❌ {msg}")
    sys.exit(1)


# ------------------------------------------------------------------------ helpers

def hhmm(text):
    """'20:00' -> 2000, le format entier attendu par AzuraCast."""
    h, m = text.split(":")
    return int(h) * 100 + int(m)


def fmt_hhmm(value):
    return f"{value // 100:02d}:{value % 100:02d}"


def load_bank():
    st, files = call("GET", f"/files?searchPhrase={BANK_DIR}%2F&rowCount=500")
    if st != 200:
        die(f"Lecture de la bibliothèque impossible (HTTP {st}) : {files}")
    rows = files.get("rows", files) if isinstance(files, dict) else files
    bank = [f for f in rows if (f.get("path") or "").startswith(f"{BANK_DIR}/")]
    bank.sort(key=lambda f: f["path"])
    return bank


def resolve_targets():
    st, pls = call("GET", "/playlists")
    if st != 200:
        die(f"Lecture des playlists impossible (HTTP {st})")
    playlist = next((p for p in pls if p["name"] == PLAYLIST_NAME), None)
    if not playlist:
        die(f"Playlist « {PLAYLIST_NAME} » introuvable. La créer d'abord dans AzuraCast.")

    st, pods = call("GET", "/podcasts")
    if st != 200:
        die(f"Lecture des podcasts impossible (HTTP {st})")
    podcast = next((p for p in pods if p["title"] == PODCAST_TITLE), None)
    if not podcast:
        die(f"Podcast « {PODCAST_TITLE} » introuvable. Le créer d'abord dans AzuraCast.")
    if podcast.get("source") != "manual":
        die(f"Le podcast « {PODCAST_TITLE} » n'est pas en source « manual » "
            f"(actuellement : {podcast.get('source')}). `source` est immuable "
            f"après création : il faut recréer le podcast.")
    return playlist, podcast


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Programme et publie la mixtape du mois.")
    ap.add_argument("--pick", type=int, help="numéro dans la banque (voir la liste)")
    ap.add_argument("--file", help="nom de fichier dans Mixtapes/ (alternative à --pick)")
    ap.add_argument("--date", help="date de diffusion, AAAA-MM-JJ")
    ap.add_argument("--start", default="20:00", help="heure de début, HH:MM (défaut 20:00)")
    ap.add_argument("--end", help="heure de fin, HH:MM (défaut : début + durée + 10 min)")
    ap.add_argument("--title", help="titre de l'épisode (défaut : nom du fichier)")
    ap.add_argument("--desc", default="", help="description de l'épisode")
    ap.add_argument("--local", help="chemin local du MP3 (évite un retéléchargement)")
    ap.add_argument("--apply", action="store_true", help="exécute (sinon : dry-run)")
    args = ap.parse_args()

    playlist, podcast = resolve_targets()
    bank = load_bank()

    print(f"=== BANQUE {BANK_DIR}/ — {len(bank)} mixtape(s) ===")
    if not bank:
        print(f"  (vide — déposer les mixtapes dans {BANK_DIR}/ par SFTP, port 2022)")
        return
    for i, f in enumerate(bank, 1):
        print(f"  [{i:>2}] {Path(f['path']).name:<60} {f.get('length_text', '?'):>8}")

    # Sélection
    if args.pick is None and not args.file:
        print("\nRien de sélectionné. Relancer avec --pick <n> (ou --file <nom>), "
              "--date AAAA-MM-JJ.")
        return
    if args.file:
        chosen = next((f for f in bank if Path(f["path"]).name == args.file), None)
        if not chosen:
            die(f"« {args.file} » introuvable dans {BANK_DIR}/")
    else:
        if not 1 <= args.pick <= len(bank):
            die(f"--pick doit être entre 1 et {len(bank)}")
        chosen = bank[args.pick - 1]

    if not args.date:
        die("--date AAAA-MM-JJ est obligatoire pour programmer la diffusion.")
    try:
        air_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        die("--date doit être au format AAAA-MM-JJ")

    # Fenêtre de diffusion : la durée du fichier + une marge, sauf --end explicite.
    start_i = hhmm(args.start)
    if args.end:
        end_i = hhmm(args.end)
    else:
        secs = int(chosen.get("length") or 0)
        end_dt = (datetime.combine(air_date, datetime.min.time())
                  + timedelta(hours=start_i // 100, minutes=start_i % 100)
                  + timedelta(seconds=secs) + timedelta(minutes=10))
        end_i = end_dt.hour * 100 + end_dt.minute

    st, eps = call("GET", f"/podcast/{podcast['id']}/episodes")
    episode_no = (len(eps) if isinstance(eps, list) else 0) + 1
    title = args.title or Path(chosen["path"]).stem
    publish_at = int(datetime.combine(
        air_date, datetime.min.time()).timestamp()) + (start_i // 100) * 3600 \
        + (start_i % 100) * 60

    print(f"\n=== PLAN ===")
    print(f"  mixtape      : {Path(chosen['path']).name}")
    print(f"  durée        : {chosen.get('length_text', '?')}")
    print(f"  antenne      : {air_date} de {fmt_hhmm(start_i)} à {fmt_hhmm(end_i)}")
    print(f"  playlist     : {PLAYLIST_NAME} (id {playlist['id']}) — vidée puis regarnie, "
          f"activée, poids {ONAIR_WEIGHT}")
    print(f"  podcast      : {PODCAST_TITLE} — épisode #{episode_no} « {title} »")
    print(f"  publication  : {datetime.fromtimestamp(publish_at):%Y-%m-%d %H:%M}")
    src = args.local or "(retéléchargement depuis le serveur)"
    print(f"  média podcast: {src}")

    if not args.apply:
        print("\n(dry-run — rien n'a été modifié. Ajouter --apply pour exécuter.)")
        return

    print("\n=== EXÉCUTION ===")

    # 1. Playlist on-air : vider, garnir, planifier, activer.
    st, r = call("DELETE", f"/playlist/{playlist['id']}/empty")
    print(f"  playlist vidée                 -> HTTP {st}")
    if st != 200:
        die(f"Échec du vidage : {r}")

    media_id = chosen["id"]
    st, f = call("GET", f"/file/{media_id}")
    current = [p["id"] for p in (f.get("playlists") or [])] if st == 200 else []
    st, r = call("PUT", f"/file/{media_id}",
                 {"playlists": sorted(set(current + [playlist["id"]]))})
    print(f"  mixtape ajoutée à la playlist  -> HTTP {st}")
    if st != 200:
        die(f"Échec de l'ajout : {r}")

    st, r = call("PUT", f"/playlist/{playlist['id']}", {
        "is_enabled": True,
        "weight": ONAIR_WEIGHT,
        "schedule_items": [{
            "start_time": start_i,
            "end_time": end_i,
            "start_date": air_date.isoformat(),
            "end_date": air_date.isoformat(),
            "days": [],
            "loop_once": True,   # une seule passe dans la fenêtre
        }],
    })
    print(f"  planning posé + playlist active -> HTTP {st}")
    if st != 200:
        die(f"Échec de la planification : {r}")

    # 2. Épisode podcast.
    # season_number/episode_number sont obligatoires : sans eux l'entité AzuraCast
    # lève « must not be accessed before initialization » (HTTP 500).
    st, ep = call("POST", f"/podcast/{podcast['id']}/episodes", {
        "title": title,
        "description": args.desc or f"KALBASSFM mixtape — {air_date:%B %Y}.",
        "explicit": False,
        "season_number": 1,
        "episode_number": episode_no,
        "publish_at": publish_at,
    })
    print(f"  épisode créé                   -> HTTP {st}")
    if st != 200:
        die(f"Échec de la création d'épisode : {ep}")

    # 3. Média du podcast.
    local = args.local
    if not local:
        tmp = TOOLS_DIR / "_mixtape_tmp.mp3"
        print("  téléchargement du média depuis le serveur…")
        req = urllib.request.Request(
            f"{BASE}/api/station/{STATION}/file/{media_id}/play")
        req.add_header("X-API-Key", AZURACAST_API_KEY)
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        with urllib.request.urlopen(req, timeout=1800) as r, open(tmp, "wb") as out:
            out.write(r.read())
        local = tmp

    st, r = upload_media(podcast["id"], ep["id"], local)
    print(f"  média uploadé ({os.path.getsize(local):,} o) -> HTTP {st}")
    if not args.local and Path(local).exists():
        Path(local).unlink()
    if st != 200:
        die(f"Épisode créé mais média non attaché : {r}\n"
            f"   Réessayer l'upload seul, ou supprimer l'épisode dans AzuraCast.")

    st, ep2 = call("GET", f"/podcast/{podcast['id']}/episode/{ep['id']}")
    print(f"\n=== FAIT ===")
    print(f"  épisode publié : {ep2.get('is_published')} | média attaché : "
          f"{ep2.get('has_media')}")
    print(f"  flux RSS       : {BASE}/public/{STATION}/podcast/{podcast['id']}/feed")
    print(f"  page publique  : {BASE}/public/{STATION}/podcasts")
    print(f"\n  Note : l'AutoDJ termine toujours le morceau en cours avant de tirer "
          f"le suivant.\n  La mixtape démarre donc à {fmt_hhmm(start_i)} « à un titre "
          f"près », pas à la seconde.")


if __name__ == "__main__":
    main()
