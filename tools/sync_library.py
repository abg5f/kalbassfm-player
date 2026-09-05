#!/usr/bin/env python3
"""Remet le PC et AzuraCast iso apres une session de nettoyage, dans les DEUX sens.

Le cas d'usage : tu ecartes des morceaux depuis le bot Telegram (/search puis
🗑 ou 🚫) ET depuis l'explorateur Windows, dans le desordre. Au bout d'un
moment plus personne ne sait qui a quoi. Ce script compare bac par bac et
propose une action pour chaque ecart :

  A. LOCAL SEUL, absent aussi du serveur en SFTP
     -> supprime cote radio (bot Telegram, UI AzuraCast, review_energy.py).
        Action : ranger le mp3 dans New_prog/_ecartes/<bac>/ (--delete-local
        pour l'effacer) et retirer l'entree de metadata.json.

  B. LOCAL SEUL mais PRESENT sur le serveur en SFTP
     -> le fichier est bien monte, AzuraCast ne l'a pas encore indexe.
        Action : AUCUNE suppression. Lance un "Rescan" de la bibliotheque
        (AzuraCast -> Files -> ⋮ -> Rescan) et relance ce script.

  C. LOCAL SEUL et en attente du VERDICT (pending_review.json)
     -> triage_new_tracks.py l'a classe, analyse_new_tracks.py ne l'a pas
        encore juge. Il n'a jamais ete envoye, et c'est normal.
        Action : AUCUNE. Lance analyse.bat pour le juger et le mettre en ligne.

  D. LOCAL SEUL et en attente d'ENVOI (pending_uploads.json)
     -> le verdict est passe, mais l'upload SFTP a echoue.
        Action : AUCUNE. Le prochain run d'analyse le renverra tout seul.

  E. SERVEUR SEUL
     -> supprime depuis le PC.
        Action : suppression sur AzuraCast (fichier + entree bibliotheque) et
        retrait de metadata.json. C'est ce que faisait deja
        prune_deleted_tracks.py, desormais couvert ici.

  F. metadata.json orphelin (entree sans fichier local ni media serveur)
     -> nettoyage de l'index d'analyse.

POURQUOI LA VUE SFTP EST INDISPENSABLE (cas B) : l'API ne liste que les medias
INDEXES par AzuraCast. Un mp3 uploade mais pas encore scanne est donc absent de
l'API tout en existant sur le serveur — le confondre avec une suppression
volontaire ferait disparaitre du PC un morceau parfaitement sain. Sans
paramiko/sftp_config.py, le script tourne quand meme (--no-sftp), mais il
REFUSE alors d'agir sur les fichiers locaux : il ne peut plus distinguer A de B.

Dry-run par defaut, comme prune_deleted_tracks.py.

Usage :
    python sync_library.py                        # rapport complet, rien n'est ecrit
    python sync_library.py 6_techno 8_jungle      # limite a des bacs
    python sync_library.py --apply                # applique les deux sens
    python sync_library.py --apply --delete-local # efface au lieu de ranger dans _ecartes
    python sync_library.py --apply --only-server  # ne touche qu'a AzuraCast (sens D)
    python sync_library.py --apply --only-local   # ne touche qu'au PC (sens A)
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)
from classify_bins import NEW_BINS  # noqa: E402  (source de verite de la grille)

LOCAL_ROOT = os.getenv("KALBASS_NEW_PROG",
                       r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog")
METADATA_PATH = os.path.join(TOOLS_DIR, "metadata.json")
PENDING_UPLOADS_PATH = os.path.join(TOOLS_DIR, "pending_uploads.json")
# Chemins redefinis ici plutot qu'importes d'azuracast_upload : ce module
# importe paramiko des le chargement, or sync_library doit rester lancable en
# --no-sftp sur une machine sans paramiko.
PENDING_REVIEW_PATH = os.path.join(TOOLS_DIR, "pending_review.json")
QUARANTINE = "_ecartes"  # meme dossier que review_energy.py --delete

BASE = os.getenv("AZURACAST_BASE_URL", "https://kalbassfm.duckdns.org") + "/api"
STATION = os.getenv("AZURACAST_STATION_ID", "1")


# ------------------------------- AzuraCast -------------------------------

def api_key():
    try:
        from azuracast_config import AZURACAST_API_KEY
    except ImportError:
        sys.exit("azuracast_config.py introuvable (cle API AzuraCast). "
                 "AzuraCast -> profil -> My API Keys.")
    return AZURACAST_API_KEY


def call(method, path):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("X-API-Key", api_key())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            return r.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:400]


def remote_media(bin_name):
    """{nom_fichier: media_id} des medias INDEXES du bac (meme appel que
    prune_deleted_tracks.py, qui a fait ses preuves en prod)."""
    q = urllib.parse.quote(bin_name)
    status, data = call("GET", f"/station/{STATION}/files/list?currentDirectory={q}")
    if status != 200:
        raise SystemExit(f"Impossible de lister {bin_name}/ : {status} {data}")
    rows = data["rows"] if isinstance(data, dict) and "rows" in data else data
    return {r["path"].split("/", 1)[-1]: r["media"]["id"] for r in rows if r.get("type") == "media"}


# --------------------------------- SFTP ---------------------------------

def sftp_view(bins):
    """{bac: {noms de fichiers}} vu du disque serveur, ou None si indisponible.

    Lecture seule : on ne se connecte que pour distinguer "supprime cote radio"
    de "pas encore indexe" (cf. cas B en tete de fichier)."""
    try:
        import paramiko
        from sftp_config import SFTP_HOST, SFTP_PORT, SFTP_USER, SFTP_PASS, SFTP_REMOTE_ROOT
    except ImportError as e:
        print(f"[SFTP indisponible : {e}] — les fichiers locaux ne seront pas touches.")
        return None

    print(f"Connexion SFTP {SFTP_HOST}:{SFTP_PORT}...")
    transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    transport.connect(username=SFTP_USER, password=SFTP_PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)
    try:
        out = {}
        for b in bins:
            remote_dir = SFTP_REMOTE_ROOT.rstrip("/") + "/" + b
            try:
                out[b] = {e.filename for e in sftp.listdir_attr(remote_dir)
                          if not e.filename.startswith(".")}
            except FileNotFoundError:
                out[b] = set()
        return out
    finally:
        sftp.close()
        transport.close()


# --------------------------------- local ---------------------------------

def local_files(bin_name):
    d = os.path.join(LOCAL_ROOT, bin_name)
    if not os.path.isdir(d):
        return set()
    return {f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))}


def _queue(path_json):
    """{(bac, nom de fichier)} lus dans une file d'attente du pipeline.

    Les deux files disent la meme chose a ce script — "ce morceau est local,
    absent du serveur, et c'est VOULU" — mais pour deux raisons differentes,
    d'ou deux rubriques distinctes dans le rapport. Les confondre avec une
    suppression ferait proposer d'ecarter un morceau parfaitement sain.
    """
    if not os.path.exists(path_json):
        return set()
    try:
        with open(path_json, encoding="utf-8") as fh:
            entries = json.load(fh)
    except (ValueError, OSError):
        return set()
    out = set()
    for e in entries:
        path = (e.get("path") or "").replace("\\", "/")
        if path:
            out.add((e.get("slot") or os.path.basename(os.path.dirname(path)),
                     os.path.basename(path)))
    return out


def pending_uploads():
    """Envois SFTP en echec — analyse_new_tracks.py les retente tout seul."""
    return _queue(PENDING_UPLOADS_PATH)


def pending_review():
    """Classes par le triage, pas encore juges — analyse.bat s'en occupe."""
    return _queue(PENDING_REVIEW_PATH)


