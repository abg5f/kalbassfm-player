#!/usr/bin/env python3
"""LOT 1 (fin) : cree les playlists AzuraCast `liquid`/`liquid_guest` sur le
dossier 9_liquid et y rattache les morceaux.

Contexte decouvert en verifiant la synchro serveur : l'appartenance a une
playlist est un champ par morceau (`Api_StationMedia.playlists`, meme
mecanisme que le fix `/move` du 2026-07-24), PAS une regle "dossier". Deplacer
les fichiers vers 9_liquid/ ne les a donc rattaches a aucune playlist —
confirme par l'API : `playlists: []` sur les morceaux verifies apres la
synchro CheckMediaTask.

Cree (si absentes, sinon reutilise) :
  - `liquid`       (miroir des 6 *_guest existants, poids place-holder :
                     LOT 2 / apply_rotation.py posera le poids et le planning
                     definitifs, ce script ne fait QUE l'appartenance)
  - `liquid_guest`

Les deux sont creees is_enabled=false : sans planning ni poids definitif elles
ne doivent pas participer a la rotation avant que LOT 2 les configure.

Rattache ensuite les DEUX playlists a chaque fichier de 9_liquid/ (liste
recuperee via GET files/list?currentDirectory=9_liquid, source de verite —
pas le CSV de migration, qui ne connait pas les media_id serveur).

Dry-run par defaut, --apply pour ecrire.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")
from azuracast_config import AZURACAST_API_KEY  # noqa: E402

BASE = "https://kalbassfm.duckdns.org/api"
STATION = 1
FOLDER = "9_liquid"
PLAYLIST_NAMES = ["liquid", "liquid_guest"]


def call(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-API-Key", AZURACAST_API_KEY)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:600]


def list_playlists():
    status, data = call("GET", f"/station/{STATION}/playlists")
    if status != 200:
        raise SystemExit(f"Impossible de lister les playlists : {status} {data}")
    return {p["name"]: p for p in data}


def list_folder_files():
    q = urllib.parse.quote(FOLDER)
    status, data = call("GET", f"/station/{STATION}/files/list?currentDirectory={q}")
    if status != 200:
        raise SystemExit(f"Impossible de lister {FOLDER}/ : {status} {data}")
    rows = data["rows"] if isinstance(data, dict) and "rows" in data else data
    return [r for r in rows if r.get("type") == "media"]


def main():
    apply_mode = "--apply" in sys.argv

    existing = list_playlists()
    to_create = [n for n in PLAYLIST_NAMES if n not in existing]
    print(f"Playlists deja presentes : {[n for n in PLAYLIST_NAMES if n in existing]}")
    print(f"Playlists a creer        : {to_create}")

    files = list_folder_files()
    print(f"\n{len(files)} fichier(s) media dans {FOLDER}/")
    without_playlist = [f for f in files if not f.get("media", {}).get("playlists")]
    print(f"{len(without_playlist)} sans aucune playlist assignee")

    if not apply_mode:
        print("\nDRY-RUN — rien n'a ete cree ni modifie. Relancer avec --apply.")
        return

    ids = {}
    for name in PLAYLIST_NAMES:
        if name in existing:
            ids[name] = existing[name]["id"]
            continue
        status, data = call("POST", f"/station/{STATION}/playlists", {
            "name": name,
            "type": "default",
            "source": "songs",
            "order": "shuffle",
            "is_enabled": False,  # LOT 2 (apply_rotation.py) posera poids + planning
            "avoid_duplicates": True,
            "include_in_requests": True,
        })
        if status not in (200, 201):
            raise SystemExit(f"Creation de la playlist {name} echouee : {status} {data}")
        ids[name] = data["id"]
        print(f"  [OK] playlist creee : {name} (id {data['id']}, is_enabled=False)")

    playlist_ids = [ids[n] for n in PLAYLIST_NAMES]
    attached, failed = 0, 0
    for f in files:
        media_id = f["media"]["id"]
        current = f["media"].get("playlists") or []
        current_ids = {p["id"] if isinstance(p, dict) else p for p in current}
        merged = sorted(current_ids | set(playlist_ids))
        if current_ids >= set(playlist_ids):
            continue  # deja rattache aux deux
        status, data = call("PUT", f"/station/{STATION}/file/{media_id}", {"playlists": merged})
        if status not in (200, 201):
            print(f"  [ECHEC] {f['path']} : {status} {data}")
            failed += 1
            continue
        attached += 1
    print(f"\n{attached} fichier(s) rattache(s) aux playlists {PLAYLIST_NAMES}, {failed} echec(s).")


if __name__ == "__main__":
    main()
