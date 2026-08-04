#!/usr/bin/env python3
"""
Nettoyage complet CLAPCRATE.COM : serveur (SFTP) + local + metadata.json

Étapes :
1. Connecte en SFTP, liste tous les fichiers dans les 8 bacs
2. Identifie les fichiers avec "clapcrate" dans le nom
3. Supprime sur le serveur
4. Supprime les fichiers audio locaux correspondants
5. Nettoie metadata.json (retire les entrées)
6. Régénère la table BPM

Usage :
    python clean_clapcrate_full.py            # dry-run : affiche ce qui sera retiré
    python clean_clapcrate_full.py --apply    # supprime effectivement
"""
import os
import sys
import json
import paramiko
from pathlib import Path
from mutagen import File as MFile

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
METADATA_PATH = os.path.join(TOOLS_DIR, "metadata.json")
NEW_PROG_LOCAL = r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog"
SLOTS = ["1_chill", "2_groove", "3_house", "4_deep", "5_clubhouse", "6_techno", "7_nightdub", "8_jungle"]
APPLY = "--apply" in sys.argv

# SFTP config
from sftp_config import SFTP_HOST, SFTP_PORT, SFTP_USER, SFTP_PASS, SFTP_REMOTE_ROOT

def sftp_connect():
    transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    transport.connect(username=SFTP_USER, password=SFTP_PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)
    return transport, sftp

def has_clapcrate_in_tags(path):
    """Retourne True si 'clapcrate' se trouve dans les tags ID3."""
    try:
        audio = MFile(path, easy=True)
        if not audio or audio.tags is None:
            return False
        for tag_name in ("artist", "title", "album", "comment"):
            values = audio.tags.get(tag_name, [])
            for val in values:
                if val and "clapcrate" in val.lower():
                    return True
        return False
    except Exception:
        return False

