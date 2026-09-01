#!/usr/bin/env python3
"""Synchronise le split 1_chill -> 9_liquid sur le serveur AzuraCast (LOT 1).

Complement de migrate_grid.py --filter=1_chill:9_liquid (deja applique en
local : les 79 fichiers liquid vivent maintenant dans New_prog/9_liquid/).
Cote serveur, deux operations distinctes par fichier, dans cet ordre STRICT :

  1) UPLOAD la copie locale (New_prog/9_liquid/<nom>) vers le SFTP AzuraCast,
     dossier 9_liquid/ (meme pattern que upload_to_azuracast() dans
     triage_new_tracks.py : paramiko + sftp_config.py).
  2) SUPPRIME l'ancienne copie serveur dans 1_chill/, et SEULEMENT apres avoir
     verifie par un stat() que la nouvelle copie est bien presente sur le
     serveur. Sans cette suppression le morceau reste dans les deux playlists
     AzuraCast et continue de sortir sur l'ancien bac (piege documente dans
     CONTEXT.md et le brief LOT 1).

La liste des 79 paires (ancien nom / nouveau nom) vient de
migration_report.csv, filtree sur nouveau_bac == 9_liquid — genere par le run
migrate_grid.py --filter=1_chill:9_liquid qui a precede ce script.

Dry-run par defaut (se connecte et fait l'etat des lieux via stat(), n'ecrit
rien) ; --apply pour executer upload + suppression.

Usage :
    python sync_liquid_bin.py            # dry-run : etat des lieux serveur
    python sync_liquid_bin.py --apply    # upload puis suppression des 79 fichiers
"""
import csv
import os
import re
import sys

import paramiko

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)
from sftp_config import SFTP_HOST, SFTP_PORT, SFTP_USER, SFTP_PASS, SFTP_REMOTE_ROOT  # noqa: E402

REPORT_CSV = os.path.join(TOOLS_DIR, "migration_report.csv")
LOCAL_LIQUID_DIR = r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog\9_liquid"
PREFIX_RE = re.compile(r"^\d{3}_")

OLD_BIN = "1_chill"
NEW_BIN = "9_liquid"


def load_pairs():
    """(nom_ancien_sur_serveur, nom_nouveau_sur_serveur) pour les lignes 1_chill -> 9_liquid."""
    pairs = []
    with open(REPORT_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["ancien_bac"] != OLD_BIN or row["nouveau_bac"] != NEW_BIN:
                continue
            old_name = os.path.basename(row["ancien_chemin"])
            new_name = PREFIX_RE.sub("", old_name)
            pairs.append((old_name, new_name))
    return pairs


def remote_path(bin_name, filename):
    return SFTP_REMOTE_ROOT.rstrip("/") + "/" + bin_name + "/" + filename


def remote_exists(sftp, path):
    try:
        sftp.stat(path)
        return True
    except FileNotFoundError:
        return False


def main():
    apply_mode = "--apply" in sys.argv

    pairs = load_pairs()
    if not pairs:
        print(f"Aucune ligne {OLD_BIN} -> {NEW_BIN} dans {REPORT_CSV}. Rien a faire.")
        return
    print(f"{len(pairs)} fichier(s) a synchroniser ({OLD_BIN} -> {NEW_BIN}).")

    print(f"Connexion SFTP {SFTP_HOST}:{SFTP_PORT}...")
    transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    transport.connect(username=SFTP_USER, password=SFTP_PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)
    try:
        remote_new_dir = remote_path(NEW_BIN, "").rstrip("/")
        try:
            sftp.stat(remote_new_dir)
        except FileNotFoundError:
            if apply_mode:
                sftp.mkdir(remote_new_dir)
                print(f"Dossier distant cree : {remote_new_dir}")
            else:
                print(f"[dry-run] dossier distant absent, sera cree : {remote_new_dir}")

        uploaded, deleted, skipped, failed = 0, 0, 0, 0
        for old_name, new_name in pairs:
            local_path = os.path.join(LOCAL_LIQUID_DIR, new_name)
            old_remote = remote_path(OLD_BIN, old_name)
            new_remote = remote_path(NEW_BIN, new_name)

            if not os.path.isfile(local_path):
                print(f"  [ECHEC] copie locale introuvable : {local_path}")
                failed += 1
                continue

            has_old = remote_exists(sftp, old_remote)
            has_new = remote_exists(sftp, new_remote)

            if not apply_mode:
                state = []
                state.append("ancien present" if has_old else "ancien absent")
                state.append("nouveau deja present" if has_new else "nouveau a envoyer")
                print(f"  [dry-run] {new_name} : {', '.join(state)}")
                continue

            if not has_new:
                sftp.put(local_path, new_remote)
                has_new = remote_exists(sftp, new_remote)
                if not has_new:
                    print(f"  [ECHEC] upload non confirme par stat() : {new_name}")
                    failed += 1
                    continue
                print(f"  [OK] envoye : {new_name}")
                uploaded += 1
            else:
                print(f"  [SKIP upload] deja present sur le serveur : {new_name}")

            # Suppression UNIQUEMENT apres confirmation stat() de la nouvelle copie.
            if has_old:
                sftp.remove(old_remote)
                print(f"  [OK] supprime ancienne copie : {OLD_BIN}/{old_name}")
                deleted += 1
            else:
                print(f"  [SKIP delete] deja absente : {OLD_BIN}/{old_name}")
                skipped += 1

        if apply_mode:
            print(f"\nTermine : {uploaded} envoye(s), {deleted} supprime(s), "
                  f"{skipped} deja propre(s), {failed} echec(s).")
        else:
            print("\nDRY-RUN termine — rien n'a ete envoye ni supprime. "
                  "Relancer avec --apply pour synchroniser.")
    finally:
        sftp.close()
        transport.close()


if __name__ == "__main__":
    main()
