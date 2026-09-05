#!/usr/bin/env python3
"""Filtre d'entree : dire d'un morceau CANDIDAT s'il a sa place a l'antenne.

Meme grille de lecture que review_energy.py (qui traite la bibliotheque deja
en place), mais applicable a UN morceau isole — donc utilisable par un outil
d'acquisition comme yt2slskd, avant ou juste apres le telechargement.

DEUX NIVEAUX, PARCE QU'ILS NE VOIENT PAS LA MEME CHOSE
------------------------------------------------------
`screen` — AVANT telechargement. N'a que du TEXTE (nom du fichier ou du
    resultat de recherche, duree, parfois un BPM colle au nom). Attrape ce qui
    s'annonce : hardcore, psytrance, gabber, sets d'une heure, intros de 40 s.
    Ne dira JAMAIS si un morceau est repetitif ou mixe trop fort — ces mesures
    n'existent pas sans le signal audio. C'est un filtre grossier, assume :
    il fait economiser des telechargements, il ne remplace pas l'analyse.

`audit` — APRES telechargement (ou sur un extrait de 60-90 s, ce qui suffit
    largement : yt-dlp --download-sections "*0:60-2:30" avant de rapatrier le
    fichier entier). La vraie analyse Essentia, celle qui a produit la revue
    d'ecoute : intensite, monotonie, ecart a la house, agressivite.

TROIS VERDICTS : keep (rien a signaler) / review (a ecouter avant diffusion) /
reject (n'a pas sa place en rotation). Aucun n'efface quoi que ce soit — c'est
l'appelant qui decide quoi en faire.

REFERENCE FIGEE : un percentile n'a de sens que rapporte a une distribution.
`refresh` fige celle de la bibliotheque dans gate_reference.json (quantiles
d'energie, de dynamic_complexity, de mood.aggressive, bornes de normalisation,
seuils de verdict). A relancer apres un gros ajout ou un gros nettoyage —
sinon les seuils decrivent une bibliotheque qui n'existe plus.

Usage :
    python track_gate.py refresh                     # (re)genere gate_reference.json
    python track_gate.py screen "Artist - Title 174" --duration 3600
    python track_gate.py screen --stdin < candidats.txt   # un JSON par ligne en sortie
    python track_gate.py audit fichier.mp3           # analyse Essentia + verdict
    python track_gate.py audit --desc descripteurs.json  # analyse deja faite ailleurs

INTEGRATION yt2slskd — le plus simple est le mode --stdin : un candidat par
ligne (texte brut, ou JSON {"name":..., "duration":..., "bitrate":...}), un
verdict JSON par ligne en sortie, dans le meme ordre. Un seul sous-processus
pour tout un lot de resultats de recherche. En Python, importer directement
screen_text() / score_descriptors() evite meme ce sous-processus.
"""
import argparse
import bisect
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)
from classify_bins import compute_energies, genre_family, top_genre  # noqa: E402

METADATA_PATH = os.path.join(TOOLS_DIR, "metadata.json")
REFERENCE_PATH = os.path.join(TOOLS_DIR, "gate_reference.json")

# Poids du score de risque — partages avec review_energy.py, qui les importe
# d'ici : une seule formule, un seul endroit ou la corriger.
WEIGHTS = {"intensite": 0.30, "monotonie": 0.25, "ecart_house": 0.25, "agressivite": 0.20}
BADGES = [
    ("intensite", 0.90, "🔥", "tres energique"),
    ("monotonie", 0.75, "🔁", "repetitif / peu de dynamique"),
    ("ecart_house", 0.65, "🧭", "s'ecarte de la house"),
    ("agressivite", 0.90, "😠", "agressif"),
]
HOUSE_FAMILIES = ("house", "groove", "garage")
HOUSE_BPM_LO, HOUSE_BPM_HI = 118, 132
BPM_SPREAD = 30.0

# Percentiles de la bibliotheque servant de seuils de verdict : ~3% de rejets,
# ~10% de mises en attente. Volontairement bas en rejet — un faux rejet coute
# un bon morceau perdu, un faux "review" coute une ecoute de 30 secondes.
REJECT_PCT, REVIEW_PCT = 0.97, 0.90


def houseness(track):
    """0-1 : a quel point le morceau est de la house au sens large.

    Meilleur score Discogs parmi les genres de famille house/disco/garage,
    pondere par l'ecart au tempo house. Genre inconnu -> 0.5 (on n'accuse pas
    sur une absence de donnee)."""
    genres = track.get("genres") or []
    if not genres:
        style = 0.5
    else:
        style = 0.0
        for entry in genres:
            label, score = (entry[0], entry[1]) if isinstance(entry, (list, tuple)) else (str(entry), 1.0)
            if genre_family(label.split("---")[-1].strip()) in HOUSE_FAMILIES:
                style = max(style, min(1.0, float(score)))
    return 0.7 * style + 0.3 * tempo_fit(track.get("bpm"))


