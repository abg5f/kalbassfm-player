#!/usr/bin/env python3
"""
LOT 2 — bascule la programmation vers la rotation continue (Nova/Radio Meuh)
et pose la montee d'energie du soir en heure de Paris.

Source de verite unique : la table declarative ci-dessous (ROTATION_TARGET).
Reexecutable : c'est l'outil de reglage des dosages a l'oreille par la suite
(cf. CONTEXT.md, section "Reglages a faire a l'oreille"). Chaque run recalcule
un diff contre l'etat live de l'API et n'ecrit que ce qui a change.

Trois groupes de playlists :
  - BASE       : rotation permanente, AUCUN schedule_items (24h/24).
  - EVENING    : s'AJOUTE a la base le soir (heure de Paris), schedule_items poses.
  - PUNCTUATION: jungle, once_per_x_songs, planning recale sur la montee du soir.
Plus DISABLE : les 4 miroirs *_guest devenus inutiles (poids unique en base
desormais) -> is_enabled False, ni supprimes ni autrement modifies.

Le fuseau station passe a Europe/Paris (heure d'ete automatique) ; c'est le
SEUL champ touche sur la ressource station.

Piege documente dans le brief : une entree qui franchit minuit (2200-0100,
0100-0300, 1900-0300) est datee par son jour de debut. Ici days=[] partout
(tous les jours) sur toutes les entrees -> pas d'ambiguite.

Usage :
    python apply_rotation.py            # dry-run : diff lisible, rien n'est ecrit
    python apply_rotation.py --apply    # ecrit timezone + poids + plannings + activations
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from azuracast_config import AZURACAST_API_KEY  # noqa: E402

BASE_URL = "https://kalbassfm.duckdns.org"
STATION = "kalbassfm"

TIMEZONE_TARGET = "Europe/Paris"

# ----------------------------------------------------------------- la grille
# id AzuraCast -> (nom, poids, schedule_items). schedule_items = [] pour la
# rotation de base (aucun planning = actif 24h/24). Heures en HHMM (int),
# toujours en heure de Paris une fois le fuseau station bascule.

BASE = {
    # id: (nom, poids)
    11: ("chill", 4),
    27: ("liquid", 4),
    14: ("deep", 7),
    17: ("nightdub", 6),
    12: ("groove", 10),
    13: ("house", 12),
}

EVENING = {
    # id: (nom, poids, [(start, end), ...])
    15: ("clubhouse", 10, [(2200, 100)]),
    16: ("techno", 8, [(2200, 100)]),
    22: ("clubhouse_guest", 6, [(1900, 2200), (100, 300)]),
    23: ("techno_guest", 5, [(1900, 2200), (100, 300)]),
    28: ("liquid_guest", 3, [(1900, 300)]),
}

# jungle : ponctuation (once_per_x_songs, inchange), seul le planning bouge
# (23h-06h -> 21h-03h pour accompagner la montee au lieu de vivre a part).
PUNCTUATION = {
    24: ("jungle", 3, [(2100, 300)]),
}

# Miroirs devenus inutiles : chaque bac a desormais un poids unique 24h/24,
# ces 4 playlists n'ont plus d'objet. Desactivees, PAS supprimees (poids et
# planning laisses tels quels pour un rollback trivial).
DISABLE = {
    18: "chill_guest",
    19: "groove_guest",
    20: "house_guest",
    21: "deep_guest",
}

# Volontairement non touches : Jingles (10), mixtape_onair (26).


# --------------------------------------------------------------------------- API

def call(method, path, body=None):
    url = path if path.startswith("http") else f"{BASE_URL}/api/station/{STATION}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-API-Key", AZURACAST_API_KEY)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:600]


def die(msg):
    print(f"ERREUR : {msg}")
    sys.exit(1)


def sched_key(items):
    """Comparable independamment de l'ordre / des id serveur (days toujours [] ici)."""
    return sorted((it["start_time"], it["end_time"]) for it in items)


def build_schedule(pairs):
    return [{"start_time": s, "end_time": e, "days": [], "start_date": None,
             "end_date": None, "loop_once": False} for s, e in pairs]


def fmt_time(hhmm):
    return f"{hhmm // 100:02d}:{hhmm % 100:02d}"


def fmt_pairs(pairs):
    return ", ".join(f"{fmt_time(s)}-{fmt_time(e)}" for s, e in pairs) if pairs else "(aucun — 24h/24)"


# --------------------------------------------------------------------------- diff

def diff_playlist(live, target_weight, target_enabled, target_pairs):
    """Retourne (payload_a_envoyer, lignes_de_diff)."""
    payload, lines = {}, []

    if live["weight"] != target_weight:
        lines.append(f"  poids     : {live['weight']} -> {target_weight}")
        payload["weight"] = target_weight

    if live["is_enabled"] != target_enabled:
        lines.append(f"  active    : {live['is_enabled']} -> {target_enabled}")
        payload["is_enabled"] = target_enabled

    if target_pairs is not None:
        live_pairs = sched_key(live.get("schedule_items") or [])
        want_pairs = sorted(target_pairs)
        if live_pairs != want_pairs:
            lines.append(f"  planning  : {fmt_pairs(live_pairs)} -> {fmt_pairs(target_pairs)}")
            payload["schedule_items"] = build_schedule(target_pairs)

    return payload, lines


