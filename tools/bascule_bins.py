#!/usr/bin/env python3
"""Transition vers les six bacs, sans jamais interrompre la diffusion.

L'IDEE QUI REND CECI SUR : sur AzuraCast, l'appartenance a une playlist est un
champ PAR FICHIER (Api_StationMedia.playlists), pas une regle de dossier. Un
morceau peut donc appartenir en meme temps a son ancienne playlist (qui passe
a l'antenne) et a sa nouvelle (qui dort, desactivee). On prepare tout a froid,
et la bascule se reduit a un basculement de drapeaux : aucun fichier ne bouge,
ni en local ni sur le serveur.

Consequence heureuse : les ecartes n'ont pas a etre supprimes. Ils restent
sur le serveur, rattaches a aucune playlist active. Hors antenne, recuperables
d'un clic. Le purgatoire du plan devient gratuit.

    --etat        ce qui existe, ce qui manque, ce qui serait rattache
    --creer       cree les playlists manquantes, DESACTIVEES
    --remplir     rattache chaque morceau a sa nouvelle playlist
    --dossiers    cree les dossiers distants et y accroche les playlists
    --deplacer    range les fichiers du serveur dans les nouveaux dossiers
    --local       range la bibliotheque locale de la meme facon
    --doser       profondeur de rotation reelle, a relancer apres enrichissement
    --basculer    active les nouvelles, desactive les anciennes
    --revenir     l'inverse exact de --basculer
    --nettoyer    supprime l'ancien monde, refuse tant que la bascule n'est pas faite

Chaque phase est un dry-run tant que --apply n'est pas donne, et chacune est
rejouable : elle recalcule un diff contre l'etat live et n'ecrit que l'ecart.

--nettoyer est le SEUL endroit irreversible. Desactiver se defait, supprimer
non. Il porte trois verrous et refuse de partir tant que la bascule n'est pas
faite : les anciennes playlists sont ce qui passe a l'antenne, les supprimer
avant ferait taire la station au lieu de la simplifier.

PIEGE AZURACAST, rappele ici parce qu'il decide de la forme du script : les
playlists SANS schedule_items ne sont pas dans le meme pool de tirage que
celles AVEC. AzuraCast tire exclusivement parmi les "scheduled" des qu'une
seule est eligible, en excluant les autres MEME A POIDS NON NUL. Toute
nouvelle playlist recoit donc un planning explicite, y compris les planchers
(00:00-23:59 et non "aucun planning").
"""
import argparse
import json
import ntpath
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)

from azuracast_config import AZURACAST_API_KEY  # noqa: E402
import analyse_new_tracks as ana  # noqa: E402  (racine locale, conversion de chemin)
import classify_new as cn  # noqa: E402

BASE = "https://kalbassfm.duckdns.org/api"
STATION = "kalbassfm"

# --------------------------------------------------------------------------- cible
# Plancher 24h/24 + boosts qui s'ajoutent dans leur fenetre. Le plancher est la
# garantie qu'aucun bac ne tombe jamais a zero : a 3h du matin un titre club
# peut passer, a 23h un sunrise peut tomber. C'est la que loge la surprise.
#
# Les poids ci-dessous viennent du plan approuve, qui visait des bacs de
# 272/236/240/318. Le classement a la main les a ramenes a 160/243/150/114 :
# --doser mesure l'ecart et propose le reglage. A refaire juste avant la
# bascule, une fois les playlists enrichies.

PLANCHER = {
    "sunrise": ("1_sunrise", 3),
    "solaire": ("2_solaire", 5),
    "sunset":  ("3_sunset",  5),
    "club":    ("4_club",    3),
}
BOOSTS = {
    "sunrise_matin": ("1_sunrise", 12, [(500, 1100)]),
    "sunrise_nuit":  ("1_sunrise",  6, [(100, 700)]),
    "solaire_jour":  ("2_solaire", 14, [(1000, 1800)]),
    "sunset_soir":   ("3_sunset",  13, [(1700, 2200)]),
    "club_nuit":     ("4_club",    16, [(2100, 300)]),
}
# `misc` est une PONCTUATION, pas un poids : un poids est un tirage independant,
# rien n'empeche deux misc d'affilee. once_per_x_songs garantit l'espacement par
# construction. Plus dense le jour, ou la monotonie guette dans les 13 heures de
# solaire et sunset qui n'ont que 4 a 6 BPM d'ecart interne.
PONCTUATION = {
    "misc_jour": ("5_misc", 10, [(300, 1900)]),
    "misc_nuit": ("5_misc", 20, [(1900, 300)]),
}
TOUTE_LA_JOURNEE = [(0, 2359)]