def tempo_fit(bpm):
    """1 en plein coeur house, 0 au-dela de BPM_SPREAD d'ecart, 0.5 si inconnu."""
    bpm = float(bpm or 0.0)
    if bpm <= 0:
        return 0.5
    if HOUSE_BPM_LO <= bpm <= HOUSE_BPM_HI:
        return 1.0
    gap = HOUSE_BPM_LO - bpm if bpm < HOUSE_BPM_LO else bpm - HOUSE_BPM_HI
    return max(0.0, 1.0 - gap / BPM_SPREAD)


# ---------------------------- reference figee ----------------------------

def quantiles(values, n=101):
    """n points de la distribution triee (0e au 100e percentile)."""
    vals = sorted(values)
    if not vals:
        return []
    return [vals[min(len(vals) - 1, int(i / (n - 1) * len(vals)))] for i in range(n)]


def pct_of(value, table):
    """Percentile (0-1) d'une valeur dans une table de quantiles."""
    if not table:
        return 0.5
    return bisect.bisect_left(table, value) / (len(table) - 1)


def cmd_refresh(args):
    if not os.path.exists(METADATA_PATH):
        sys.exit("metadata.json introuvable — lance d'abord analyze_essentia.py.")
    with open(METADATA_PATH, encoding="utf-8") as fh:
        tracks = json.load(fh)
    energies = compute_energies(tracks)

    rms = [t.get("rms", 0.0) for t in tracks]
    bpm = [t.get("bpm", 0.0) for t in tracks]
    ref = {
        "generated_from": os.path.basename(METADATA_PATH),
        "tracks": len(tracks),
        # compute_energies normalise sur les min/max du LOT ; pour noter un
        # morceau isole il faut donc figer ces bornes ici, sinon la meme piste
        # obtiendrait une energie differente selon ce qu'on analyse avec elle.
        "bounds": {"rms": [min(rms), max(rms)], "bpm": [min(bpm), max(bpm)]},
        "quantiles": {
            "energy": quantiles(energies),
            "dynamic_complexity": quantiles([t.get("dynamic_complexity", 0.0) for t in tracks]),
            "aggressive": quantiles([(t.get("mood") or {}).get("aggressive", 0.0) for t in tracks]),
        },
        "weights": WEIGHTS,
    }
    scores = sorted(score_descriptors(t, ref)["score"] for t in tracks)
    ref["verdict"] = {
        "reject": scores[min(len(scores) - 1, int(REJECT_PCT * len(scores)))],
        "review": scores[min(len(scores) - 1, int(REVIEW_PCT * len(scores)))],
    }
    with open(REFERENCE_PATH, "w", encoding="utf-8") as fh:
        json.dump(ref, fh, ensure_ascii=False, indent=1)
    print(f"{len(tracks)} morceaux -> {REFERENCE_PATH}")
    print(f"  seuils : review >= {ref['verdict']['review']:.3f}, "
          f"reject >= {ref['verdict']['reject']:.3f} "
          f"({sum(1 for s in scores if s >= ref['verdict']['reject'])} morceaux de la "
          f"bibliotheque actuelle seraient rejetes)")