def load_metadata():
    if not os.path.exists(METADATA_PATH):
        return None
    with open(METADATA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def meta_key(entry):
    p = (entry.get("path") or "").replace("\\", "/")
    return os.path.basename(os.path.dirname(p)), os.path.basename(p)


# ------------------------------ diagnostic ------------------------------

def diagnose(bins, use_sftp):
    remote = {b: remote_media(b) for b in bins}
    local = {b: local_files(b) for b in bins}
    on_server = sftp_view(bins) if use_sftp else None
    pending = pending_uploads()
    awaiting_verdict = pending_review()

    deleted_on_radio, not_indexed, awaiting_upload, deleted_on_pc = [], [], [], []
    awaiting_review = []
    for b in bins:
        for name in sorted(local[b] - set(remote[b])):
            # L'attente du verdict passe en premier : un morceau tout juste
            # classe n'a jamais ete envoye, il n'a donc rien a faire dans la
            # file des envois rates.
            if (b, name) in awaiting_verdict:
                awaiting_review.append((b, name))
            elif (b, name) in pending:
                awaiting_upload.append((b, name))
            elif on_server is not None and name in on_server.get(b, set()):
                not_indexed.append((b, name))
            else:
                deleted_on_radio.append((b, name))
        for name in sorted(set(remote[b]) - local[b]):
            deleted_on_pc.append((b, name, remote[b][name]))

    meta = load_metadata()
    orphans = []
    if meta is not None:
        known = {(b, n) for b in bins for n in local[b]} | {(b, n) for b in bins for n in remote[b]}
        for entry in meta:
            bac, name = meta_key(entry)
            if bac in bins and (bac, name) not in known:
                orphans.append((bac, name))

    return {
        "bins": bins, "local": local, "remote": remote, "sftp": on_server,
        "deleted_on_radio": deleted_on_radio, "not_indexed": not_indexed,
        "awaiting_review": awaiting_review,
        "awaiting_upload": awaiting_upload, "deleted_on_pc": deleted_on_pc,
        "orphans": orphans, "meta": meta,
    }


def report(d):
    for b in d["bins"]:
        n_local, n_remote = len(d["local"][b]), len(d["remote"][b])
        # Comparaison des CONTENUS, pas des comptes : un fichier supprime d'un
        # cote et un autre ajoute de l'autre donnent le meme total sans etre iso.
        flag = "OK" if d["local"][b] == set(d["remote"][b]) else "ECART"
        print(f"[{b}] local={n_local} azuracast={n_remote}  {flag}")

    def block(title, rows, hint):
        if not rows:
            return
        print(f"\n{title} ({len(rows)})")
        print(f"  {hint}")
        for r in rows:
            print(f"    [{r[0]}] {r[1]}")

    block("A. Supprimes cote radio, encore sur le PC", d["deleted_on_radio"],
          "-> ranges dans _ecartes/<bac>/ (ou effaces avec --delete-local) + retires de metadata.json")
    block("B. Sur le serveur mais pas indexes par AzuraCast", d["not_indexed"],
          "-> AUCUNE suppression : lance un Rescan de la bibliotheque puis relance ce script")
    block("C. En attente du verdict d'analyse (pending_review.json)", d["awaiting_review"],
          "-> AUCUNE action : lance analyse.bat pour les juger et les mettre en ligne")
    block("D. En attente d'envoi SFTP (pending_uploads.json)", d["awaiting_upload"],
          "-> AUCUNE action : le prochain run d'analyse les renverra")
    block("E. Supprimes sur le PC, encore sur AzuraCast", d["deleted_on_pc"],
          "-> supprimes d'AzuraCast (fichier + entree bibliotheque) + retires de metadata.json")
    block("F. Entrees metadata.json orphelines", d["orphans"],
          "-> retirees de metadata.json (l'analyse Essentia ne sert plus a rien)")

    if d["sftp"] is None and d["deleted_on_radio"]:
        print("\n⚠️  Vue SFTP absente : impossible de distinguer A (supprime cote radio) de B "
              "(pas encore indexe). Les fichiers locaux ne seront PAS touches.")
    total = (len(d["deleted_on_radio"]) + len(d["deleted_on_pc"]) + len(d["orphans"]))
    if d["awaiting_review"]:
        print(f"\n{len(d['awaiting_review'])} morceau(x) classes attendent leur verdict "
              f"-> analyse.bat (ils ne sont pas censes etre sur le serveur).")
    if not total and not d["not_indexed"] and not d["awaiting_upload"] \
            and not d["awaiting_review"]:
        print("\nBibliotheques iso — rien a faire.")
    return total


# ------------------------------ application ------------------------------

def apply_local(rows, delete_local):
    """Sens A : le morceau n'est plus sur la radio, on le retire des bacs locaux.

    Par defaut il part dans New_prog/_ecartes/<bac>/ plutot qu'a la poubelle :
    la decision de le sortir de l'antenne a deja ete prise, celle de perdre le
    fichier non."""
    done = []
    for bac, name in rows:
        src = os.path.join(LOCAL_ROOT, bac, name)
        if not os.path.isfile(src):
            continue
        try:
            if delete_local:
                os.remove(src)
            else:
                dst_dir = os.path.join(LOCAL_ROOT, QUARANTINE, bac)
                os.makedirs(dst_dir, exist_ok=True)
                os.replace(src, os.path.join(dst_dir, name))
            print(f"  [OK] {'supprime' if delete_local else 'range'} : {bac}/{name}")
            done.append((bac, name))
        except OSError as e:
            print(f"  [ECHEC] {bac}/{name} : {e}")
    return done


def apply_server(rows):
    """Sens D : le morceau n'est plus sur le PC, on le retire d'AzuraCast."""
    done = []
    for bac, name, media_id in rows:
        status, res = call("DELETE", f"/station/{STATION}/file/{media_id}")
        if status not in (200, 204):
            print(f"  [ECHEC] {bac}/{name} : {status} {res}")
            continue
        print(f"  [OK] supprime d'AzuraCast : {bac}/{name}")
        done.append((bac, name))
    return done


def prune_metadata(meta, keys):
    """Retire des entrees de metadata.json (meme principe que
    prune_deleted_tracks.py / clean_clapcrate_full.py)."""
    if meta is None or not keys:
        return
    before = len(meta)
    kept = [e for e in meta if meta_key(e) not in keys]
    if len(kept) == before:
        return
    with open(METADATA_PATH, "w", encoding="utf-8") as fh:
        json.dump(kept, fh, ensure_ascii=False, indent=1)
    print(f"metadata.json : {before - len(kept)} entree(s) retiree(s) "
          f"(avant {before}, apres {len(kept)}).")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bins", nargs="*", metavar="BAC",
                    help="bacs a comparer (tous par defaut) : " + ", ".join(NEW_BINS))
    ap.add_argument("--apply", action="store_true", help="ecrire reellement (sinon dry-run)")
    ap.add_argument("--delete-local", action="store_true",
                    help="effacer les fichiers locaux au lieu de les ranger dans _ecartes/")
    ap.add_argument("--no-sftp", action="store_true",
                    help="ne pas se connecter en SFTP (le sens PC sera alors desactive)")
    ap.add_argument("--only-server", action="store_true", help="n'agir que sur AzuraCast")
    ap.add_argument("--only-local", action="store_true", help="n'agir que sur les fichiers locaux")
    args = ap.parse_args()

    bins = list(args.bins) or NEW_BINS
    inconnus = [b for b in bins if b not in NEW_BINS]
    if inconnus:
        sys.exit(f"Bac(s) inconnu(s) : {', '.join(inconnus)}. Attendus : {', '.join(NEW_BINS)}")
    d = diagnose(bins, use_sftp=not args.no_sftp)
    total = report(d)

    if not args.apply:
        if total:
            print("\nDRY-RUN — rien n'a ete modifie. Relance avec --apply.")
        return

    keys = set()
    # Sens A : desactive tant qu'on n'a pas la vue SFTP (cf. cas B).
    if d["deleted_on_radio"] and not args.only_server:
        if d["sftp"] is None:
            print("\nSens PC ignore : pas de vue SFTP pour confirmer les suppressions.")
        else:
            print("\nRetrait des fichiers locaux :")
            keys |= set(apply_local(d["deleted_on_radio"], args.delete_local))
    if d["deleted_on_pc"] and not args.only_local:
        print("\nSuppression sur AzuraCast :")
        keys |= set(apply_server(d["deleted_on_pc"]))
    keys |= set(d["orphans"])
    prune_metadata(d["meta"], keys)
    print("\nTermine. Relance sans --apply pour verifier que les deux cotes sont iso.")


if __name__ == "__main__":
    main()
