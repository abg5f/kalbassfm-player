#!/usr/bin/env python3
"""LOT 4 (setup) : cree les playlists AzuraCast `boost_up`/`boost_down` pour
la commande Telegram /energy.

Meme mecanisme decouvert au LOT 1 : l'appartenance a une playlist est un champ
par morceau (Api_StationMedia.playlists), pas une regle de dossier. On cree
donc les playlists puis on y rattache explicitement le contenu des dossiers
sources.

  - boost_up   : 5_clubhouse + 6_techno  ("pousser" la rotation)
  - boost_down : 1_chill + 7_nightdub    ("calmer" la rotation)

Les deux sont creees DESACTIVEES, sans planning permanent : /energy les
active avec un planning date (start_date/end_date) que AzuraCast expire tout
seul, jamais ce script.

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

# nom de playlist -> dossiers sources (voir docstring)
BOOST_PLAYLISTS = {
    "boost_up": ["5_clubhouse", "6_techno"],
    "boost_down": ["1_chill", "7_nightdub"],
}


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


def list_folder_files(folder):
    q = urllib.parse.quote(folder)
    status, data = call("GET", f"/station/{STATION}/files/list?currentDirectory={q}")
    if status != 200:
        raise SystemExit(f"Impossible de lister {folder}/ : {status} {data}")
    rows = data["rows"] if isinstance(data, dict) and "rows" in data else data
    return [r for r in rows if r.get("type") == "media"]


def main():
    apply_mode = "--apply" in sys.argv

    existing = list_playlists()
    to_create = [n for n in BOOST_PLAYLISTS if n not in existing]
    print(f"Playlists deja presentes : {[n for n in BOOST_PLAYLISTS if n in existing]}")
    print(f"Playlists a creer        : {to_create}")

    folder_files = {}
    for name, folders in BOOST_PLAYLISTS.items():
        files = []
        for f in folders:
            files.extend(list_folder_files(f))
        folder_files[name] = files
        without = [x for x in files if not x.get("media", {}).get("playlists")]
        print(f"\n[{name}] source={'+'.join(folders)} : {len(files)} fichier(s) media, "
              f"{len(without)} sans aucune playlist assignee")

    if not apply_mode:
        print("\nDRY-RUN — rien n'a ete cree ni modifie. Relancer avec --apply.")
        return

    ids = {}
    for name in BOOST_PLAYLISTS:
        if name in existing:
            ids[name] = existing[name]["id"]
            continue
        status, data = call("POST", f"/station/{STATION}/playlists", {
            "name": name,
            "type": "default",
            "source": "songs",
            "order": "shuffle",
            "is_enabled": False,  # active uniquement par /energy, avec planning date
            "avoid_duplicates": True,
            "include_in_requests": True,
        })
        if status not in (200, 201):
            raise SystemExit(f"Creation de la playlist {name} echouee : {status} {data}")
        ids[name] = data["id"]
        print(f"  [OK] playlist creee : {name} (id {data['id']}, is_enabled=False)")

    for name, files in folder_files.items():
        pid = ids[name]
        attached, failed = 0, 0
        for f in files:
            media_id = f["media"]["id"]
            current = {p["id"] if isinstance(p, dict) else p for p in (f["media"].get("playlists") or [])}
            if pid in current:
                continue
            status, data = call("PUT", f"/station/{STATION}/file/{media_id}",
                                 {"playlists": sorted(current | {pid})})
            if status not in (200, 201):
                print(f"  [ECHEC] {f['path']} : {status} {data}")
                failed += 1
                continue
            attached += 1
        print(f"\n{name} (#{pid}) : {attached} fichier(s) rattache(s), {failed} echec(s).")


if __name__ == "__main__":
    main()
