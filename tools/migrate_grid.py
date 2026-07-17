#!/usr/bin/env python3
"""Migration one-shot : grille 4 creneaux -> 8 bacs "horloge a bacs ponderes".

Modele radio pro (FIP/Radio Meuh) : des BACS curates (genre d'abord, energie
ensuite), une HORLOGE cote AzuraCast (playlists planifiees + poids), la variete
quotidienne assuree par le mode Shuffled + Avoid Duplicate Artists/Titles.
L'ordre de lecture n'est plus jamais calcule localement (plus de prefixe NNN_).

    1_chill      Ambient, Downtempo, deep house lente, jungle chill
    2_groove     Disco, Funk, Soul, Boogie, Nu-Disco, house solaire
    3_house      House eclectique diurne, UK Garage, Electro mid-tempo
    4_deep       House deep/melodique crepusculaire, trance douce
    5_clubhouse  Tech house / house club, Speed Garage, Electro energique
    6_techno     Techno, trance energique, jungle tres club (>= 0.70)
    7_nightdub   Deep/minimal/dub techno (< 0.6)
    8_jungle     PONCTUATION : jungle/dnb 0.45-0.70 (1 titre / 14 chansons, nuit)

Usage :
    python migrate_grid.py            # dry-run : rapport seul, rien n'est deplace
    python migrate_grid.py --apply    # deplace les fichiers + metadata.json + script WinSCP

Garde-fou : refuse de tourner tant que _incoming contient des fichiers a
traiter (triage pas fini) — la classification part du metadata.json complet.

La classification doit rester coherente avec classify_bin() dans
triage_new_tracks.py une fois la grille en place.
"""
import csv
import json
import os
import shutil
import sys
import re

ROOT = r"C:\Users\ph.dufourcq\Music\00_AZURACAST"
NEW_PROG = os.path.join(ROOT, "New_prog")
INCOMING = os.path.join(ROOT, "_incoming")
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
METADATA = os.path.join(TOOLS_DIR, "metadata.json")
REPORT_CSV = os.path.join(TOOLS_DIR, "migration_report.csv")
SFTP_SCRIPT = os.path.join(TOOLS_DIR, "migration_sftp.txt")

OLD_SLOTS = ["1_morning", "2_afternoon", "3_evening", "4_night"]

from classify_bins import (  # source de verite unique de la grille  # noqa: E402
    NEW_BINS, ROTATION_BINS,
    top_genre, compute_energies, compute_cutoffs, classify_bin,
)

PREFIX_RE = re.compile(r"^\d{3}_")
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aiff", ".m4a", ".ogg"}
FALLBACK_DURATION_S = 6 * 60

# Prefixe distant pour le script WinSCP (racine media AzuraCast vue du SFTP).
# A adapter si l'arborescence serveur differe.
REMOTE_PREFIX = "/"


def incoming_pending():
    """Fichiers audio encore a traiter a la racine de _incoming."""
    if not os.path.isdir(INCOMING):
        return 0
    count = 0
    for name in os.listdir(INCOMING):
        p = os.path.join(INCOMING, name)
        if os.path.isfile(p) and os.path.splitext(name)[1].lower() in AUDIO_EXTS:
            count += 1
    return count


def read_duration(path):
    try:
        import mutagen
        audio = mutagen.File(path)
        if audio is not None and audio.info and audio.info.length:
            return float(audio.info.length)
    except Exception:
        pass
    return FALLBACK_DURATION_S


def unique_target(folder, name):
    """Evite d'ecraser un fichier existant (doublon de nom) : suffixe _2, _3..."""
    base, ext = os.path.splitext(name)
    candidate = os.path.join(folder, name)
    i = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base}_{i}{ext}")
        i += 1
    return candidate


