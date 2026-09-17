#!/usr/bin/env python3
"""Envoi SFTP vers AzuraCast — partage par le triage et l'analyse.

POURQUOI CE MODULE EXISTE : depuis que le classement (triage_new_tracks.py) et
le verdict d'antenne (analyse_new_tracks.py) sont deux etapes distinctes,
l'envoi appartient a la SECONDE. Mais la file d'attente des envois rates, elle,
doit rester lisible par les deux — et sync_library.py raisonne dessus (cas C).
Une seule implementation, un seul format de fichier, un seul endroit ou
corriger un bug d'upload.

DEUX FILES, QUI NE DISENT PAS LA MEME CHOSE
-------------------------------------------
pending_uploads.json  un envoi a ECHOUE (serveur injoignable, coupure) et sera
                      retente au prochain run. Le morceau a deja passe le
                      verdict : il a sa place a l'antenne, il n'y est pas
                      encore arrive.
pending_review.json   le morceau est classe localement et ATTEND SON VERDICT.
                      Il n'a jamais ete envoye, et il ne le sera peut-etre
                      jamais. Ecrit par le triage, consomme par l'analyse.

Les confondre reviendrait a envoyer sur l'antenne des morceaux que personne
n'a encore juges — exactement ce que la separation cherche a eviter.
"""
import json
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)

import paramiko  # noqa: E402
from sftp_config import (  # noqa: E402
    SFTP_HOST, SFTP_PORT, SFTP_USER, SFTP_PASS, SFTP_REMOTE_ROOT,
)

PENDING_UPLOADS_PATH = os.path.join(TOOLS_DIR, "pending_uploads.json")
PENDING_REVIEW_PATH = os.path.join(TOOLS_DIR, "pending_review.json")


# --------------------------------------------------------------------------- chemins

def to_current_platform(path):
    """Rend utilisable ICI un chemin ecrit par l'autre moitie du pipeline.

    Le triage tourne dans le venv WSL (chemins /mnt/c/...), l'analyse n'a
    besoin d'aucun modele Essentia et tourne donc en Python Windows (C:\\...).
    Les deux fichiers d'attente sont ecrits au format Windows, comme
    metadata.json — cette fonction fait la traduction dans l'autre sens quand
    le script tourne sous WSL, pour que le meme JSON serve aux deux.
    """
    if not path:
        return path
    if sys.platform.startswith("win"):
        return path.replace("/mnt/c", "C:").replace("/", "\\")
    return path.replace("C:\\", "/mnt/c/").replace("C:/", "/mnt/c/").replace("\\", "/")


def to_windows(path):
    """Format de stockage commun aux JSON du pipeline (cf. metadata.json)."""
    return path.replace("/mnt/c", "C:").replace("/", "\\")


# --------------------------------------------------------------------------- files d'attente