# Renommages a faire AVANT creation, quand une ancienne playlist occupe un nom
# que la cible reclame. Deux playlists du meme nom rendraient l'interface
# AzuraCast illisible et le rapprochement par nom ambigu. Un renommage ne
# touche qu'un libelle et n'a aucun effet sur la diffusion.
# A servi pour deep -> deep_old le 2026-09-10, puis vide : le plancher du soir
# s'appelle desormais `sunset`, qui fait la paire avec `sunrise`.
RENOMMAGES = {}

# Coups de pouce manuels de /energy dans le bot Telegram. Ce ne sont PAS des
# playlists de rotation : elles dorment, et le bot les reveille avec un planning
# DATE qui expire tout seul -- aucun cron, aucune tache de restauration. Elles
# tirent aux deux extremites de la grille : pousser, c'est plus de club ;
# calmer, c'est plus de sunrise.
BOOSTS_MANUELS = {"boost_up": "4_club", "boost_down": "1_sunrise"}

_ANCIENNES = ["chill", "groove", "house", "deep_old", "deep", "clubhouse", "techno",
              "nightdub", "chill_guest", "groove_guest", "house_guest", "deep_guest",
              "clubhouse_guest", "techno_guest", "jungle", "liquid", "liquid_guest"]
# `deep` figure dans la liste ci-dessus parce qu'avant le renommage c'etait
# l'ANCIENNE playlist. Une fois le renommage fait, ce nom designe la NOUVELLE :
# le garder ferait croire au verrou que l'ancien monde est encore a l'antenne,
# et surtout ferait supprimer le plancher deep par --nettoyer. Un nom present
# dans la cible n'est jamais un ancien, quelle qu'ait ete son histoire.
ANCIENNES = [n for n in _ANCIENNES if n not in
             set(PLANCHER) | set(BOOSTS) | set(PONCTUATION)]

# Jingles et mixtape_onair ne bougent jamais : ils ne dependent pas de la grille.
INTOUCHABLES = ["Jingles", "mixtape_onair"]


# --------------------------------------------------------------------------- API

def appel(methode, chemin, corps=None, timeout=60):
    data = json.dumps(corps).encode() if corps is not None else None
    req = urllib.request.Request(BASE + chemin, data=data, method=methode)
    req.add_header("X-API-Key", AZURACAST_API_KEY)
    if corps is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:600]
    except urllib.error.URLError as e:
        return 0, str(e)


def playlists_live():
    s, d = appel("GET", f"/station/{STATION}/playlists")
    if s != 200:
        raise SystemExit(f"Lecture des playlists impossible : {s} {d}")
    return {p["name"]: p for p in d}


def fichiers_live():
    s, d = appel("GET", f"/station/{STATION}/files", timeout=180)
    if s != 200:
        raise SystemExit(f"Lecture des fichiers impossible : {s} {d}")
    return d


def cible():
    """nom -> (bac, type, valeur, plannings)."""
    out = {}
    for nom, (bac, poids) in PLANCHER.items():
        out[nom] = (bac, "default", poids, TOUTE_LA_JOURNEE)
    for nom, (bac, poids, sch) in BOOSTS.items():
        out[nom] = (bac, "default", poids, sch)
    for nom, (bac, un_sur, sch) in PONCTUATION.items():
        out[nom] = (bac, "once_per_x_songs", un_sur, sch)
    return out


# --------------------------------------------------------------------------- etat

def decisions_par_nom():
    """nom de fichier en minuscules -> bac retenu."""
    return {r["key"]: r["retenu"] for r in cn.lignes()}


def rapprocher(fichiers, dec):
    """Associe chaque fichier du serveur a son futur bac.

    Le rapprochement se fait sur le nom de fichier, pas sur le chemin : un
    morceau range a la main dans un autre bac garderait son nom, et comparer
    les chemins lui ferait perdre sa trace.
    """
    apparies, inconnus = {}, []
    for f in fichiers:
        chemin = f.get("path") or ""
        dossier = chemin.split("/")[0]
        if dossier in ("Jingles", "Mixtapes"):
            continue
        bac = dec.get(ntpath.basename(chemin).lower())
        if bac is None:
            inconnus.append(chemin)
        else:
            apparies[f["id"]] = (bac, f, chemin)
    manquants = set(dec) - {ntpath.basename(c).lower() for _, _, c in apparies.values()}
    return apparies, inconnus, sorted(manquants)