def main():
    apply_mode = "--apply" in sys.argv

    # /api/station/{name} est en lecture seule (405 sur PUT, constate a l'usage) ;
    # l'edition passe par l'endpoint admin (id numerique). On lit l'objet complet
    # ici pour pouvoir le renvoyer entier a l'apply (Station est un gros schema,
    # un PUT partiel y est plus risque que sur les playlists).
    status, station = call("GET", f"{BASE_URL}/api/admin/station/1")
    if status != 200:
        die(f"lecture station impossible : {status} {station}")

    status, playlists = call("GET", "/playlists")
    if status != 200:
        die(f"lecture playlists impossible : {status} {playlists}")
    by_id = {p["id"]: p for p in playlists}

    print(f"{'APPLY' if apply_mode else 'DRY-RUN'} — bascule vers la rotation continue\n")

    # ---- fuseau
    tz_changed = station.get("timezone") != TIMEZONE_TARGET
    if tz_changed:
        print(f"[station] timezone : {station.get('timezone')} -> {TIMEZONE_TARGET}")
    else:
        print(f"[station] timezone : deja {TIMEZONE_TARGET}, inchange")

    # ---- rotation de base : poids, AUCUN planning
    playlist_payloads = {}
    print("\n-- Rotation de base (24h/24, aucun schedule_items) --")
    for pid, (name, weight) in BASE.items():
        live = by_id.get(pid)
        if not live:
            die(f"playlist id={pid} ({name}) introuvable sur le serveur")
        payload, lines = diff_playlist(live, weight, True, [])
        if lines:
            print(f"[{name} #{pid}]")
            print("\n".join(lines))
            playlist_payloads[pid] = (name, payload)
        else:
            print(f"[{name} #{pid}] deja a jour")

    # ---- montee du soir
    print("\n-- Montee du soir (heure de Paris, s'ajoute a la base) --")
    for pid, (name, weight, pairs) in EVENING.items():
        live = by_id.get(pid)
        if not live:
            die(f"playlist id={pid} ({name}) introuvable sur le serveur")
        payload, lines = diff_playlist(live, weight, True, pairs)
        if lines:
            print(f"[{name} #{pid}]")
            print("\n".join(lines))
            playlist_payloads[pid] = (name, payload)
        else:
            print(f"[{name} #{pid}] deja a jour")

    # ---- ponctuation jungle
    print("\n-- Ponctuation --")
    for pid, (name, weight, pairs) in PUNCTUATION.items():
        live = by_id.get(pid)
        if not live:
            die(f"playlist id={pid} ({name}) introuvable sur le serveur")
        payload, lines = diff_playlist(live, weight, True, pairs)
        if lines:
            print(f"[{name} #{pid}]")
            print("\n".join(lines))
            playlist_payloads[pid] = (name, payload)
        else:
            print(f"[{name} #{pid}] deja a jour")

    # ---- desactivation des miroirs inutiles (poids/planning non touches)
    print("\n-- Miroirs desactives (poids et planning laisses tels quels) --")
    for pid, name in DISABLE.items():
        live = by_id.get(pid)
        if not live:
            die(f"playlist id={pid} ({name}) introuvable sur le serveur")
        if live["is_enabled"]:
            print(f"[{name} #{pid}]\n  active    : True -> False")
            playlist_payloads[pid] = (name, {"is_enabled": False})
        else:
            print(f"[{name} #{pid}] deja desactivee")

    changed = sum(1 for _, p in playlist_payloads.values() if p)
    print(f"\n{changed} playlist(s) a modifier" + (", timezone a changer" if tz_changed else ""))

    if not apply_mode:
        print("\nDRY-RUN termine — rien n'a ete ecrit. Relancer avec --apply pour appliquer.")
        return

    # ---------------------------------------------------------------- APPLY
    if tz_changed:
        # Objet complet renvoye (mute juste timezone) plutot qu'un PUT partiel :
        # Station est un gros schema admin, plus prudent que sur les playlists.
        station["timezone"] = TIMEZONE_TARGET
        status, res = call("PUT", f"{BASE_URL}/api/admin/station/1", station)
        if status not in (200, 201):
            die(f"PUT timezone echoue : {status} {res}")
        print(f"[OK] timezone -> {TIMEZONE_TARGET}")

    for pid, (name, payload) in playlist_payloads.items():
        if not payload:
            continue
        status, res = call("PUT", f"/playlist/{pid}", payload)
        if status not in (200, 201):
            print(f"[ECHEC] {name} (#{pid}) : {status} {res}")
            continue
        print(f"[OK] {name} (#{pid}) mis a jour")

    print("\nTermine. Purger la file AutoDJ si un changement doit s'entendre "
          "immediatement (GET/DELETE /api/station/1/queue) — sinon effet au "
          "titre suivant, jusqu'a ~27 min plus tard.")


if __name__ == "__main__":
    main()