def _load(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return []


def _save(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)


def load_pending_uploads():
    return _load(PENDING_UPLOADS_PATH)


def save_pending_uploads(rows):
    _save(PENDING_UPLOADS_PATH, rows)


def load_pending_review():
    return _load(PENDING_REVIEW_PATH)


def save_pending_review(rows):
    _save(PENDING_REVIEW_PATH, rows)


# --------------------------------------------------------------------------- SFTP

class RemoteAlreadyExists(Exception):
    """Un fichier du meme nom existe deja dans le bac distant."""


class ConnexionPerdue(Exception):
    """La session SFTP est morte et la reconnexion a echoue : inutile d'insister."""


# Delai sans reponse du serveur au-dela duquel une operation SFTP echoue. Sans
# lui, une connexion coupee net peut bloquer un envoi indefiniment.
SFTP_TIMEOUT = 120


def open_sftp():
    """Ouvre la connexion SFTP vers AzuraCast. Retourne (transport, sftp) ou (None, None)."""
    try:
        transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
        transport.connect(username=SFTP_USER, password=SFTP_PASS)
        transport.set_keepalive(30)
        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.get_channel().settimeout(SFTP_TIMEOUT)
        return transport, sftp
    except Exception as e:
        print(f"[SFTP] Connexion impossible ({e}) — rien ne sera envoye ce run.")
        return None, None


def upload(sftp, slot, local_path):
    """Envoie local_path vers /<slot>/<nom> sur AzuraCast. Leve en cas d'echec.

    ENVOI DIRECT, SOUS LE NOM FINAL, ET VERIFIE. Le SFTP d'AzuraCast previent
    l'indexation a chaque fichier depose : un envoi en deux temps
    (`<nom>.part` puis renommage, essaye le 2026-09-16) declenchait une
    course entre cette indexation et le renommage — 24 morceaux sur 80 sont
    ressortis « unprocessable », complets sur le disque mais jamais a
    l'antenne. On envoie donc comme AzuraCast l'attend, et on se protege
    autrement : la taille distante est comparee a la locale APRES l'envoi
    (un fichier coupe en route est ainsi renvoye au prochain passage), et un
    fichier deja present mais PLUS PETIT que l'original est reconnu comme un
    envoi interrompu, pas comme un morceau deja en ligne.
    """
    local = to_current_platform(local_path)
    taille = os.path.getsize(local)
    remote_dir = SFTP_REMOTE_ROOT.rstrip("/") + "/" + slot
    remote_path = remote_dir + "/" + os.path.basename(local_path)
    try:
        sftp.stat(remote_dir)
    except FileNotFoundError:
        sftp.mkdir(remote_dir)
    # Garde-fou : ne jamais ecraser silencieusement un morceau deja en ligne.
    try:
        distant = sftp.stat(remote_path).st_size
    except FileNotFoundError:
        distant = None
    if distant is not None:
        if distant >= taille:
            raise RemoteAlreadyExists(remote_path)
        print(f"  [SFTP] {os.path.basename(remote_path)} tronque sur le serveur "
              f"({distant} / {taille} octets) -> renvoi complet")
    sftp.put(local, remote_path)
    arrive = sftp.stat(remote_path).st_size
    if arrive != taille:
        raise IOError(f"envoi incomplet : {arrive} / {taille} octets")


class Connexion:
    """Session SFTP qui se reconnecte quand le serveur coupe.

    Avant elle, une seule coupure reseau faisait echouer TOUS les envois
    suivants en rafale sur une session morte : le 2026-09-16, 0 envoye et 61
    echecs apres la coupure pendant Jackson 5.
    """

    def __init__(self):
        self.transport, self.sftp = open_sftp()

    def ok(self):
        return self.sftp is not None

    def close(self):
        for obj in (self.sftp, self.transport):
            try:
                if obj is not None:
                    obj.close()
            except Exception:                           # noqa: BLE001
                pass
        self.transport = self.sftp = None

    def send(self, slot, local_path):
        """upload() avec UNE reconnexion si la session est morte.

        Leve RemoteAlreadyExists, l'erreur d'origine si la session est saine
        (probleme propre a ce fichier), ou ConnexionPerdue si le serveur ne
        repond plus : l'appelant doit alors arreter et garder le reste en file.
        """
        try:
            return upload(self.sftp, slot, local_path)
        except RemoteAlreadyExists:
            raise
        except Exception as exc:
            # On rouvre meme si la session semble active : apres un delai
            # depasse, paramiko la garde ouverte alors qu'elle ne repond plus.
            print(f"  [SFTP] {exc} — reconnexion...")
            self.close()
            self.transport, self.sftp = open_sftp()
            if not self.ok():
                raise ConnexionPerdue(str(exc)) from exc
            return upload(self.sftp, slot, local_path)


def retry_pending_uploads(conn, on_success=None):
    """Retente les envois SFTP restes en echec lors d'un run precedent.

    Retourne la liste des entrees toujours en echec ; n'ecrit PAS le fichier :
    l'appelant reste seul proprietaire de l'ecriture, pour fusionner
    proprement avec les echecs du run courant.
    """
    pending = load_pending_uploads()
    if not pending:
        return []
    print(f"{len(pending)} envoi(s) AzuraCast en attente d'un run precedent...")
    still_pending = []
    for n, entry in enumerate(pending):
        slot, stored = entry["slot"], entry["path"]
        local = to_current_platform(stored)
        if not os.path.exists(local):
            # Fichier deplace/supprime manuellement depuis -> on abandonne le suivi.
            continue
        try:
            conn.send(slot, local)
            print(f"  [OK] {os.path.basename(local)} envoye (retry)")
            if on_success:
                on_success()
        except RemoteAlreadyExists:
            # Deja present sur le serveur : l'envoi precedent avait en fait
            # reussi malgre l'echec de sauvegarde de son statut. On considere
            # ce morceau traite -> evite une boucle d'echec infinie.
            print(f"  [OK] {os.path.basename(local)} deja sur le serveur (retry)")
            if on_success:
                on_success()
        except ConnexionPerdue as e:
            print(f"  [ECHEC] serveur injoignable ({e}) — {len(pending) - n} envoi(s) "
                  f"restent en attente.")
            still_pending.extend(pending[n:])
            break
        except Exception as e:
            print(f"  [ECHEC] {os.path.basename(local)}: {e}")
            still_pending.append(entry)
    return still_pending