def etat(args):
    pl = playlists_live()
    tgt = cible()
    print("=== playlists ===")
    # Un nom encore porte par une ANCIENNE playlist en instance de renommage
    # n'est pas la nouvelle : l'annoncer comme "existe" ferait croire le
    # travail fait alors que la playlist cible n'existe pas encore.
    a_liberer = {a for a, b in RENOMMAGES.items() if a in pl and b not in pl}
    deja = {n for n in tgt if n in pl and n not in a_liberer}
    absentes = [n for n in tgt if n not in deja]
    presentes = sorted(deja)
    for n in sorted(tgt):
        bac, typ, val, sch = tgt[n]
        if n in a_liberer:
            print("  %-15s a creer  <- %s  %s %s   (nom occupe par l'ancienne, a renommer)"
                  % (n, bac, typ, val))
        elif n in pl:
            p = pl[n]
            print("  %-15s existe   id %-4s %s  poids/1-sur %s"
                  % (n, p["id"], "ACTIVE" if p["is_enabled"] else "dormante", p.get("weight")))
        else:
            print("  %-15s a creer  <- %s  %s %s" % (n, bac, typ, val))
    print("  %d a creer, %d deja la" % (len(absentes), len(presentes)))

    coll = [a for a in RENOMMAGES if a in pl and RENOMMAGES[a] not in pl]
    if coll:
        print("  collision de nom : %s -> %s"
              % (", ".join(coll), ", ".join(RENOMMAGES[c] for c in coll)))

    print("\n=== rattachements ===")
    dec = decisions_par_nom()
    fichiers = fichiers_live()
    apparies, inconnus, manquants = rapprocher(fichiers, dec)
    par_bac = Counter(b for b, _, _ in apparies.values())
    for bac in cn.BACS:
        n = par_bac.get(bac, 0)
        cibles = [k for k, v in tgt.items() if v[0] == bac]
        print("  %-11s %4d fichier(s) -> %s" % (bac, n, ", ".join(cibles) or "aucune playlist (hors antenne)"))
    print("  %d fichiers sur le serveur, %d apparies" % (len(fichiers), len(apparies)))
    if inconnus:
        print("  %d sur le serveur sans decision de classement :" % len(inconnus))
        for c in inconnus[:8]:
            print("      %s" % c)
    if manquants:
        print("  %d classes mais absents du serveur :" % len(manquants))
        for c in manquants[:8]:
            print("      %s" % c)
    return 0


# --------------------------------------------------------------------------- creer

def creer(args):
    pl = playlists_live()
    tgt = cible()

    renommer = [(a, b) for a, b in RENOMMAGES.items() if a in pl and b not in pl]
    # Le renommage LIBERE un nom : le calculer avant lui ferait sauter la
    # playlist qui doit le reprendre. Ici, sans cette ligne, le plancher `deep`
    # n'etait jamais cree et le bac serait reste muet hors de sa fenetre.
    liberes = {a for a, _ in renommer}
    a_creer = [n for n in tgt if n not in pl or n in liberes]

    for a, b in renommer:
        print("  renommer  %s -> %s   (libelle seul, sans effet sur l'antenne)" % (a, b))
    for n in a_creer:
        bac, typ, val, sch = tgt[n]
        print("  creer     %-15s %-16s %-3s  %s   DESACTIVEE"
              % (n, typ, val, " ".join("%04d-%04d" % s for s in sch)))
    if not renommer and not a_creer:
        print("  rien a faire, tout est deja en place.")
        return 0
    if not args.apply:
        print("\nDRY-RUN. Rien n'a ete ecrit. Relancer avec --apply.")
        return 0

    for a, b in renommer:
        s, d = appel("PUT", f"/station/{STATION}/playlist/{pl[a]['id']}", {"name": b})
        if s not in (200, 201):
            raise SystemExit("Renommage de %s echoue : %s %s" % (a, s, d))
        print("  [OK] %s renommee %s" % (a, b))

    for n in a_creer:
        bac, typ, val, sch = tgt[n]
        corps = {
            "name": n,
            "type": typ,
            "source": "songs",
            "order": "shuffle",
            # DESACTIVEE : une playlist desactivee n'entre pas dans le tirage.
            # C'est ce qui permet de tout preparer sans toucher a l'antenne.
            "is_enabled": False,
            "avoid_duplicates": True,
            "include_in_requests": True,
            "schedule_items": [{"start_time": a, "end_time": b, "days": [],
                                "loop_once": False} for a, b in sch],
        }
        if typ == "once_per_x_songs":
            corps["play_per_songs"] = val
        else:
            corps["weight"] = val
        s, d = appel("POST", f"/station/{STATION}/playlists", corps)
        if s not in (200, 201):
            raise SystemExit("Creation de %s echouee : %s %s" % (n, s, d))
        print("  [OK] %s creee (id %s, dormante)" % (n, d["id"]))
    return 0


