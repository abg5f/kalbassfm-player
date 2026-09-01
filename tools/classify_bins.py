#!/usr/bin/env python3
"""Classification partagee des morceaux dans les 9 bacs de la grille.

Source de verite unique pour la grille : utilisee par migrate_grid.py (migration
one-shot) et triage_new_tracks.py (nouveaux morceaux). Modele radio pro : des
bacs curates genre-d'abord/energie-ensuite, l'ordonnancement etant delegue a
AzuraCast — rotation continue ponderee depuis le 2026-08-31 (plus de creneaux
horaires fixes, cf. tools/apply_rotation.py), aucun ordre calcule ici.

    1_chill      Ambient, Downtempo, deep house lente
    2_groove     Disco, Funk, Soul, Boogie, Nu-Disco, house solaire
    3_house      House eclectique diurne, UK Garage, Electro mid-tempo
    4_deep       House deep/melodique crepusculaire, trance douce
    5_clubhouse  Tech house / house club, Speed Garage, Electro energique
    6_techno     Techno, trance energique, jungle tres club
    7_nightdub   Deep/minimal/dub techno
    8_jungle     PONCTUATION nocturne : jungle/dnb intermediaire
    9_liquid     Liquid drum & bass (jungle/DnB peu agressif)

Les seuils d'energie sont AUTO-CALIBRES par percentiles au sein de chaque
famille de genre (l'echelle d'energie est compressee, p95 global ~0.56, et
depend de la bibliotheque — des valeurs absolues seraient a retoucher sans
cesse). Les proportions SHARES restent valables quelle que soit la distribution.

LIMITE CONNUE DE L'AXE D'ENERGIE (constatee a l'antenne le 2026-07-28, quand
1_chill ne passait qu'en creneau matinal — la limite reste valable main-
tenant que le bac tourne 24h/24) :
energy = 0.5*rms + 0.3*bpm + 0.2*party, or le RMS mesure le NIVEAU DE MASTERING
autant que l'energie musicale. Une regle en percentile d'energie remplit donc
son bac avec les titres MIXES BAS, pas avec les titres calmes. Consequence
observee : 62 des 118 titres de 1_chill etaient a >=120 BPM (garage house a
126 BPM). Le bac chill a donc deux garde-fous qui ne dependent PAS du RMS :
  - house/genres inconnus : veto de tempo (CHILL_BPM_MAX) ;
  - jungle/DnB : percentile de mood.aggressive, pas d'energie — le BPM y est
    inutilisable (detecte en demi-tempo : 86 pour 172) et l'ancienne regle
    d'energie retenait la jungle old-school mixee bas (Source Direct, Dillinja)
    en laissant le vrai liquid DnB (Hybrid Minds, Monrroe, Whiney) en
    ponctuation nocturne, alors que c'est exactement la matiere "chill/travail".

BAC 9_LIQUID (separe de 1_chill le 2026-08-31) : le liquid DnB choisi par
mood.aggressive n'a plus sa place dans 1_chill. Mesure sur metadata.json :
1_chill contenait 156 titres dont 79 de liquid (51%), melangeant deux musiques
sans rapport — ambient/downtempo a 70-90 BPM et rouleaux liquid a ~170 BPM (le
BPM median releve, 87, est l'artefact CHILL_BPM_ARTIFACT). Tolerable tant que
chill ne passait qu'en creneau matinal, intenable en rotation continue 24h/24.
La SELECTION par mood.aggressive reste inchangee (cf. ci-dessus) ; seule la
DESTINATION change : 9_liquid au lieu de 1_chill.
"""

NEW_BINS = ["1_chill", "2_groove", "3_house", "4_deep", "5_clubhouse", "6_techno", "7_nightdub", "8_jungle", "9_liquid"]
ROTATION_BINS = [b for b in NEW_BINS if b != "8_jungle"]  # 8_jungle = ponctuation

# Tempo plafond du bac chill : au-dela, un titre est un titre de club quel
# que soit son niveau de mastering (et quoi qu'en disent mood.relaxed/party,
# qui decrivaient le garage house de 126 BPM comme "relaxed 0.85").
CHILL_BPM_MAX = 120
# Au-dela, une valeur de BPM est presque toujours un artefact de detection
# (tempo double sur un morceau lent, ou demi-tempo sur du DnB) : on ne l'oppose
# donc PAS a un titre etiquete ambient/downtempo. Entre les deux, le tempo est
# un vrai tempo de club et c'est l'etiquette de genre qui se trompe (verifie :
# 2 faux "Ambient" a 130 BPM contre 2 vrais lents lus 163-164).
CHILL_BPM_ARTIFACT = 145