def main():
    print("=" * 70)
    print("NETTOYAGE CLAPCRATE.COM - Serveur SFTP + Local + Metadata")
    print("=" * 70)

    # Charge metadata.json
    with open(METADATA_PATH, encoding="utf-8") as f:
        metadata = json.load(f)
    print(f"\n[LOCAL] metadata.json charge : {len(metadata)} entrees\n")

    # Connecte SFTP
    print("[SFTP] Connexion a l'historique {SFTP_HOST}:{SFTP_PORT}...")
    try:
        transport, sftp = sftp_connect()
        print("[SFTP] OK\n")
    except Exception as e:
        print(f"[SFTP] Erreur connexion : {e}")
        print("      Continuant en mode local seul (pas de suppression serveur)\n")
        transport, sftp = None, None

    clapcrate_files = []  # (local_path, remote_path, basename)

    # Scan local + SFTP
    print("[LOCAL] Scan des fichiers locaux avec 'clapcrate' (nom ou tags)...")
    for slot in SLOTS:
        local_dir = os.path.join(NEW_PROG_LOCAL, slot)
        if not os.path.isdir(local_dir):
            continue
        for fname in os.listdir(local_dir):
            if not fname.lower().endswith(".mp3"):
                continue
            local_path = os.path.join(local_dir, fname)
            # Cherche dans le nom de fichier OU les tags ID3
            if "clapcrate" in fname.lower() or has_clapcrate_in_tags(local_path):
                remote_path = f"{SFTP_REMOTE_ROOT.rstrip('/')}/{slot}/{fname}"
                clapcrate_files.append((local_path, remote_path, fname))
                print(f"  -> {slot}/{fname}")

    if not clapcrate_files:
        print("  [OK] Aucun fichier CLAPCRATE detecte localement.\n")
    else:
        print(f"\n[!] {len(clapcrate_files)} fichier(s) CLAPCRATE trouves localement\n")

    # Scan SFTP si connecte
    if sftp:
        print("[SFTP] Scan des fichiers sur le serveur...")
        sftp_clapcrate = []
        for slot in SLOTS:
            remote_dir = f"{SFTP_REMOTE_ROOT.rstrip('/')}/{slot}"
            try:
                for item in sftp.listdir_attr(remote_dir):
                    if not item.filename.lower().endswith(".mp3"):
                        continue
                    if "clapcrate" in item.filename.lower():
                        remote_path = f"{remote_dir}/{item.filename}"
                        sftp_clapcrate.append((remote_path, item.filename, slot))
                        if (item.filename, remote_path, item.filename) not in clapcrate_files:
                            print(f"  -> [SFTP ONLY] {slot}/{item.filename}")
            except Exception as e:
                print(f"  [ERR] Scan {slot} : {e}")

        if sftp_clapcrate:
            print(f"\n[!] {len(sftp_clapcrate)} fichier(s) CLAPCRATE trouves sur le serveur")

    if not clapcrate_files and (not sftp or not sftp_clapcrate):
        print("\n[OK] Aucun fichier a nettoyer.")
        if sftp:
            sftp.close()
            transport.close()
        return

    # Dry-run info
    if not APPLY:
        print(f"\nDRY-RUN termine.")
        print(f"  - Local : {len(clapcrate_files)} fichier(s) a supprimer")
        if sftp:
            print(f"  - SFTP : {len(sftp_clapcrate)} fichier(s) a supprimer")
        print(f"\nRelancez avec --apply pour effectuer les suppressions.")
        if sftp:
            sftp.close()
            transport.close()
        return

    # APPLY MODE
    print("\n" + "=" * 70)
    print("[APPLY] Debut du nettoyage...")
    print("=" * 70 + "\n")

    # Supprime sur SFTP
    if sftp and sftp_clapcrate:
        print("[SFTP] Suppression sur le serveur...")
        deleted_sftp = 0
        for remote_path, fname, slot in sftp_clapcrate:
            try:
                sftp.remove(remote_path)
                print(f"  [OK] Supprime {slot}/{fname}")
                deleted_sftp += 1
            except Exception as e:
                print(f"  [ERR] Impossible supprimer {fname} : {e}")
        print(f"  -> {deleted_sftp} fichier(s) supprime(s) du serveur\n")

    # Supprime local + metadata
    print("[LOCAL] Suppression des fichiers locaux...")
    deleted_local = 0
    deleted_metadata = 0
    for local_path, _, fname in clapcrate_files:
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
                print(f"  [OK] Supprime {fname}")
                deleted_local += 1
            except Exception as e:
                print(f"  [ERR] Impossible supprimer {fname} : {e}")

    print(f"  -> {deleted_local} fichier(s) local supprime(s)\n")

    # Nettoie metadata.json
    print("[METADATA] Nettoyage de metadata.json...")
    clapcrate_paths = {p for p, _, _ in clapcrate_files}
    original_count = len(metadata)
    cleaned = [e for e in metadata if e.get("path") not in clapcrate_paths]
    deleted_metadata = original_count - len(cleaned)

    if deleted_metadata > 0:
        with open(METADATA_PATH, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=1)
        print(f"  [OK] Retire {deleted_metadata} entree(s) de metadata.json")
        print(f"       Avant : {original_count} | Apres : {len(cleaned)}\n")
    else:
        print(f"  [OK] Aucune entree CLAPCRATE dans metadata.json\n")

    print("=" * 70)
    print("[DONE] Nettoyage termine !")
    print("=" * 70)
    print(f"\nResume :")
    print(f"  - Fichiers locaux supprimes : {deleted_local}")
    print(f"  - Fichiers serveur supprimes : {len(sftp_clapcrate) if sftp else 0}")
    print(f"  - Entrees metadata supprimees : {deleted_metadata}")
    print(f"\nNote : Relancez export_bpm_table.py apres pour regenerer la table BPM.")

    if sftp:
        sftp.close()
        transport.close()

if __name__ == "__main__":
    main()