# --------------------------------------------------------------------------- remplir

def remplir(args):
    pl = playlists_live()
    tgt = cible()
    absentes = [n for n in tgt if n not in pl]
    if absentes:
        raise SystemExit("Playlists absentes : %s. Lancer --creer d'abord."
                         % ", ".join(sorted(absentes)))

    par_bac_ids = ids_par_bac(pl, tgt)

    dec = decisions_par_nom()
    fichiers = fichiers_live()
    apparies, inconnus, manquants = rapprocher(fichiers, dec)

    a_faire = []
    for mid, (bac, f, chemin) in apparies.items():
        voulues = par_bac_ids.get(bac, set())          # _ecarte -> aucune
        actuelles = {p["id"] if isinstance(p, dict) else p for p in (f.get("playlists") or [])}
        if voulues - actuelles:
            a_faire.append((mid, chemin, sorted(actuelles | voulues), sorted(voulues - actuelles)))

    print("  %d fichiers apparies, %d rattachements a poser" % (len(apparies), len(a_faire)))
    par_bac = Counter(apparies[m][0] for m, _, _, _ in a_faire)
    for bac in cn.BACS:
        if par_bac.get(bac):
            print("      %-11s %4d" % (bac, par_bac[bac]))
    ecartes = sum(1 for b, _, _ in apparies.values() if b == "_ecarte")
    print("  %d ecartes : aucune nouvelle playlist, ils sortiront de l'antenne "
          "a la bascule sans etre supprimes" % ecartes)
    if not a_faire:
        print("  rien a faire.")
        return 0
    if not args.apply:
        print("\nDRY-RUN. Rien n'a ete ecrit. Relancer avec --apply.")
        return 0

    ok = ko = 0
    for i, (mid, chemin, toutes, ajout) in enumerate(a_faire, 1):
        s, d = appel("PUT", f"/station/{STATION}/file/{mid}", {"playlists": toutes})
        if s in (200, 201):
            ok += 1
        else:
            ko += 1
            print("  [ECHEC] %s : %s %s" % (chemin, s, d))
        if i % 100 == 0 or i == len(a_faire):
            print("  %d/%d  (%d ok, %d echecs)" % (i, len(a_faire), ok, ko))
    print("\n%d rattachements poses, %d echecs. L'antenne n'a pas change : les "
          "nouvelles playlists dorment." % (ok, ko))
    return 1 if ko else 0


# --------------------------------------------------------------------------- dossiers

def ids_par_bac(pl, tgt):
    d = {}
    for nom, (bac, _, _, _) in tgt.items():
        d.setdefault(bac, set()).add(pl[nom]["id"])
    return d


def dossiers(args):
    """Cree les dossiers distants et y accroche les playlists.

    AzuraCast sait associer un dossier a une ou plusieurs playlists : tout
    fichier qui y arrive les rejoint sans intervention. C'est ce mecanisme qui
    fait marcher l'ancien monde (`1_chill` -> chill + chill_guest), et c'est
    ce qui rendra le depot SFTP a la main autonome.

    `_ecarte` recoit un dossier mais AUCUNE playlist : y deposer un morceau le
    met en reserve, sur le serveur, hors antenne.
    """
    pl = playlists_live()
    absentes = [n for n in cible() if n not in pl]
    if absentes:
        raise SystemExit("Playlists absentes : %s. Lancer --creer d'abord." % ", ".join(absentes))
    tgt = cible()
    par_bac = ids_par_bac(pl, tgt)
    nom_par_id = {p["id"]: p["name"] for p in pl.values()}

    s, d = appel("GET", f"/station/{STATION}/files/directories")
    if s != 200:
        raise SystemExit("Lecture des dossiers impossible : %s %s" % (s, d))
    existants = {r["path"] for r in d["rows"]}

    for bac in cn.BACS:
        ids = sorted(par_bac.get(bac, ()))
        etat_dossier = "existe" if bac in existants else "a creer"
        libelle = ", ".join(nom_par_id[i] for i in ids) or "aucune (mise en reserve)"
        print("  %-11s %-8s -> %s" % (bac, etat_dossier, libelle))
    if not args.apply:
        print("\nDRY-RUN. Rien n'a ete ecrit. Relancer avec --apply.")
        return 0

    for bac in cn.BACS:
        if bac not in existants:
            s, d = appel("POST", f"/station/{STATION}/files/mkdir", {"name": bac})
            if s not in (200, 201):
                raise SystemExit("Creation du dossier %s echouee : %s %s" % (bac, s, d))
            print("  [OK] dossier %s cree" % bac)
    for bac, ids in par_bac.items():
        for pid in sorted(ids):
            s, d = appel("PUT", f"/station/{STATION}/playlist/{pid}/apply-to",
                         {"directories": [bac]})
            if s not in (200, 201):
                print("  [ECHEC] %s -> %s : %s %s" % (nom_par_id[pid], bac, s, d))
                continue
            print("  [OK] %-15s accrochee a %s" % (nom_par_id[pid], bac))
    return 0