def load_reference():
    if not os.path.exists(REFERENCE_PATH):
        sys.exit(f"{os.path.basename(REFERENCE_PATH)} introuvable — lance "
                 f"`python track_gate.py refresh` (une fois, puis apres chaque gros lot).")
    with open(REFERENCE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------- audit (apres telechargement) -------------------------

def score_descriptors(desc, ref):
    """Quatre axes + score de risque d'un morceau, note contre la reference.

    `desc` : dict de descripteurs Essentia (bpm, rms, dynamic_complexity,
    mood, genres) — exactement ce que produit analyze_essentia.analyze()."""
    (rms_lo, rms_hi) = ref["bounds"]["rms"]
    (bpm_lo, bpm_hi) = ref["bounds"]["bpm"]

    def norm(v, lo, hi):
        return min(1.0, max(0.0, (float(v or 0.0) - lo) / ((hi - lo) or 1.0)))

    mood = desc.get("mood") or {}
    energy = (0.5 * norm(desc.get("rms"), rms_lo, rms_hi)
              + 0.3 * norm(desc.get("bpm"), bpm_lo, bpm_hi)
              + 0.2 * float(mood.get("party", 0.0)))
    q = ref["quantiles"]
    axes = {
        "intensite": pct_of(energy, q["energy"]),
        "monotonie": 1.0 - pct_of(float(desc.get("dynamic_complexity") or 0.0), q["dynamic_complexity"]),
        "ecart_house": 1.0 - houseness(desc),
        "agressivite": pct_of(float(mood.get("aggressive", 0.0)), q["aggressive"]),
    }
    weights = ref.get("weights", WEIGHTS)
    return {"axes": axes, "energy": energy,
            "score": sum(weights[k] * v for k, v in axes.items())}


def verdict_of(score, ref):
    v = ref["verdict"]
    if score >= v["reject"]:
        return "reject"
    if score >= v["review"]:
        return "review"
    return "keep"


def audit_descriptors(desc, ref=None):
    """Verdict complet d'un morceau analyse. Retourne un dict serialisable."""
    ref = ref or load_reference()
    scored = score_descriptors(desc, ref)
    axes = scored["axes"]
    reasons = [f"{label} ({axes[key]:.0%})" for key, mini, _, label in BADGES if axes[key] >= mini]
    return {
        "verdict": verdict_of(scored["score"], ref),
        "score": round(scored["score"], 3),
        "axes": {k: round(v, 3) for k, v in axes.items()},
        "bpm": round(float(desc.get("bpm") or 0.0)),
        "genre": top_genre(desc.get("genres")),
        "reasons": reasons,
        "stage": "audit",
    }


# ------------------------ screen (avant telechargement) ------------------------

# Familles annoncees dans le nom : poids = a quel point elles eloignent de la
# house. Le liquid DnB est revendique par la station ("100% House & some Liquid
# DnB"), il n'est donc pas penalise comme le reste du DnB.
FAR_FROM_HOUSE = [
    (0.95, ("hardcore", "gabber", "frenchcore", "uptempo", "speedcore", "terror", "hardstyle", "rawstyle")),
    (0.85, ("psytrance", "psy-trance", "psy trance", "goa", "fullon", "full-on", "hitech")),
    (0.80, ("metal", "punk", "hardrock", "screamo", "emo")),
    (0.75, ("schranz", "hard techno", "hardtechno", "industrial techno", "acidcore")),
    (0.65, ("dubstep", "riddim", "brostep", "neurofunk", "neuro", "crossbreed")),
    (0.55, ("trap", "phonk", "hyperpop", "drill")),
    (0.45, ("drum and bass", "drum & bass", "drum n bass", "dnb", "d&b", "jungle", "breakcore")),
    (0.35, ("trance", "hard house", "happy hardcore", "eurodance")),
]
LIQUID_HINTS = ("liquid", "soulful", "atmospheric", "rollers", "deep dnb")
# Ce qui n'est pas un morceau : sets, podcasts, interviews, intros.
NOT_A_TRACK = ("live set", "dj set", "podcast", "radio show", "livestream", "b2b",
               "mixtape", "essential mix", "boiler room", "full album", "interview",
               "tracklist", "megamix", "continuous mix")
BPM_IN_NAME = re.compile(r"(?:^|[\s\-_\[\(])(\d{2,3})(?:bpm)?(?:[\s\-_\]\)]|$)", re.I)
LONG_SET_SEC = 12 * 60   # au-dela, c'est un set, pas un titre
SHORT_CLIP_SEC = 100     # en deca, c'est une intro, un jingle ou un extrait


def parse_bpm(name):
    """BPM annonce dans le nom (convention du pipeline : "Titre 128.mp3").

    Ne retient que les valeurs plausibles pour un morceau : en dessous de 60 ou
    au-dessus de 210, c'est une annee, un numero de piste ou un identifiant."""
    best = None
    for m in BPM_IN_NAME.finditer(name):
        v = int(m.group(1))
        if 60 <= v <= 210:
            best = v  # le dernier gagne : le BPM est colle en fin de nom
    return best


def screen_text(name, duration=None, ref=None):
    """Verdict AVANT telechargement, a partir du seul nom (+ duree si connue).

    Volontairement conservateur : `reject` uniquement sur ce qui est explicite
    (genre annonce tres loin de la house, set d'une heure). Tout le reste passe
    en `keep`, quitte a etre repris par `audit` une fois le fichier la."""
    text = " " + re.sub(r"[_\.]+", " ", str(name or "")).lower() + " "
    reasons, penalty = [], 0.0

    for kw in NOT_A_TRACK:
        if kw in text:
            return {"verdict": "reject", "score": 1.0, "stage": "screen",
                    "reasons": [f"n'est pas un titre : « {kw} »"], "bpm": parse_bpm(text)}

    liquid = any(k in text for k in LIQUID_HINTS)
    for weight, keywords in FAR_FROM_HOUSE:
        hit = next((k for k in keywords if k in text), None)
        if not hit:
            continue
        w = weight * (0.4 if liquid else 1.0)  # liquid DnB : revendique par la station
        if w > penalty:
            penalty = w
            reasons = [f"genre annonce « {hit} »" + (" (liquid, tolere)" if liquid else "")]
        break

    bpm = parse_bpm(text)
    if bpm is not None:
        fit = tempo_fit(bpm)
        if fit < 1.0:
            penalty = max(penalty, 0.6 * (1.0 - fit))
            reasons.append(f"{bpm} BPM, hors du coeur house ({HOUSE_BPM_LO}-{HOUSE_BPM_HI})")

    # "100% House & some Liquid DnB" : le liquid est revendique par la station.
    # Son tempo (~172) et son etiquette DnB le condamneraient a chaque fois, on
    # plafonne donc sous le seuil de mise en attente. Les controles de duree
    # ci-dessous restent, eux, valables (un set liquid d'une heure reste un set).
    if liquid:
        penalty = min(penalty, 0.35)

    if duration:
        duration = float(duration)
        if duration >= LONG_SET_SEC:
            return {"verdict": "reject", "score": 1.0, "stage": "screen", "bpm": bpm,
                    "reasons": [f"duree {duration / 60:.0f} min : set ou album, pas un titre"]}
        if duration <= SHORT_CLIP_SEC:
            penalty = max(penalty, 0.7)
            reasons.append(f"duree {duration:.0f} s : intro, jingle ou extrait")

    verdict = "reject" if penalty >= 0.8 else ("review" if penalty >= 0.4 else "keep")
    return {"verdict": verdict, "score": round(penalty, 3), "stage": "screen",
            "bpm": bpm, "reasons": reasons}


# --------------------------------- CLI ---------------------------------

def cmd_screen(args):
    def emit(payload):
        if isinstance(payload, str):
            payload = {"name": payload}
        out = screen_text(payload.get("name") or payload.get("filename") or "",
                          payload.get("duration") or payload.get("length"))
        out["name"] = payload.get("name") or payload.get("filename") or ""
        print(json.dumps(out, ensure_ascii=False))

    if args.stdin:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                emit(json.loads(line) if line.startswith("{") else line)
            except ValueError:
                emit(line)
        return
    if not args.name:
        sys.exit("Usage : track_gate.py screen \"<nom du fichier>\" [--duration SECONDES]")
    emit({"name": " ".join(args.name), "duration": args.duration})


def cmd_audit(args):
    ref = load_reference()
    if args.desc:
        with open(args.desc, encoding="utf-8") as fh:
            desc = json.load(fh)
    else:
        if not args.file:
            sys.exit("Usage : track_gate.py audit <fichier audio> | --desc <descripteurs.json>")
        try:
            import analyze_essentia
        except ImportError as e:
            sys.exit(f"analyse Essentia indisponible ({e}) — lance ce mode depuis WSL2, "
                     f"ou passe des descripteurs deja calcules avec --desc.")
        desc = analyze_essentia.analyze(args.file)
    out = audit_descriptors(desc, ref)
    if args.file:
        out["file"] = args.file
    print(json.dumps(out, ensure_ascii=False, indent=None if args.json else 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("refresh", help="figer la distribution de la bibliotheque dans gate_reference.json")

    ps = sub.add_parser("screen", help="verdict avant telechargement (texte seul)")
    ps.add_argument("name", nargs="*", help="nom du fichier ou du resultat de recherche")
    ps.add_argument("--duration", type=float, help="duree en secondes, si connue")
    ps.add_argument("--stdin", action="store_true",
                    help="lire un candidat par ligne (texte ou JSON), ecrire un verdict JSON par ligne")

    pa = sub.add_parser("audit", help="verdict apres telechargement (analyse Essentia)")
    pa.add_argument("file", nargs="?", help="fichier audio (un extrait de 60-90 s suffit)")
    pa.add_argument("--desc", help="descripteurs Essentia deja calcules (JSON)")
    pa.add_argument("--json", action="store_true", help="sortie sur une seule ligne")

    args = ap.parse_args()
    {"refresh": cmd_refresh, "screen": cmd_screen, "audit": cmd_audit}[args.cmd](args)


if __name__ == "__main__":
    main()
