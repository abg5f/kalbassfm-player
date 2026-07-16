#!/usr/bin/env python3
"""Migration one-shot : grille 4 creneaux -> grille 6 creneaux "arc d'ambiance".

    1_sunrise    06h-09h  Eveil doux        (ambient, downtempo, deep house lente)
    2_groove     09h-13h  Groove solaire    (disco, funk, soul, nu-disco, house groovy)
    3_breeze     13h-17h  Eclectique        (house, UK garage, electro mid-tempo)
    4_sunset     17h-20h  Coucher de soleil (deep/melodic house)
    5_club       20h-00h  Club              (tech house, techno, jungle/dnb, speed garage)
    6_deep_night 00h-06h  Nuit profonde     (deep/minimal techno, redescente)

Usage :
    python migrate_grid.py            # dry-run : rapport seul, rien n'est deplace
    python migrate_grid.py --apply    # deplace les fichiers + met a jour metadata.json

Pattern dry-run/--apply habituel du projet. Garde-fou : refuse de tourner tant
que _incoming contient encore des fichiers a traiter (triage pas fini) — la
classification doit partir du metadata.json complet post-triage.

La classification (genre d'abord, energie ensuite) doit rester coherente avec
classify_slot() dans triage_new_tracks.py une fois la grille en place.
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
METADATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata.json")
REPORT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migration_report.csv")

OLD_SLOTS = ["1_morning", "2_afternoon", "3_evening", "4_night"]
NEW_SLOTS = ["1_sunrise", "2_groove", "3_breeze", "4_sunset", "5_club", "6_deep_night"]

# Courbes (debut, fin) sur 0-1 — memes valeurs a reporter dans build_rotation.py
# et triage_new_tracks.py au moment de la bascule.
NEW_CURVES = {
    "1_sunrise":    (0.15, 0.40),
    "2_groove":     (0.35, 0.60),
    "3_breeze":     (0.45, 0.65),
    "4_sunset":     (0.50, 0.70),
    "5_club":       (0.65, 0.90),
    "6_deep_night": (0.70, 0.25),
}

# Seuils de la classification multi-criteres — ajustables si un creneau
# ressort anorexique au dry-run.
JUNGLE_CLUB_ENERGY = 0.55   # jungle/dnb : >= -> club, sinon deep_night
GARAGE_CLUB_ENERGY = 0.60   # garage : >= (ou speed garage) -> club, sinon breeze
TECHNO_CLUB_ENERGY = 0.60   # techno : >= -> club, sinon deep_night
HOUSE_SUNRISE_MAX  = 0.35   # house : < -> sunrise
HOUSE_DAY_MAX      = 0.55   # house : < -> groove/breeze (selon mood)
HOUSE_SUNSET_MAX   = 0.68   # house : < -> sunset, sinon club
HOUSE_GROOVE_MOOD  = 0.50   # house diurne : (happy+party)/2 >= -> groove, sinon breeze

PREFIX_RE = re.compile(r"^\d{3}_")
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aiff", ".m4a", ".ogg"}
FALLBACK_DURATION_S = 6 * 60  # si mutagen ne sait pas lire la duree


def incoming_pending():
    """Fichiers audio encore a traiter a la racine de _incoming (hors _duplicates/_failed)."""
    if not os.path.isdir(INCOMING):
        return 0
    count = 0
    for name in os.listdir(INCOMING):
        p = os.path.join(INCOMING, name)
        if os.path.isfile(p) and os.path.splitext(name)[1].lower() in AUDIO_EXTS:
            count += 1
    return count


def top_genre(genres):
    """Sous-genre Discogs du genre le mieux score ("Categorie---Sous-genre")."""
    if not genres:
        return ""
    label = genres[0][0] if isinstance(genres[0], (list, tuple)) else str(genres[0])
    return label.split("---")[-1].strip()


def compute_energies(tracks):
    """Energie 0-1 par morceau — meme formule que build_rotation.py :
    0.5*rms normalise + 0.3*bpm normalise + 0.2*mood party."""
    def norm(values):
        lo, hi = min(values), max(values)
        span = (hi - lo) or 1.0
        return [(v - lo) / span for v in values]

    rms_n = norm([t.get("rms", 0.0) for t in tracks])
    bpm_n = norm([t.get("bpm", 0.0) for t in tracks])
    energies = []
    for t, r, b in zip(tracks, rms_n, bpm_n):
        party = (t.get("mood") or {}).get("party", 0.0)
        energies.append(0.5 * r + 0.3 * b + 0.2 * party)
    return energies


def classify(subgenre, energy, mood):
    """Regles genre-d'abord, energie-ensuite de la grille arc d'ambiance."""
    g = subgenre.lower()
    mood = mood or {}

    if any(k in g for k in ("ambient", "downtempo", "trip hop", "trip-hop")):
        return "1_sunrise"
    if any(k in g for k in ("disco", "funk", "soul", "boogie")):
        return "2_groove"
    if any(k in g for k in ("jungle", "drum n bass", "drum & bass", "drum and bass", "dnb", "d&b")):
        return "5_club" if energy >= JUNGLE_CLUB_ENERGY else "6_deep_night"
    if "garage" in g or "bassline" in g:
        return "5_club" if ("speed" in g or energy >= GARAGE_CLUB_ENERGY) else "3_breeze"
    if "techno" in g:
        return "5_club" if energy >= TECHNO_CLUB_ENERGY else "6_deep_night"
    if "house" in g:
        if energy < HOUSE_SUNRISE_MAX:
            return "1_sunrise"
        if energy < HOUSE_DAY_MAX:
            grooviness = (mood.get("happy", 0.0) + mood.get("party", 0.0)) / 2
            return "2_groove" if grooviness >= HOUSE_GROOVE_MOOD else "3_breeze"
        if energy < HOUSE_SUNSET_MAX:
            return "4_sunset"
        return "5_club"

    # Fallback (electro, trance, synth-pop...) : milieu de courbe le plus proche.
    def midpoint(curve):
        return (curve[0] + curve[1]) / 2
    return min(NEW_CURVES, key=lambda s: abs(energy - midpoint(NEW_CURVES[s])))


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

    moves = []          # (track, energy, old_path, new_slot)
    missing = []
    for t, energy in zip(tracks, energies):
        path = t.get("path", "")
        if not os.path.isfile(path):
            missing.append(path)
            continue
        slot = classify(top_genre(t.get("genres")), energy, t.get("mood"))
        moves.append((t, energy, path, slot))

    if missing:
        print(f"ATTENTION : {len(missing)} chemin(s) de metadata.json introuvable(s) sur disque :")
        for p in missing[:10]:
            print(f"  - {p}")
        if len(missing) > 10:
            print(f"  ... et {len(missing) - 10} autres")

    # Rapport : effectifs + heures estimees par creneau
    print("\nRepartition dans la nouvelle grille :")
    print(f"{'creneau':<14} {'morceaux':>8} {'heures':>8}")
    total_h = 0.0
    slot_counts = {s: 0 for s in NEW_SLOTS}
    slot_hours = {s: 0.0 for s in NEW_SLOTS}
    for t, energy, path, slot in moves:
        slot_counts[slot] += 1
        slot_hours[slot] += read_duration(path) / 3600
    for s in NEW_SLOTS:
        total_h += slot_hours[s]
        flag = "  <-- ANOREXIQUE (< 4h)" if slot_hours[s] < 4 else ""
        print(f"{s:<14} {slot_counts[s]:>8} {slot_hours[s]:>7.1f}h{flag}")
    print(f"{'TOTAL':<14} {len(moves):>8} {total_h:>7.1f}h")

    # CSV detaille de tous les deplacements prevus
    with open(REPORT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ancien_chemin", "nouveau_creneau", "energie", "sous_genre"])
        for t, energy, path, slot in moves:
            w.writerow([path, slot, f"{energy:.3f}", top_genre(t.get("genres"))])
    print(f"\nDetail complet : {REPORT_CSV}")

    if not apply_mode:
        print("\nDRY-RUN termine — rien n'a ete deplace. Relancer avec --apply pour migrer.")
        return

    # ---- APPLY ----
    print("\nAPPLY : deplacement des fichiers...")
    for s in NEW_SLOTS:
        os.makedirs(os.path.join(NEW_PROG, s), exist_ok=True)

    new_paths = {}
    moved = 0
    for t, energy, path, slot in moves:
        name = PREFIX_RE.sub("", os.path.basename(path))  # retire le prefixe NNN_ obsolete
        target = unique_target(os.path.join(NEW_PROG, slot), name)
        shutil.move(path, target)
        new_paths[path] = target
        moved += 1
    print(f"{moved} fichiers deplaces.")

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

    print("\nMigration terminee. Prochaines etapes : mettre a jour build_rotation.py,")
    print("triage_new_tracks.py, export_rotation.py puis regenerer la rotation.")


if __name__ == "__main__":
    main()