SHARES = {
    "techno_nightdub":  0.45,  # techno : 45% les moins energiques -> 7_nightdub, le reste -> 6_techno
    "house_chill":      0.15,  # house : 15% les plus calmes -> 1_chill (SI tempo < CHILL_BPM_MAX)
    "house_day":        0.60,  # house : jusqu'au 60e percentile -> 2_groove/3_house (selon mood)
    "house_deep":       0.85,  # house : jusqu'au 85e percentile -> 4_deep, au-dela -> 5_clubhouse
    "jungle_liquid":    0.50,  # jungle : 50% les MOINS AGRESSIFS -> 9_liquid
    "jungle_club":      0.80,  # jungle : au-dela du 80e percentile d'energie -> 6_techno ; sinon -> 8_jungle
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

    # Seuil de liquidite : percentile d'AGRESSIVITE (pas d'energie) au sein de
    # la famille jungle/DnB — seul indicateur qui separe le liquid du ragga /
    # darkside dans cette bibliotheque (p50 ~= 0.16, distribution tres tassee
    # vers le bas : le fonds est deja majoritairement liquide).
    jungle_aggr = sorted(
        (t.get("mood") or {}).get("aggressive", 0.0)
        for t in tracks
        if genre_family(top_genre(t.get("genres"))) == "jungle"
    )

    cut = {
        "techno_nightdub": _percentile(techno, SHARES["techno_nightdub"]),
        "house_chill":     _percentile(house, SHARES["house_chill"]),
        "house_day":       _percentile(house, SHARES["house_day"]),
        "house_deep":      _percentile(house, SHARES["house_deep"]),
        "jungle_liquid":   _percentile(jungle_aggr, SHARES["jungle_liquid"]),
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


def _chill_tempo_ok(bpm):
    """Le bac chill n'accepte pas un tempo de club. `bpm=None` (appelant qui
    ne le fournit pas) = pas de veto, pour rester retrocompatible."""
    return bpm is None or bpm < CHILL_BPM_MAX


def classify_bin(subgenre, energy, mood, cut, bpm=None):
    """Regles genre-d'abord, energie-ensuite (seuils calibres par compute_cutoffs).
    Vetos structurels : techno et jungle agressive ne peuvent JAMAIS tomber en
    1_chill/2_groove, et rien au-dessus de CHILL_BPM_MAX n'entre dans 1_chill
    par la voie house/fallback (cf. LIMITE CONNUE DE L'AXE D'ENERGIE en tete de
    module)."""
    g = subgenre.lower()
    fam = genre_family(subgenre)
    mood = mood or {}

    if fam == "chill":
        # Un "ambient" a tempo de club franc est une erreur d'etiquette, pas un
        # titre calme (cas reel : deux titres a 130 BPM).
        if bpm is not None and CHILL_BPM_MAX <= bpm < CHILL_BPM_ARTIFACT:
            return "3_house"
        return "1_chill"
    if fam == "groove":
        return "2_groove"
    if fam == "jungle":
        # Liquide (peu agressif) -> bac dedie 9_liquid, c'est la matiere "DnB
        # pour travailler". Selection par mood.aggressive et NON par energie :
        # le RMS trie par niveau de mastering et retenait la jungle old-school
        # mixee bas en laissant le vrai liquid en ponctuation nocturne.
        # Destination 9_liquid (et non 1_chill) depuis le 2026-08-31 : les deux
        # musiques n'ont pas leur place dans le meme bac en rotation continue.
        if mood.get("aggressive", 1.0) < cut["jungle_liquid"]:
            return "9_liquid"
        if energy >= cut["jungle_club"]:
            return "6_techno"         # tres club : rotation Peak occasionnelle
        return "8_jungle"             # coeur du style : ponctuation nocturne
    if fam == "garage":
        return "5_clubhouse" if ("speed" in g or energy >= cut["garage_club"]) else "3_house"
    if fam == "techno":
        return "6_techno" if energy >= cut["techno_nightdub"] else "7_nightdub"
    if fam == "house":
        if energy < cut["house_chill"]:
            # Calme "au RMS" ne veut pas dire calme a l'oreille : un titre a
            # tempo club recale ici part en 3_house plutot qu'en 1_chill —
            # jamais en 2_groove, dont le profil (disco/funk energique) ne
            # convient pas non plus a un tempo de club mal classe.
            return "1_chill" if _chill_tempo_ok(bpm) else "3_house"
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
        return "1_chill" if _chill_tempo_ok(bpm) else "3_house"
    if energy < cut["fallback_house"]:
        return "3_house"
    if energy < cut["fallback_deep"]:
        return "4_deep"
    return "5_clubhouse"
