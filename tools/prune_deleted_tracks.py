#!/usr/bin/env python3
"""Repercute sur AzuraCast les suppressions faites a la main en local.

Cas d'usage : tu passes en revue un bac (ex. 5_clubhouse, 7_nightdub) dans
l'explorateur Windows et supprimes quelques fichiers directement dans
New_prog/<bac>/. Ce script compare chaque bac local a son pendant AzuraCast
(API files/list, pas SFTP -- il faut le media_id pour supprimer proprement
FICHIER + ENTREE BIBLIOTHEQUE en un seul appel, meme endpoint que la commande
Telegram /delete_track) et retire du serveur ce qui a disparu en local.

Retire aussi les entrees correspondantes de metadata.json (meme principe que
clean_clapcrate_full.py).

Dry-run par defaut, --apply pour supprimer reellement (irreversible cote
AzuraCast). Sans argument : les 9 bacs. Sinon, limiter aux bacs donnes.

Usage :
    python prune_deleted_tracks.py                          # tous les bacs, dry-run
    python prune_deleted_tracks.py 5_clubhouse 7_nightdub    # dry-run cible
    python prune_deleted_tracks.py 5_clubhouse 7_nightdub --apply
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)
from azuracast_config import AZURACAST_API_KEY  # noqa: E402
from classify_bins import NEW_BINS  # noqa: E402  (source de verite unique de la grille)

BASE = "https://kalbassfm.duckdns.org/api"
STATION = 1
LOCAL_ROOT = r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog"
METADATA_PATH = os.path.join(TOOLS_DIR, "metadata.json")


def call(method, path):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("X-API-Key", AZURACAST_API_KEY)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            return r.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:400]


def local_files(bin_name):
    d = os.path.join(LOCAL_ROOT, bin_name)
    if not os.path.isdir(d):
        return set()
    return {f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))}


def remote_media(bin_name):
    """{nom_fichier: media_id} pour tout le contenu media du bac sur AzuraCast."""
    q = urllib.parse.quote(bin_name)
    status, data = call("GET", f"/station/{STATION}/files/list?currentDirectory={q}")
    if status != 200:
        raise SystemExit(f"Impossible de lister {bin_name}/ : {status} {data}")
    rows = data["rows"] if isinstance(data, dict) and "rows" in data else data
    return {r["path"].split("/", 1)[-1]: r["media"]["id"] for r in rows if r.get("type") == "media"}


def main():
    apply_mode = "--apply" in sys.argv
    bins = [a for a in sys.argv[1:] if not a.startswith("--")] or NEW_BINS

    to_delete = []  # (bin, filename, media_id)
    for b in bins:
        loc = local_files(b)
        rem = remote_media(b)
        missing = sorted(set(rem) - loc)
        if missing:
            print(f"[{b}] {len(missing)} fichier(s) present(s) sur le serveur, absent(s) en local :")
            for f in missing:
                print(f"    {f}")
            to_delete.extend((b, f, rem[f]) for f in missing)
        else:
            print(f"[{b}] OK, rien a supprimer")

    if not to_delete:
        print("\nRien a faire.")
        return
    print(f"\n{len(to_delete)} fichier(s) au total.")

    if not apply_mode:
        print("\nDRY-RUN — rien n'a ete supprime. Relancer avec --apply pour supprimer "
              "reellement (fichier + entree bibliotheque, irreversible cote AzuraCast).")
        return

    deleted_ids = set()
    for b, f, media_id in to_delete:
        status, res = call("DELETE", f"/station/{STATION}/file/{media_id}")
        if status not in (200, 204):
            print(f"  [ECHEC] {b}/{f} : {status} {res}")
            continue
        print(f"  [OK] supprime : {b}/{f}")
        deleted_ids.add((b, f))

    # metadata.json local : retire les memes entrees (meme principe que
    # clean_clapcrate_full.py), matching sur bac+nom de fichier.
    if os.path.exists(METADATA_PATH) and deleted_ids:
        with open(METADATA_PATH, encoding="utf-8") as fh:
            meta = json.load(fh)
        deleted_keys = {(b, f) for b, f, _ in to_delete if (b, f) in deleted_ids}
        before = len(meta)
        meta = [
            e for e in meta
            if (os.path.basename(os.path.dirname(e.get("path", ""))), os.path.basename(e.get("path", "")))
            not in deleted_keys
        ]
        if len(meta) != before:
            with open(METADATA_PATH, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=1)
            print(f"\nmetadata.json : {before - len(meta)} entree(s) retiree(s) "
                  f"(avant {before}, apres {len(meta)}).")

    print(f"\n{len(deleted_ids)}/{len(to_delete)} supprime(s) sur AzuraCast.")


if __name__ == "__main__":
    main()
