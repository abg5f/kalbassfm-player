#!/usr/bin/env python3
"""Classification partagee des morceaux dans les 8 bacs "horloge a bacs ponderes".

Source de verite unique pour la grille : utilisee par migrate_grid.py (migration
one-shot) et triage_new_tracks.py (nouveaux morceaux). Modele radio pro : des
bacs curates genre-d'abord/energie-ensuite, l'ordonnancement etant delegue a
AzuraCast (Shuffled + poids + separation artiste) — aucun ordre calcule ici.

    1_chill      Ambient, Downtempo, deep house lente, jungle chill
    2_groove     Disco, Funk, Soul, Boogie, Nu-Disco, house solaire
    3_house      House eclectique diurne, UK Garage, Electro mid-tempo
    4_deep       House deep/melodique crepusculaire, trance douce
    5_clubhouse  Tech house / house club, Speed Garage, Electro energique
    6_techno     Techno, trance energique, jungle tres club
    7_nightdub   Deep/minimal/dub techno
    8_jungle     PONCTUATION nocturne : jungle/dnb intermediaire

Les seuils d'energie sont AUTO-CALIBRES par percentiles au sein de chaque
famille de genre (l'echelle d'energie est compressee, p95 global ~0.56, et
depend de la bibliotheque — des valeurs absolues seraient a retoucher sans
cesse). Les proportions SHARES restent valables quelle que soit la distribution.
"""

NEW_BINS = ["1_chill", "2_groove", "3_house", "4_deep", "5_clubhouse", "6_techno", "7_nightdub", "8_jungle"]
ROTATION_BINS = [b for b in NEW_BINS if b != "8_jungle"]  # 8_jungle = ponctuation

SHARES = {
    "techno_nightdub":  0.45,  # techno : 45% les moins energiques -> 7_nightdub, le reste -> 6_techno
    "house_chill":      0.15,  # house : 15% les plus calmes -> 1_chill
    "house_day":        0.60,  # house : jusqu'au 60e percentile -> 2_groove/3_house (selon mood)
    "house_deep":       0.85,  # house : jusqu'au 85e percentile -> 4_deep, au-dela -> 5_clubhouse
    "jungle_chill":     0.30,  # jungle : 30% les plus calmes -> 1_chill (journee)
    "jungle_club":      0.80,  # jungle : au-dela du 80e percentile -> 6_techno ; entre les deux -> 8_jungle
    "garage_club":      0.60,  # garage : au-dela du 60e percentile (ou "speed") -> 5_clubhouse
    "fallback_chill":   0.20,  # genres inconnus : quantiles globaux
    "fallback_house":   0.55,
    "fallback_deep":    0.80,
}


def top_genre(genres):
    """Sous-genre Discogs du genre le mieux score ("Categorie---Sous-genre")."""
    if not genres:
        return ""
    label = genres[0][0] if isinstance(genres[0], (list, tuple)) else str(genres[0])
    return label.split("---")[-1].strip()


def compute_energies(tracks):
    """Energie 0-1 par morceau — formule historique du pipeline :
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


def genre_family(subgenre):
    """Famille de style pour la calibration percentile (premier match gagne)."""
    g = subgenre.lower()
    if any(k in g for k in ("ambient", "downtempo", "trip hop", "trip-hop")):
        return "chill"
    if any(k in g for k in ("disco", "funk", "soul", "boogie")):
        return "groove"
    if any(k in g for k in ("jungle", "drum n bass", "drum & bass", "drum and bass", "dnb", "d&b")):
        return "jungle"
    if "garage" in g or "bassline" in g:
        return "garage"
    if "techno" in g:
        return "techno"
    if "house" in g:
        return "house"
    return "autre"


def _percentile(sorted_vals, share):
    """Valeur au percentile `share` (0-1) d'une liste triee."""
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(share * len(sorted_vals)))
    return sorted_vals[idx]


