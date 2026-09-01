#!/usr/bin/env python3
"""
Automatisation hebdomadaire de la mixtape du dimanche : bandeau pin J-3,
diffusion + podcast + annonce chat le jour J.

Concu pour tourner une fois par jour via le Planificateur de taches Windows
-- aucun trigger interne, ce script se contente de verifier "y a-t-il
quelque chose a faire aujourd'hui ?" a chaque appel (idempotent, cf. l'etat
local plus bas).

Modele de donnees : mixtape_onair (playlist AzuraCast) contient PLUSIEURS
mixtapes candidates en meme temps -- l'admin les y depose a la main sur
AzuraCast. La date de diffusion choisie pour chacune est stockee dans son
champ Album (AAAA-MM-JJ), choisi plutot qu'ISRC (reserve aux rapports de
licence SACEM, a ne pas detourner). Le CHOIX de la date se fait via
/queue_mix dans le bot Telegram (api/telegram.js) -- ce script ne fait
qu'executer ce qui a deja ete decide, jamais le choix lui-meme.

AzuraCast ne planifie qu'au niveau PLAYLIST, jamais au niveau morceau : pour
qu'un seul morceau precis passe un dimanche precis alors que plusieurs
partagent la meme playlist, il faut reduire mixtape_onair a CE SEUL morceau
juste avant de poser le planning du jour -- meme geste que
tools/publish_mixtape.py (fonctions reutilisees directement, pas dupliquees).

Etat local (tools/mixtape_state.json, gitignore) : memorise quelles paires
(morceau, date) ont deja recu leur pin / leur diffusion, pour ne rien
reposter si le script tourne plusieurs fois le meme jour (le Planificateur
de taches peut rattraper une execution manquee, ou etre relance a la main).

Usage :
    python mixtape_weekly.py            # dry-run : affiche ce qui serait fait
    python mixtape_weekly.py --apply    # execute reellement
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from publish_mixtape import (  # noqa: E402  (reutilise le geste "diffuser + publier")
    call, upload_media, hhmm, resolve_targets, die,
    BASE, STATION, BANK_DIR, ONAIR_WEIGHT,
)
from azuracast_config import AZURACAST_API_KEY  # noqa: E402

STATE_PATH = TOOLS_DIR / "mixtape_state.json"
AIR_START = "18:00"
PIN_DAYS_BEFORE = 3


# --------------------------------------------------------------------------- etat local

def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"pinned": [], "published": []}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


# --------------------------------------------------------------------------- Redis (chat)

def kv_call(*segments):
    from kv_config import KV_REST_API_URL, KV_REST_API_TOKEN
    url = KV_REST_API_URL.rstrip("/") + "/" + "/".join(urllib.parse.quote(str(s), safe="") for s in segments)
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {KV_REST_API_TOKEN}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def post_admin_message(text):
    """Meme forme que postAdminMessage() dans api/telegram.js : admin:true
    pose UNIQUEMENT ici, jamais derivable par un client."""
    import random
    import string
    import time
    msg_id = f"{int(time.time() * 1000):x}" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    msg = {"id": msg_id, "nick": "Admin", "text": text[:200], "ts": int(time.time() * 1000), "admin": True}
    kv_call("lpush", "chat:messages", json.dumps(msg, ensure_ascii=False))
    kv_call("ltrim", "chat:messages", "0", "99")


def set_pinned(text):
    if text:
        kv_call("set", "chat:pinned", text[:200])
    else:
        kv_call("del", "chat:pinned")


# --------------------------------------------------------------------------- AzuraCast

def load_candidates(playlist_id):
    """Morceaux actuellement membres de mixtape_onair, avec leur date (champ
    Album, AAAA-MM-JJ) si deja programmee -- meme endpoint que load_bank()
    dans publish_mixtape.py, filtre par appartenance a la playlist."""
    st, files = call("GET", f"/files?searchPhrase={BANK_DIR}%2F&rowCount=500")
    if st != 200:
        die(f"Lecture de la bibliotheque impossible (HTTP {st}) : {files}")
    rows = files.get("rows", files) if isinstance(files, dict) else files
    out = []
    for f in rows:
        playlists = [p.get("id") if isinstance(p, dict) else p for p in (f.get("playlists") or [])]
        if playlist_id in playlists:
            out.append(f)
    return out


def parse_socials(lyrics):
    """Lignes "Soundcloud <url>" / "Instagram : <url>" dans le champ Paroles
    (AzuraCast ne prevoit pas de champs dedies aux reseaux sociaux)."""
    links = []
    for line in (lyrics or "").splitlines():
        m = re.search(r"(https?://\S+|www\.\S+)", line)
        if not m:
            continue
        url = m.group(1).rstrip("/")
        low = line.lower()
        label = "SoundCloud" if "soundcloud" in low else ("Instagram" if "instagram" in low else None)
        if label:
            links.append((label, url))
    return links


def publish_one(candidate, air_date, playlist, podcast, apply_mode):
    """Vide mixtape_onair, n'y remet QUE ce morceau, pose le planning du
    jour, publie l'episode podcast, purge la file AutoDJ, annonce dans le
    chat. Reprend le geste de publish_mixtape.py --apply, adapte a une
    playlist qui contient deja d'autres candidats a ne pas deranger."""
    media_id = candidate["id"]
    title = candidate.get("title") or Path(candidate["path"]).stem
    artist = candidate.get("artist") or "a guest DJ"

    start_i = hhmm(AIR_START)
    secs = int(candidate.get("length") or 0)
    end_dt = (datetime.combine(air_date, datetime.min.time())
              + timedelta(hours=start_i // 100, minutes=start_i % 100)
              + timedelta(seconds=secs) + timedelta(minutes=10))
    end_i = end_dt.hour * 100 + end_dt.minute

    print(f"  -> {title} ({artist}) le {air_date} de {AIR_START} a {end_i // 100:02d}:{end_i % 100:02d}")
    if not apply_mode:
        return

    st, r = call("DELETE", f"/playlist/{playlist['id']}/empty")
    if st != 200:
        die(f"Echec du vidage de {playlist['name']} : {r}")

    st, r = call("PUT", f"/playlist/{playlist['id']}", {
        "is_enabled": True,
        "weight": ONAIR_WEIGHT,
        "schedule_items": [{
            "start_time": start_i, "end_time": end_i,
            "start_date": air_date.isoformat(), "end_date": air_date.isoformat(),
            "days": [], "loop_once": True,
        }],
    })
    if st != 200:
        die(f"Echec de la planification : {r}")

    st, r = call("PUT", f"/file/{media_id}", {"playlists": [playlist["id"]]})
    if st != 200:
        die(f"Echec du rattachement a la playlist : {r}")

    st, eps = call("GET", f"/podcast/{podcast['id']}/episodes")
    episode_no = (len(eps) if isinstance(eps, list) else 0) + 1
    publish_at = int(datetime.combine(air_date, datetime.min.time()).timestamp()) \
        + (start_i // 100) * 3600 + (start_i % 100) * 60
    st, ep = call("POST", f"/podcast/{podcast['id']}/episodes", {
        "title": title,
        "description": f"KALBASSFM mixtape — {artist}.",
        "explicit": False, "season_number": 1, "episode_number": episode_no,
        "publish_at": publish_at,
    })
    if st != 200:
        die(f"Echec de la creation d'episode : {ep}")

    tmp = TOOLS_DIR / "_mixtape_tmp.mp3"
    dl_req = urllib.request.Request(f"{BASE}/api/station/{STATION}/file/{media_id}/play")
    dl_req.add_header("X-API-Key", AZURACAST_API_KEY)
    dl_req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    with urllib.request.urlopen(dl_req, timeout=1800) as r, open(tmp, "wb") as out:
        out.write(r.read())
    st, r = upload_media(podcast["id"], ep["id"], tmp)
    tmp.unlink(missing_ok=True)
    if st != 200:
        die(f"Episode cree mais media non attache : {r}")

    # Purge la file AutoDJ deja construite (~27 min d'avance) pour un effet
    # immediat -- meme endpoint que /energy et le LOT 2.
    call("PUT", f"{BASE}/api/admin/debug/station/1/clearqueue")

    links = parse_socials(candidate.get("lyrics"))
    tail = (" Follow: " + " · ".join(f"{label} — {url}" for label, url in links)) if links else ""
    announce = f'🎧 This week\'s Sunday mix is live: "{title}" by {artist}!{tail}'
    post_admin_message(announce)

    # Le rappel "arrive bientot" n'a plus lieu d'etre une fois le mix en
    # direct -- l'annonce chat ci-dessus prend le relais.
    set_pinned(None)


# --------------------------------------------------------------------------- main

def main():
    apply_mode = "--apply" in sys.argv
    today = date.today()  # heure de la machine (Windows, attendue Europe/Paris)

    playlist, podcast = resolve_targets()
    candidates = load_candidates(playlist["id"])
    scheduled = [(c, c["album"]) for c in candidates if c.get("album")]
    print(f"{len(candidates)} morceau(x) dans {playlist['name']}, {len(scheduled)} programme(s).")

    state = load_state()
    to_pin, to_publish = [], []
    for c, album in scheduled:
        try:
            air_date = datetime.strptime(album, "%Y-%m-%d").date()
        except ValueError:
            print(f"  [IGNORE] champ Album illisible comme date : {album!r} ({Path(c['path']).name})")
            continue
        key = f"{c['id']}:{album}"
        if air_date == today + timedelta(days=PIN_DAYS_BEFORE) and key not in state["pinned"]:
            to_pin.append((c, air_date, key))
        if air_date == today and key not in state["published"]:
            to_publish.append((c, air_date, key))

    if not to_pin and not to_publish:
        print("Rien a faire aujourd'hui.")
        return

    for c, air_date, key in to_pin:
        artist = c.get("artist") or "a guest DJ"
        title = c.get("title") or Path(c["path"]).stem
        text = (f'📌 Sunday mix incoming: {artist} — "{title}" airs live '
                f'this Sunday, {air_date:%B %d}, at {AIR_START} (Paris time).')
        print(f"[PIN] {text}")
        if apply_mode:
            set_pinned(text)
            state["pinned"].append(key)

    for c, air_date, key in to_publish:
        print(f"[PUBLISH] {Path(c['path']).name}")
        publish_one(c, air_date, playlist, podcast, apply_mode)
        if apply_mode:
            state["published"].append(key)

    if apply_mode:
        save_state(state)
    else:
        print("\nDRY-RUN — rien n'a ete ecrit/publie/annonce. Relancer avec --apply.")


if __name__ == "__main__":
    main()
