#!/usr/bin/env python3
"""Verifie que les 9 bacs locaux (New_prog/<bac>) sont iso avec la station
AzuraCast (meme liste de fichiers, bac par bac). Lecture seule, ne modifie rien.

Usage : python check_local_vs_server.py
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import paramiko

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)
from sftp_config import SFTP_HOST, SFTP_PORT, SFTP_USER, SFTP_PASS, SFTP_REMOTE_ROOT  # noqa: E402

LOCAL_ROOT = r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog"
BINS = ["1_chill", "2_groove", "3_house", "4_deep", "5_clubhouse",
        "6_techno", "7_nightdub", "8_jungle", "9_liquid"]


def local_files(bin_name):
    d = os.path.join(LOCAL_ROOT, bin_name)
    if not os.path.isdir(d):
        return set()
    return {f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))}


def main():
    print(f"Connexion SFTP {SFTP_HOST}:{SFTP_PORT}...")
    transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    transport.connect(username=SFTP_USER, password=SFTP_PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)

    total_only_local, total_only_remote = 0, 0
    try:
        for b in BINS:
            loc = local_files(b)
            remote_dir = SFTP_REMOTE_ROOT.rstrip("/") + "/" + b
            try:
                rem = {e.filename for e in sftp.listdir_attr(remote_dir)
                       if not e.filename.startswith(".")}
            except FileNotFoundError:
                rem = set()

            only_local = loc - rem
            only_remote = rem - loc
            total_only_local += len(only_local)
            total_only_remote += len(only_remote)

            status = "OK" if not only_local and not only_remote else "ECART"
            print(f"[{b}] local={len(loc)} serveur={len(rem)}  {status}")
            for f in sorted(only_local):
                print(f"    seulement en local  : {f}")
            for f in sorted(only_remote):
                print(f"    seulement sur serveur: {f}")
    finally:
        sftp.close()
        transport.close()

    print(f"\nTotal : {total_only_local} fichier(s) seulement en local, "
          f"{total_only_remote} seulement sur le serveur.")


if __name__ == "__main__":
    main()