# --------------------------------------------------------------------------- deplacer

def deplacer(args):
    """Range les fichiers du serveur dans leur nouveau dossier.

    L'appartenance aux playlists suit le fichier (elle porte sur l'id du
    media, pas sur le chemin), donc ce deplacement ne change RIEN a ce qui
    passe a l'antenne. Il ne sert qu'a la lisibilite : que le dossier dise la
    verite, en SFTP comme dans l'interface.
    """
    dec = decisions_par_nom()
    fichiers = fichiers_live()
    apparies, _, _ = rapprocher(fichiers, dec)

    par_dest = {}
    for mid, (bac, f, chemin) in apparies.items():
        if chemin.split("/")[0] == bac:
            continue                       # deja au bon endroit
        par_dest.setdefault(bac, []).append(chemin)

    total = sum(len(v) for v in par_dest.values())
    for bac in cn.BACS:
        if par_dest.get(bac):
            print("  %-11s %4d fichier(s) a deplacer" % (bac, len(par_dest[bac])))
    print("  %d au total" % total)
    if not total:
        print("  rien a faire.")
        return 0
    if not args.apply:
        print("\nDRY-RUN. Rien n'a ete ecrit. Relancer avec --apply.")
        return 0

    # Par paquets : un seul appel pour 1100 fichiers depasserait le timeout du
    # serveur, et un echec au milieu laisserait un etat illisible.
    PAQUET = 50
    faits = rates = 0
    for bac, chemins in par_dest.items():
        for i in range(0, len(chemins), PAQUET):
            lot = chemins[i:i + PAQUET]
            s, d = appel("PUT", f"/station/{STATION}/files/batch",
                         {"do": "move", "currentDirectory": "", "files": lot,
                          "dirs": [], "directory": bac}, timeout=180)
            if s in (200, 201) and not (d or {}).get("errors"):
                faits += len(lot)
            else:
                rates += len(lot)
                print("  [ECHEC] %s lot %d : %s %s" % (bac, i // PAQUET, s, str(d)[:200]))
            print("  %s : %d/%d" % (bac, min(i + PAQUET, len(chemins)), len(chemins)))
    print("\n%d deplaces, %d en echec." % (faits, rates))
    return 1 if rates else 0


# --------------------------------------------------------------------------- local

def local(args):
    """Range la bibliotheque locale comme le serveur.

    Le local et le distant sont le miroir l'un de l'autre : sync_library.py et
    check_local_vs_server.py comparent bac par bac, et le triage ecrit dans
    New_prog/<bac>/. Laisser le local sur les anciens noms ferait mentir les
    trois.

    Deplacement seul, jamais de suppression : un fichier deja present a
    destination fait renoncer sur ce fichier plutot que d'ecraser.
    """
    import shutil
    racine = ana.LOCAL(ana.NEW_PROG)
    if not os.path.isdir(racine):
        raise SystemExit("Introuvable : %s" % racine)

    dec = {r["key"]: r["retenu"] for r in cn.lignes()}
    a_bouger, absents, collisions = [], [], []
    for dossier in sorted(os.listdir(racine)):
        chemin_dossier = os.path.join(racine, dossier)
        if not os.path.isdir(chemin_dossier) or dossier in cn.BACS:
            continue
        if dossier in ("_a_revoir", "10_Mixtapes"):
            continue                      # hors grille, on n'y touche pas
        for nom in os.listdir(chemin_dossier):
            if not nom.lower().endswith(".mp3"):
                continue
            bac = dec.get(nom.lower())
            if bac is None:
                absents.append(os.path.join(dossier, nom))
                continue
            src = os.path.join(chemin_dossier, nom)
            dst = os.path.join(racine, bac, nom)
            if os.path.exists(dst):
                collisions.append(os.path.join(dossier, nom))
                continue
            a_bouger.append((src, dst, bac))

    par_bac = Counter(b for _, _, b in a_bouger)
    for bac in cn.BACS:
        if par_bac.get(bac):
            print("  %-11s %4d fichier(s)" % (bac, par_bac[bac]))
    print("  %d a deplacer" % len(a_bouger))
    if absents:
        print("  %d sans decision de classement, laisses en place :" % len(absents))
        for c in absents[:6]:
            print("      %s" % c)
    if collisions:
        print("  %d deja presents a destination, ignores :" % len(collisions))
        for c in collisions[:6]:
            print("      %s" % c)
    if not a_bouger:
        print("  rien a faire.")
        return 0
    if not args.apply:
        print("\nDRY-RUN. Rien n'a bouge. Relancer avec --apply.")
        return 0

    for bac in cn.BACS:
        os.makedirs(os.path.join(racine, bac), exist_ok=True)
    faits = rates = 0
    for src, dst, _ in a_bouger:
        try:
            shutil.move(src, dst)
            faits += 1
        except OSError as e:
            rates += 1
            print("  [ECHEC] %s : %s" % (os.path.basename(src), e))
    print("\n%d deplaces, %d en echec." % (faits, rates))
    print("Les anciens dossiers vides restent : les retirer a la main quand "
          "sync_library.py aura confirme 0 ecart.")
    return 1 if rates else 0


# --------------------------------------------------------------------------- boosts

def boosts(args):
    """Cree et remplit boost_up / boost_down, les leviers de /energy.

    Elles restent DESACTIVEES : c'est le bot qui les allume, avec un planning
    date qui s'eteint tout seul. Pas de folder-playlist ici, sinon tout nouveau
    morceau du bac s'y ajouterait sans qu'on l'ait voulu ; le rattachement est
    explicite et se rejoue avec cette phase apres chaque arrivage.
    """
    pl = playlists_live()
    fichiers = fichiers_live()

    a_creer = [n for n in BOOSTS_MANUELS if n not in pl]
    for nom, bac in BOOSTS_MANUELS.items():
        dedans = sum(1 for f in fichiers if (f.get("path") or "").startswith(bac + "/"))
        etat = "a creer" if nom in a_creer else (
            "%d titres" % (pl[nom].get("num_songs") or 0))
        print("  %-11s <- %-10s  %s (le bac en compte %d)" % (nom, bac, etat, dedans))
    if not args.apply:
        print("\nDRY-RUN. Rien n'a ete ecrit. Relancer avec --apply.")
        return 0

    for nom in a_creer:
        s, d = appel("POST", f"/station/{STATION}/playlists", {
            "name": nom, "type": "default", "source": "songs", "order": "shuffle",
            "is_enabled": False, "avoid_duplicates": True, "include_in_requests": True,
        })
        if s not in (200, 201):
            raise SystemExit("Creation de %s echouee : %s %s" % (nom, s, d))
        pl[nom] = d
        print("  [OK] %s creee (id %s, dormante)" % (nom, d["id"]))

    for nom, bac in BOOSTS_MANUELS.items():
        pid = pl[nom]["id"]
        poses = 0
        for f in fichiers:
            if not (f.get("path") or "").startswith(bac + "/"):
                continue
            actuelles = {p["id"] if isinstance(p, dict) else p for p in (f.get("playlists") or [])}
            if pid in actuelles:
                continue
            s, d = appel("PUT", f"/station/{STATION}/file/{f['id']}",
                         {"playlists": sorted(actuelles | {pid})})
            if s in (200, 201):
                poses += 1
        print("  [OK] %-11s %d rattachement(s) pose(s)" % (nom, poses))
    return 0


# --------------------------------------------------------------------------- nettoyer

def nettoyer(args):
    """Supprime l'ancien monde : playlists et dossiers vides.

    LE SEUL ENDROIT IRREVERSIBLE DE TOUTE LA TRANSITION, d'ou les trois
    verrous. Une playlist supprimee ne se retrouve pas ; --revenir ne pourra
    plus rien pour toi apres.

    Verrou 1 : la bascule doit etre faite. Les anciennes playlists sont ce qui
    passe A L'ANTENNE en ce moment : les supprimer avant ferait taire la
    station, pas la simplifier.
    Verrou 2 : les nouvelles doivent etre actives et non vides.
    Verrou 3 : un dossier qui contient encore un fichier n'est pas supprime.
    """
    pl = playlists_live()
    tgt = cible()

    encore_allumees = [n for n in ANCIENNES if n in pl and pl[n]["is_enabled"]]
    eteintes_neuves = [n for n in tgt if n in pl and not pl[n]["is_enabled"]]
    if encore_allumees or eteintes_neuves:
        print("  BASCULE PAS FAITE, suppression refusee.")
        if encore_allumees:
            print("    encore a l'antenne : %s" % ", ".join(encore_allumees))
        if eteintes_neuves:
            print("    nouvelles endormies : %s" % ", ".join(sorted(eteintes_neuves)))
        print("  Lancer --basculer --apply, ecouter, et revenir ici ensuite.")
        return 1

    s, d = appel("GET", f"/station/{STATION}/files/directories")
    if s != 200:
        raise SystemExit("Lecture des dossiers impossible : %s %s" % (s, d))
    dossiers_serveur = {r["path"] for r in d["rows"]}
    restes = Counter((f.get("path") or "").split("/")[0] for f in fichiers_live())

    a_supprimer_pl = [n for n in ANCIENNES if n in pl and n not in BOOSTS_MANUELS]
    vieux_dossiers = [x for x in dossiers_serveur
                      if x not in cn.BACS and x not in ("Jingles", "Mixtapes")]
    vides = [x for x in vieux_dossiers if not restes.get(x)]
    pleins = [(x, restes[x]) for x in vieux_dossiers if restes.get(x)]

    print("  playlists a supprimer : %s" % (", ".join(a_supprimer_pl) or "aucune"))
    print("  dossiers vides a supprimer : %s" % (", ".join(sorted(vides)) or "aucun"))
    for x, n in sorted(pleins):
        print("  %s garde %d fichier(s) : conserve" % (x, n))
    if not args.apply:
        print("\nDRY-RUN. Rien n'a ete supprime. Relancer avec --apply.")
        return 0

    for n in a_supprimer_pl:
        s, d = appel("DELETE", f"/station/{STATION}/playlist/{pl[n]['id']}")
        print("  %s playlist %s" % ("[OK]" if s in (200, 204) else "[ECHEC %s]" % s, n))
    if vides:
        s, d = appel("PUT", f"/station/{STATION}/files/batch",
                     {"do": "delete", "currentDirectory": "", "files": [],
                      "dirs": sorted(vides)}, timeout=120)
        print("  %s dossiers %s" % ("[OK]" if s in (200, 201) else "[ECHEC %s]" % s,
                                    ", ".join(sorted(vides))))
    return 0


# --------------------------------------------------------------------------- doser

def doser(args):
    """Profondeur de rotation reelle, a partir des tailles de bac du moment."""
    tgt = cible()
    rows = cn.lignes()
    tailles = Counter(r["retenu"] for r in rows)

    def poids_a(h):
        p = {bac: w for bac, w in PLANCHER.values()}
        for bac, w, sch in BOOSTS.values():
            for d, f in sch:
                if (d // 100 <= h < f // 100) if d < f else (h >= d // 100 or h < f // 100):
                    p[bac] += w
        return p

    TITRES_HEURE = 8.0
    joues = Counter()
    for h in range(24):
        p = poids_a(h)
        total = sum(p.values())
        for bac, w in p.items():
            joues[bac] += TITRES_HEURE * w / total

    print("%-11s %7s %11s %10s" % ("bac", "fonds", "joues/jour", "retour"))
    for bac in ("1_sunrise", "2_solaire", "3_sunset", "4_club"):
        n, j = tailles.get(bac, 0), joues[bac]
        print("%-11s %7d %11.1f %7.1f jours" % (bac, n, j, n / j if j else 0))
    n_misc = tailles.get("5_misc", 0)
    print("%-11s %7d   ponctuation 1 sur %s le jour, 1 sur %s la nuit"
          % ("5_misc", n_misc, PONCTUATION["misc_jour"][1], PONCTUATION["misc_nuit"][1]))

    antenne = sum(tailles.get(b, 0) for b in cn.BACS if b != "_ecarte")
    par_jour = sum(joues.values())
    print("\n%d morceaux a l'antenne, %d ecartes." % (antenne, tailles.get("_ecarte", 0)))
    print("Environ %.0f diffusions par jour : la moyenne de retour est de %.1f jours,"
          % (par_jour, antenne / par_jour if par_jour else 0))
    print("quelle que soit la ponderation. Les poids repartissent, ils ne creent")
    print("pas de fonds : pour allonger le retour il faut enrichir les bacs.")
    return 0


# --------------------------------------------------------------------------- basculer

def _activer(noms, actif, pl):
    faits = 0
    for n in noms:
        p = pl.get(n)
        if not p or bool(p["is_enabled"]) == actif:
            continue
        s, d = appel("PUT", f"/station/{STATION}/playlist/{p['id']}", {"is_enabled": actif})
        if s not in (200, 201):
            print("  [ECHEC] %s : %s %s" % (n, s, d))
            continue
        print("  [OK] %-16s %s" % (n, "activee" if actif else "desactivee"))
        faits += 1
    return faits


def basculer(args):
    pl = playlists_live()
    tgt = cible()
    absentes = [n for n in tgt if n not in pl]
    if absentes:
        raise SystemExit("Playlists absentes : %s. Lancer --creer puis --remplir."
                         % ", ".join(sorted(absentes)))

    vides = [n for n in tgt if not (pl[n].get("num_songs") or 0)]
    if vides:
        print("  ATTENTION, playlists vides : %s" % ", ".join(sorted(vides)))
        print("  Lancer --remplir avant de basculer, sinon l'antenne se tait.")
        if args.apply:
            raise SystemExit("Bascule refusee : une playlist vide passerait a l'antenne.")

    a_eteindre = [n for n in ANCIENNES if n in pl and pl[n]["is_enabled"]]
    print("  activer      : %s" % ", ".join(sorted(tgt)))
    print("  desactiver   : %s" % (", ".join(a_eteindre) or "aucune"))
    print("  ne pas toucher : %s" % ", ".join(INTOUCHABLES))
    print("  RIEN N'EST SUPPRIME. --revenir defait exactement ceci.")
    if not args.apply:
        print("\nDRY-RUN. Rien n'a ete ecrit. Relancer avec --apply.")
        return 0

    # Allumer AVANT d'eteindre : entre les deux appels, un pool vide ferait
    # taire la station. Un instant de doublon vaut mieux qu'un instant de vide.
    _activer(sorted(tgt), True, pl)
    _activer(a_eteindre, False, pl)
    print("\nBascule faite. Verifier a l'antenne, puis, si besoin : --revenir --apply")
    return 0


def revenir(args):
    pl = playlists_live()
    tgt = cible()
    a_rallumer = [n for n in ANCIENNES if n in pl and not pl[n]["is_enabled"]
                  and n not in ("chill_guest", "groove_guest", "house_guest", "deep_guest")]
    print("  rallumer   : %s" % ", ".join(sorted(a_rallumer)))
    print("  endormir   : %s" % ", ".join(sorted(n for n in tgt if n in pl)))
    if not args.apply:
        print("\nDRY-RUN. Rien n'a ete ecrit. Relancer avec --apply.")
        return 0
    _activer(a_rallumer, True, pl)
    _activer(sorted(n for n in tgt if n in pl), False, pl)
    print("\nRetour arriere fait.")
    return 0


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    for nom, aide in [("etat", "ce qui existe et ce qui manque"),
                      ("creer", "cree les playlists, desactivees"),
                      ("remplir", "rattache les morceaux"),
                      ("dossiers", "cree les dossiers et y accroche les playlists"),
                      ("deplacer", "range les fichiers du serveur"),
                      ("local", "range la bibliotheque locale"),
                      ("boosts", "cree boost_up/boost_down pour /energy"),
                      ("nettoyer", "supprime l'ancien monde, APRES la bascule"),
                      ("doser", "profondeur de rotation reelle"),
                      ("basculer", "active les nouvelles, eteint les anciennes"),
                      ("revenir", "defait la bascule")]:
        g.add_argument("--" + nom, action="store_true", help=aide)
    ap.add_argument("--apply", action="store_true", help="ecrit vraiment")
    args = ap.parse_args()

    for nom, fn in (("creer", creer), ("remplir", remplir),
                    ("dossiers", dossiers), ("deplacer", deplacer),
                    ("local", local), ("boosts", boosts),
                    ("nettoyer", nettoyer), ("doser", doser),
                    ("basculer", basculer), ("revenir", revenir)):
        if getattr(args, nom):
            return fn(args)
    return etat(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