def main():
    apply_mode = "--apply" in sys.argv

    pending = incoming_pending()
    if pending:
        print(f"REFUS : {pending} fichier(s) audio encore a traiter dans _incoming.")
        print("Attendre la fin du triage (triage.bat) avant de migrer.")
        sys.exit(1)

    with open(METADATA, encoding="utf-8") as f:
        tracks = json.load(f)
    print(f"{len(tracks)} morceaux dans metadata.json")

    energies = compute_energies(tracks)
    cut = compute_cutoffs(tracks, energies)
    print("\nSeuils calibres sur la bibliotheque (percentiles par famille) :")
    for k in sorted(cut):
        print(f"  {k:<18} {cut[k]:.3f}")

    moves = []          # (track, energy, old_path, bin)
    missing = []
    for t, energy in zip(tracks, energies):
        path = t.get("path", "")
        if not os.path.isfile(path):
            missing.append(path)
            continue
        b = classify_bin(top_genre(t.get("genres")), energy, t.get("mood"), cut)
        moves.append((t, energy, path, b))

    if missing:
        print(f"ATTENTION : {len(missing)} chemin(s) de metadata.json introuvable(s) sur disque :")
        for p in missing[:10]:
            print(f"  - {p}")
        if len(missing) > 10:
            print(f"  ... et {len(missing) - 10} autres")

    # Controle vetos : aucun techno / jungle non-chill en 1_chill / 2_groove
    veto_violations = []
    for t, energy, path, b in moves:
        g = top_genre(t.get("genres")).lower()
        if b in ("1_chill", "2_groove") and "techno" in g:
            veto_violations.append(path)
        if b == "2_groove" and any(k in g for k in ("jungle", "dnb", "drum")):
            veto_violations.append(path)
    print(f"\nControle vetos (techno/jungle en chill/groove) : "
          f"{'OK, aucune violation' if not veto_violations else str(len(veto_violations)) + ' VIOLATION(S) !'}")

    # Rapport : effectifs + heures estimees par bac
    print("\nRepartition dans les 8 bacs :")
    print(f"{'bac':<13} {'morceaux':>8} {'heures':>8}")
    total_h = 0.0
    bin_counts = {b: 0 for b in NEW_BINS}
    bin_hours = {b: 0.0 for b in NEW_BINS}
    for t, energy, path, b in moves:
        bin_counts[b] += 1
        bin_hours[b] += read_duration(path) / 3600
    for b in NEW_BINS:
        total_h += bin_hours[b]
        flag = ""
        if b in ROTATION_BINS and bin_hours[b] < 4:
            flag = "  <-- ANOREXIQUE (< 4h)"
        elif b == "8_jungle":
            flag = "  (ponctuation, pas de seuil)"
        print(f"{b:<13} {bin_counts[b]:>8} {bin_hours[b]:>7.1f}h{flag}")
    print(f"{'TOTAL':<13} {len(moves):>8} {total_h:>7.1f}h")

    # CSV detaille de tous les deplacements prevus
    with open(REPORT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ancien_chemin", "bac", "energie", "sous_genre"])
        for t, energy, path, b in moves:
            w.writerow([path, b, f"{energy:.3f}", top_genre(t.get("genres"))])
    print(f"\nDetail complet : {REPORT_CSV}")

    if not apply_mode:
        print("\nDRY-RUN termine — rien n'a ete deplace. Relancer avec --apply pour migrer.")
        return

    # ---- APPLY ----
    print("\nAPPLY : deplacement des fichiers...")
    for b in NEW_BINS:
        os.makedirs(os.path.join(NEW_PROG, b), exist_ok=True)

    new_paths = {}
    sftp_lines = [f'# Script WinSCP genere par migrate_grid.py — renames cote serveur.',
                  f'# ATTENTION : suppose que les noms de fichiers serveur = noms locaux',
                  f'# AVANT migration. Si le serveur a d\'autres noms (vieux uploads),',
                  f'# preferer une synchro WinSCP complete des nouveaux dossiers.',
                  f'# Adapter REMOTE_PREFIX ({REMOTE_PREFIX}) si besoin.']
    for b in NEW_BINS:
        sftp_lines.append(f'mkdir "{REMOTE_PREFIX}{b}"')
    moved = 0
    for t, energy, path, b in moves:
        old_name = os.path.basename(path)
        name = PREFIX_RE.sub("", old_name)  # retire le prefixe NNN_ : plus d'ordre encode
        target = unique_target(os.path.join(NEW_PROG, b), name)
        shutil.move(path, target)
        new_paths[path] = target
        old_slot = os.path.basename(os.path.dirname(path))
        sftp_lines.append(f'mv "{REMOTE_PREFIX}{old_slot}/{old_name}" "{REMOTE_PREFIX}{b}/{os.path.basename(target)}"')
        moved += 1
    print(f"{moved} fichiers deplaces.")

    with open(SFTP_SCRIPT, "w", encoding="utf-8") as f:
        f.write("\n".join(sftp_lines) + "\n")
    print(f"Script WinSCP : {SFTP_SCRIPT}")

    # metadata.json : mise a jour des chemins
    for t in tracks:
        old = t.get("path", "")
        if old in new_paths:
            t["path"] = new_paths[old]
    with open(METADATA, "w", encoding="utf-8") as f:
        json.dump(tracks, f, ensure_ascii=False, indent=1)
    print("metadata.json mis a jour.")

    # Verification post-apply : tous les chemins doivent exister
    broken = [t["path"] for t in tracks if not os.path.isfile(t.get("path", ""))]
    if broken:
        print(f"ATTENTION : {len(broken)} chemin(s) casse(s) apres migration !")
        for p in broken[:10]:
            print(f"  - {p}")
    else:
        print("Verification OK : tous les chemins de metadata.json existent.")

    # Anciens dossiers : supprimes seulement s'ils sont vides
    for s in OLD_SLOTS:
        folder = os.path.join(NEW_PROG, s)
        if os.path.isdir(folder):
            if not os.listdir(folder):
                os.rmdir(folder)
                print(f"Supprime (vide) : {folder}")
            else:
                print(f"CONSERVE (non vide, a verifier a la main) : {folder}")

    print("\nMigration terminee. Prochaines etapes : mettre a jour triage_new_tracks.py,")
    print("marquer build/export superseded, puis configurer les playlists AzuraCast.")


if __name__ == "__main__":
    main()