def compute_cutoffs(tracks, energies):
    """Convertit les proportions SHARES en seuils d'energie absolus, calibres
    sur la distribution reelle de chaque famille. Retourne aussi le seuil de
    'grooviness' (mediane des house diurnes) pour le split groove/house."""
    by_family = {}
    for t, e in zip(tracks, energies):
        by_family.setdefault(genre_family(top_genre(t.get("genres"))), []).append(e)
    for fam in by_family:
        by_family[fam].sort()

    all_sorted = sorted(energies)
    techno = by_family.get("techno", [])
    house = by_family.get("house", [])
    jungle = by_family.get("jungle", [])
    garage = by_family.get("garage", [])

    cut = {
        "techno_nightdub": _percentile(techno, SHARES["techno_nightdub"]),
        "house_chill":     _percentile(house, SHARES["house_chill"]),
        "house_day":       _percentile(house, SHARES["house_day"]),
        "house_deep":      _percentile(house, SHARES["house_deep"]),
        "jungle_chill":    _percentile(jungle, SHARES["jungle_chill"]),
        "jungle_club":     _percentile(jungle, SHARES["jungle_club"]),
        "garage_club":     _percentile(garage, SHARES["garage_club"]),
        "fallback_chill":  _percentile(all_sorted, SHARES["fallback_chill"]),
        "fallback_house":  _percentile(all_sorted, SHARES["fallback_house"]),
        "fallback_deep":   _percentile(all_sorted, SHARES["fallback_deep"]),
    }

    # Seuil de grooviness : mediane des house "diurnes" — split 50/50 naturel
    # entre 2_groove et 3_house, quel que soit le profil mood de la bibliotheque.
    day_grooviness = sorted(
        ((t.get("mood") or {}).get("happy", 0.0) + (t.get("mood") or {}).get("party", 0.0)) / 2
        for t, e in zip(tracks, energies)
        if genre_family(top_genre(t.get("genres"))) == "house"
        and cut["house_chill"] <= e < cut["house_day"]
    )
    cut["house_grooviness"] = _percentile(day_grooviness, 0.5) if day_grooviness else 0.5
    return cut


def classify_bin(subgenre, energy, mood, cut):
    """Regles genre-d'abord, energie-ensuite (seuils calibres par compute_cutoffs).
    Vetos structurels : techno et jungle non-chill ne peuvent JAMAIS tomber en
    1_chill/2_groove."""
    g = subgenre.lower()
    fam = genre_family(subgenre)
    mood = mood or {}

    if fam == "chill":
        return "1_chill"
    if fam == "groove":
        return "2_groove"
    if fam == "jungle":
        if energy < cut["jungle_chill"]:
            return "1_chill"          # jungle chill : integrable en journee
        if energy >= cut["jungle_club"]:
            return "6_techno"         # tres club : rotation Peak occasionnelle
        return "8_jungle"             # coeur du style : ponctuation nocturne
    if fam == "garage":
        return "5_clubhouse" if ("speed" in g or energy >= cut["garage_club"]) else "3_house"
    if fam == "techno":
        return "6_techno" if energy >= cut["techno_nightdub"] else "7_nightdub"
    if fam == "house":
        if energy < cut["house_chill"]:
            return "1_chill"
        if energy < cut["house_day"]:
            grooviness = (mood.get("happy", 0.0) + mood.get("party", 0.0)) / 2
            return "2_groove" if grooviness >= cut["house_grooviness"] else "3_house"
        if energy < cut["house_deep"]:
            return "4_deep"
        return "5_clubhouse"
    if "electro" in g:
        return "5_clubhouse" if energy >= cut["fallback_deep"] else "3_house"
    if "trance" in g:
        return "6_techno" if energy >= cut["fallback_deep"] else "4_deep"

    # Fallback (synth-pop, latin, hip hop...) : quantiles globaux.
    if energy < cut["fallback_chill"]:
        return "1_chill"
    if energy < cut["fallback_house"]:
        return "3_house"
    if energy < cut["fallback_deep"]:
        return "4_deep"
    return "5_clubhouse"
