#!/usr/bin/env python3
"""Classement de la bibliotheque dans les futurs bacs, avant la bascule.

Prepare la migration : chaque morceau recoit une destination proposee par la
grille, et tu ne touches QUE ce avec quoi tu n'es pas d'accord. La grille tombe
juste a 94 % (mesure sur 80 ecoutes) : il y a de l'ordre de 60 lignes a
contredire, pas 1126 a trancher.

RIEN N'EST DEPLACE ICI. Ce script n'ecrit que des destinations dans
classify_new_decisions.json, relu plus tard par la bascule elle-meme. Aucun
fichier ne bouge, aucune playlist n'est touchee, l'antenne continue.

LA GRILLE (seuils absolus, pas de percentiles) :

    1. genre Drum n Bass / Jungle ... _ecarte    EN PREMIER : leur BPM est lu en
                                                 demi-tempo (87 pour du 174), donc
                                                 tout test de tempo place avant les
                                                 rangerait dans le bac du matin.
    2. BPM > 145 ................... _ecarte     tempo lu en double
    3. BPM < 120 ................... 1_sunrise
    4. BPM >= 127 .................. 4_club
    5. happy >= 0.45 ............... 2_solaire
    6. sinon ....................... 3_deep

`5_misc` n'est JAMAIS atteint automatiquement : c'est une fonction (ce qui casse
le rythme), pas une categorie de genre. 26 % de la bibliotheque est hors famille
house au sens Discogs, et 23 des 80 morceaux valides a l'oreille en font partie
tout en ayant leur place dans les bacs normaux. Seule une decision humaine y
ecrit.

Usage :
    python classify_new.py
    python classify_new.py --port 8140
    python classify_new.py --rapport   # repartition et desaccords, sans serveur
    python classify_new.py --export    # ecrit le plan de bascule en CSV
    python classify_new.py --reset
"""
import argparse
import csv
import html
import json
import ntpath
import os
import sys
import threading
import urllib.parse
import webbrowser
from collections import OrderedDict, Counter
from http.server import ThreadingHTTPServer

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)

import analyse_new_tracks as ana  # noqa: E402
import classify_bins  # noqa: E402  (source de verite unique de la grille)
import review_analyse as ra  # noqa: E402  (moteur audio : Range, cache, prefetch)

DECISIONS_PATH = os.path.join(TOOLS_DIR, "classify_new_decisions.json")
EXPORT_PATH = os.path.join(TOOLS_DIR, "bascule_plan.csv")
DEFAULT_PORT = 8140

# Une seule definition de la grille, dans classify_bins : c'est elle que le
# triage des nouveaux morceaux appelle. Deux copies divergeraient au premier
# reglage de seuil, et l'interface classerait autrement que la chaine.
BACS = classify_bins.FUTURS_BACS
LIBELLE = {
    "1_sunrise": "Sunrise, lent et aere",
    "2_solaire": "Solaire, plein jour",
    "3_deep": "Deep, meme tempo mais sombre",
    "4_club": "Club, tempo haut",
    "5_misc": "Misc, l'echappatoire (a la main)",
    "_ecarte": "En attente, hors antenne",
}
BPM_BAS = classify_bins.FUTUR_BPM_BAS
BPM_HAUT = classify_bins.FUTUR_BPM_HAUT
BPM_PLAFOND = classify_bins.FUTUR_BPM_PLAFOND
HAPPY_SEUIL = classify_bins.FUTUR_HAPPY


def est_dnb(t):
    return classify_bins.genre_family(genre(t)) == "jungle"


# --------------------------------------------------------------------------- grille

def bpm(t):
    return float(t.get("bpm") or 0.0)


def happy(t):
    return float((t.get("mood") or {}).get("happy", 0.0))


def agressif(t):
    return float((t.get("mood") or {}).get("aggressive", 0.0))


def genre(t):
    g = t.get("genres") or []
    if not g:
        return ""
    label = g[0][0] if isinstance(g[0], (list, tuple)) else str(g[0])
    return label.split("---")[-1].strip()


def bac_actuel(t):
    return ntpath.basename(ntpath.dirname(t.get("path") or ""))


def propose(t):
    return classify_bins.classify_futur_bin(genre(t), bpm(t), t.get("mood"))


def pourquoi(t):
    """La raison, en clair. Sert autant a decider qu'a verifier la grille."""
    if est_dnb(t):
        return f"{genre(t)} : tempo illisible, mis en attente"
    b = bpm(t)
    if b > BPM_PLAFOND:
        return f"{b:.1f} BPM : au-dela de {BPM_PLAFOND:.0f}, tempo lu en double"
    for seuil in (BPM_BAS, BPM_HAUT):
        if abs(b - seuil) < BRUIT_BPM:
            return f"{b:.2f} BPM : sur la frontiere des {seuil:.0f}, la mesure tranche"
    if b < BPM_BAS:
        return f"{b:.1f} BPM, sous {BPM_BAS:.0f}"
    if b >= BPM_HAUT:
        return f"{b:.1f} BPM, au-dessus de {BPM_HAUT:.0f}"
    cote = "au-dessus" if happy(t) >= HAPPY_SEUIL else "sous"
    return f"{b:.1f} BPM, couleur {happy(t):.2f} {cote} de {HAPPY_SEUIL}"


def marge(t):
    """Distance au seuil le plus proche, normalisee. 0 = pile sur la frontiere.

    Les deux axes n'ont pas la meme echelle : 8 BPM et 0.25 de couleur sont
    ramenes a la meme unite, sinon le tempo ecraserait toujours la couleur.
    Sert a trier : le plus contestable en premier dans chaque bac.
    """
    b, h = bpm(t), happy(t)
    if est_dnb(t):
        return 9.0
    d = [abs(b - BPM_BAS) / 8.0, abs(b - BPM_HAUT) / 8.0, abs(b - BPM_PLAFOND) / 8.0]
    if BPM_BAS <= b < BPM_HAUT:
        d.append(abs(h - HAPPY_SEUIL) / 0.25)
    return min(d)


# Sous ces distances, ce n'est plus un jugement mais un pile ou face : le
# tempo de la maison est quantifie sur l'entier, et les deux frontieres tombent
# pile sur un pic. 54 morceaux sont a 120.0 BPM et 46 a 127.0 ; l'extracteur
# rend 119.97 pour les uns et 120.02 pour les autres, et la grille les envoie
# dans deux bacs differents pour 0.05 BPM d'ecart de mesure. Ces morceaux-la
# sont a montrer, pas a reecouter : a l'oreille ils ont le meme tempo.
BRUIT_BPM = 0.35
BRUIT_COULEUR = 0.04


def limite(t):
    b = bpm(t)
    if est_dnb(t):
        return False
    if min(abs(b - BPM_BAS), abs(b - BPM_HAUT), abs(b - BPM_PLAFOND)) < BRUIT_BPM:
        return True
    return BPM_BAS <= b < BPM_HAUT and abs(happy(t) - HAPPY_SEUIL) < BRUIT_COULEUR


# --------------------------------------------------------------------------- etat

def charger():
    if not os.path.exists(DECISIONS_PATH):
        return {}
    try:
        with open(DECISIONS_PATH, encoding="utf-8") as fh:
            d = json.load(fh) or {}
        return {k: v for k, v in d.items() if v in BACS}
    except (json.JSONDecodeError, OSError):
        return {}


def ecrire(d):
    """Ecriture atomique : ces decisions sont rendues a l'oreille, une heure
    d'ecoute par centaine. Ouvrir le fichier en "w" le vide avant de le
    remplir ; une coupure de courant pile la laisserait vide. On ecrit a cote,
    on force sur le disque, puis on remplace d'un coup -- os.replace est
    atomique, y compris sur NTFS."""
    tmp = DECISIONS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, DECISIONS_PATH)


def lignes():
    """Un enregistrement par morceau, groupe par destination RETENUE."""
    dec = charger()
    out = []
    for t in ana.load_metadata():
        chemin = t.get("path") or ""
        cle = ana.key_of(chemin)
        prop = propose(t)
        out.append({
            "key": cle,
            "path": chemin,
            "nom": ntpath.basename(chemin),
            "source": bac_actuel(t),
            "propose": prop,
            "retenu": dec.get(cle, prop),
            "force": cle in dec and dec[cle] != prop,
            "bpm": bpm(t),
            "happy": happy(t),
            "agressif": agressif(t),
            "genre": genre(t) or "?",
            "pourquoi": pourquoi(t),
            "marge": marge(t),
            "limite": limite(t),
            "jouable": os.path.exists(ana.LOCAL(chemin)),
        })
    out.sort(key=lambda r: (BACS.index(r["retenu"]), r["marge"]))
    return out


def bilan(rows):
    par_bac = Counter(r["retenu"] for r in rows)
    return {
        "total": len(rows),
        "forces": sum(1 for r in rows if r["force"]),
        "limites": sum(1 for r in rows if r["limite"]),
        "par_bac": {b: par_bac.get(b, 0) for b in BACS},
    }


# --------------------------------------------------------------------------- page

CSS = """
:root{
  --fond:#14151a; --panneau:#1b1d24; --ligne:#272a33; --texte:#e8eaef;
  --faible:#98a0b0; --accent:#6aa9e0; --vif:#4fb477; --alerte:#e0705f;
  --focus:#8ec5ff;
}
*{box-sizing:border-box}
/* .ligne est en display:grid, ce qui bat le display:none du navigateur sur
   [hidden] : sans cette regle le filtre marque les lignes sans les cacher. */
[hidden]{display:none!important}
body{margin:0;background:var(--fond);color:var(--texte);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.num{font-variant-numeric:tabular-nums}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px;border-radius:4px}

header{position:sticky;top:0;z-index:9;background:var(--fond);
border-bottom:1px solid var(--ligne);padding:12px 22px}
h1{margin:0 0 8px;font-size:17px;font-weight:600}
.repartition{display:flex;gap:6px;flex-wrap:wrap}
.puce{display:flex;align-items:baseline;gap:6px;background:var(--panneau);
border:1px solid var(--ligne);border-radius:6px;padding:4px 10px;font-size:12px}
.puce b{font-size:15px;font-variant-numeric:tabular-nums}
.puce.a-moi{border-color:var(--accent)}
.compte{color:var(--faible);font-size:12.5px;margin-top:7px}
.compte b{color:var(--texte);font-variant-numeric:tabular-nums}

main{padding:14px 22px 84px;max-width:1280px}
.filtres{display:flex;gap:7px;margin-bottom:14px;flex-wrap:wrap}
.filtres button{font-size:12.5px;padding:6px 12px}
.filtres button[aria-pressed="true"]{background:var(--accent);color:#0a1520;font-weight:600}

h2{font-size:14px;font-weight:600;margin:20px 0 6px;padding-bottom:5px;
border-bottom:1px solid var(--ligne);display:flex;gap:9px;align-items:baseline;cursor:pointer}
h2 .n{color:var(--faible);font-weight:400;font-variant-numeric:tabular-nums}
h2 .fleche{transition:transform .15s;font-size:11px;color:var(--faible)}
h2.replie .fleche{transform:rotate(-90deg)}

.ligne{display:grid;grid-template-columns:34px 1fr 250px 210px;gap:12px;align-items:center;
background:var(--panneau);border:1px solid var(--ligne);border-radius:7px;
padding:8px 12px;margin-bottom:5px}
.ligne.force{background:#1d2530;border-color:var(--accent)}
.ligne.limite .titre::after{content:"frontiere";margin-left:8px;font-size:10px;
color:#d8b45f;border:1px solid #4a3f22;border-radius:9px;padding:1px 6px;vertical-align:1px}
.ligne.joue{background:#1f2732}
.ligne.injouable{opacity:.5}
.titre{font-weight:500;word-break:break-word}
.detail{color:var(--faible);font-size:12px;margin-top:2px}
.source{color:var(--faible);font-size:11.5px}
.mesures{display:flex;gap:14px;font-size:12px;color:var(--faible)}
.mesures b{color:var(--texte);font-weight:500}

button{background:var(--ligne);color:var(--texte);border:1px solid transparent;
border-radius:6px;padding:6px 11px;cursor:pointer;font:inherit;font-size:13px;
transition:background .15s,border-color .15s}
button:hover:not(:disabled){border-color:var(--accent)}
button:disabled{opacity:.4;cursor:default}
button.lire{padding:5px 8px;display:grid;place-items:center}
button.lire svg{display:block}
select{background:var(--ligne);color:var(--texte);border:1px solid transparent;
border-radius:6px;padding:6px 8px;font:inherit;font-size:12.5px;cursor:pointer;width:100%}
select:hover{border-color:var(--accent)}
select.force{border-color:var(--accent);color:var(--accent);font-weight:600}

#alerte{position:fixed;bottom:56px;left:22px;right:22px;z-index:11;
background:#3a1f1c;border:1px solid var(--alerte);color:#ffd9d2;
border-radius:7px;padding:10px 14px;font-size:13px}
footer{position:fixed;bottom:0;left:0;right:0;background:var(--panneau);
border-top:1px solid var(--ligne);padding:9px 22px;display:flex;gap:16px;
align-items:center;z-index:9;font-size:12.5px;color:var(--faible)}
footer audio{height:34px;width:300px}
#encours{color:var(--texte);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
kbd{background:var(--ligne);border:1px solid #333846;border-bottom-width:2px;
border-radius:4px;padding:1px 5px;font:inherit;font-size:11px;color:var(--texte)}
.aide{position:fixed;inset:0;background:rgba(8,9,12,.82);display:grid;place-items:center;z-index:20}
.aide[hidden]{display:none}
.aide .boite{background:var(--panneau);border:1px solid var(--ligne);border-radius:10px;
padding:22px 26px;max-width:460px}
.aide h3{margin:0 0 14px;font-size:15px}
.aide dl{display:grid;grid-template-columns:auto 1fr;gap:8px 16px;margin:0;font-size:13px}
.aide dt{text-align:right}
.aide dd{margin:0;color:var(--faible)}
@media (prefers-reduced-motion: reduce){*{transition:none!important}}
/* Sous 1150 px les mesures passent sous le titre au lieu de disparaitre :
   ce sont elles qui justifient le bac propose, les masquer rend l'arbitrage
   aveugle. */
@media (max-width:1150px){
  .ligne{grid-template-columns:34px 1fr 190px;row-gap:5px}
  .ligne>.lire{grid-area:1/1}
  .ligne>.infos{grid-area:1/2}
  .ligne>select{grid-area:1/3}
  .ligne>.mesures{grid-area:2/2/3/4}
}
@media (max-width:620px){
  .ligne{grid-template-columns:34px 1fr}
  .ligne>select{grid-area:2/2}
  .ligne>.mesures{grid-area:3/2}
}
"""

JS = r"""
const BACS = __BACS__;
let courant = null;

// --- lecteur unique : 1132 elements <audio> tueraient la page ---
const lecteur = document.getElementById('lecteur');
function lire(l){
  document.querySelectorAll('.ligne.joue').forEach(x => x.classList.remove('joue'));
  l.classList.add('joue');
  selectionner(l);
  document.getElementById('encours').textContent = l.querySelector('.titre').textContent;
  lecteur.src = '/audio?k=' + encodeURIComponent(l.dataset.k);
  lecteur.play().catch(() => {});
  const t = [...visibles()], i = t.indexOf(l);
  for (const n of t.slice(i + 1, i + 3)) {
    if (n.dataset.pf) continue;
    n.dataset.pf = 1;
    fetch('/audio?k=' + encodeURIComponent(n.dataset.k), {headers:{Range:'bytes=0-524287'}})
      .then(r => r.arrayBuffer()).catch(() => {});
  }
}
const visibles = () => [...document.querySelectorAll('.ligne')].filter(l => l.offsetParent);

function selectionner(l){
  if (!l) return;
  courant = l;
  l.querySelector('.lire').focus({preventScroll:true});
  l.scrollIntoView({block:'nearest'});
}
function voisin(pas){
  const t = visibles();
  if (!t.length) return;
  const i = courant ? t.indexOf(courant) : -1;
  selectionner(t[Math.min(Math.max(i + pas, 0), t.length - 1)]);
}

async function poser(l, bac){
  // Un serveur arrete fait rejeter fetch, pas renvoyer un code : sans ce
  // try/catch la decision etait perdue en silence et la ligne affichait
  // quand meme le nouveau bac.
  let r;
  try {
    r = await fetch('/decision', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({key: l.dataset.k, bac: bac})});
  } catch (e) {
    signaler("Non enregistre : le serveur ne repond pas. Relance le script, "
             + "rien n est perdu, puis recommence ce choix.");
    l.querySelector('select').value = l.dataset.retenu;
    return;
  }
  if (!r.ok) { signaler('Non enregistre (' + r.status + ')');
               l.querySelector('select').value = l.dataset.retenu; return; }
  const d = await r.json();
  l.dataset.retenu = d.retenu;
  l.classList.toggle('force', d.force);
  const s = l.querySelector('select');
  s.value = d.retenu; s.classList.toggle('force', d.force);
  majBilan(d.bilan);
}

function signaler(texte){
  const e = document.getElementById('alerte');
  e.textContent = texte;
  e.hidden = false;
  clearTimeout(signaler.t);
  signaler.t = setTimeout(() => { e.hidden = true; }, 8000);
}

document.addEventListener('click', e => {
  const b = e.target.closest('.lire');
  if (b) return lire(b.closest('.ligne'));
  const h = e.target.closest('h2');
  if (h) { h.classList.toggle('replie'); h.nextElementSibling.hidden = h.classList.contains('replie'); }
});
document.addEventListener('change', e => {
  const s = e.target.closest('select');
  if (s) poser(s.closest('.ligne'), s.value);
});
document.addEventListener('focusin', e => {
  const l = e.target.closest('.ligne');
  if (l) courant = l;
});

// --- clavier : c'est lui qui rend 1132 morceaux tenables ---
document.addEventListener('keydown', e => {
  const cible = e.target;
  if (cible && cible.matches && cible.matches('select, input') && e.key !== 'Escape') return;
  const k = e.key.toLowerCase();
  if (k === '?') { e.preventDefault(); basculerAide(); return; }
  if (k === 'escape') { document.getElementById('aide').hidden = true; return; }
  if (k === ' ') { e.preventDefault();
    if (!courant) voisin(1);
    else if (lecteur.src && courant.classList.contains('joue'))
      lecteur.paused ? lecteur.play() : lecteur.pause();
    else lire(courant);
    return; }
  if (k === 'j' || e.key === 'ArrowDown') { e.preventDefault(); voisin(1); return; }
  if (k === 'k' || e.key === 'ArrowUp')   { e.preventDefault(); voisin(-1); return; }
  if (k === 'enter') { e.preventDefault();
    const s = visibles().filter(l => l.classList.contains('limite') && !l.classList.contains('force'));
    const i = s.indexOf(courant);
    if (s.length) selectionner(s[(i + 1) % s.length]);
    return; }
  if (k >= '1' && k <= '6') { e.preventDefault();
    if (!courant) selectionner(visibles()[0]);   // ranger doit marcher des l'ouverture
    if (courant) { poser(courant, BACS[+k - 1]); voisin(1); }
    return; }
});
function basculerAide(){
  const a = document.getElementById('aide');
  a.hidden = !a.hidden;
}

function replier(saufPremier){
  document.querySelectorAll('h2').forEach((h, i) => {
    const ferme = saufPremier ? i > 0 : false;
    h.classList.toggle('replie', ferme);
    h.nextElementSibling.hidden = ferme;
  });
}
replier(true);

// --- filtres ---
document.querySelectorAll('.filtres button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.filtres button').forEach(x => x.setAttribute('aria-pressed', 'false'));
  b.setAttribute('aria-pressed', 'true');
  const f = b.dataset.f;
  replier(f === 'tous');
  document.querySelectorAll('.ligne').forEach(l => {
    l.hidden = !(f === 'tous'
      || (f === 'limites' && l.classList.contains('limite'))
      || (f === 'forces'  && l.classList.contains('force')));
  });
  document.querySelectorAll('h2').forEach(h => {
    const g = h.nextElementSibling;
    const n = [...g.querySelectorAll('.ligne')].filter(l => !l.hidden).length;
    h.hidden = n === 0;
    if (n === 0) g.hidden = true;
    h.querySelector('.n').textContent = n;
  });
  courant = null;
}));

function majBilan(b){
  document.getElementById('n-forces').textContent = b.forces;
  for (const [bac, n] of Object.entries(b.par_bac)) {
    const e = document.getElementById('c-' + bac);
    if (e) e.textContent = n;
  }
}
"""

SVG_LIRE = ('<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" '
            'aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>')


def rendre(rows):
    b = bilan(rows)
    par_bac = OrderedDict((x, []) for x in BACS)
    for r in rows:
        par_bac[r["retenu"]].append(r)

    corps = []
    for bac, items in par_bac.items():
        if not items:
            continue
        corps.append(
            f'<h2><span class="fleche">&#9660;</span> {html.escape(LIBELLE[bac])}'
            f' <span class="n num">{len(items)}</span></h2><div>')
        for r in items:
            opts = "".join(
                f'<option value="{o}"{" selected" if o == r["retenu"] else ""}>'
                f'{o}{" (propose)" if o == r["propose"] else ""}</option>' for o in BACS)
            cls = " ".join(filter(None, [
                "ligne", "force" if r["force"] else "",
                "limite" if r["limite"] else "", "" if r["jouable"] else "injouable"]))
            corps.append(f"""
<div class="{cls}" data-k="{html.escape(r['key'], quote=True)}"
     data-retenu="{r['retenu']}">
  <button class="lire" aria-label="Ecouter {html.escape(r['nom'][:60], quote=True)}"
          {'' if r['jouable'] else 'disabled'}>{SVG_LIRE}</button>
  <div class="infos">
    <div class="titre">{html.escape(r['nom'])}</div>
    <div class="detail"><span class="source">{html.escape(r['source'])}</span>
      &rsaquo; {html.escape(r['pourquoi'])}</div>
  </div>
  <div class="mesures num">
    <span><b>{r['bpm']:.1f}</b> BPM</span>
    <span>coul. <b>{r['happy']:.2f}</b></span>
    <span>agr. <b>{r['agressif']:.2f}</b></span>
  </div>
  <select class="{'force' if r['force'] else ''}"
          aria-label="Bac de destination">{opts}</select>
</div>""")
        corps.append("</div>")

    puces = "".join(
        f'<span class="puce{" a-moi" if x == "5_misc" else ""}">{x}'
        f' <b class="num" id="c-{x}">{b["par_bac"][x]}</b></span>' for x in BACS)
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KALBASSFM, classement dans les futurs bacs</title>
<style>{CSS}</style></head><body>
<header>
  <h1>Classement dans les futurs bacs</h1>
  <div class="repartition">{puces}</div>
  <div class="compte">
    <b>{b['total']}</b> morceaux &middot; <b id="n-forces">{b['forces']}</b> destinations
    corrig&eacute;es &agrave; la main &middot; <b>{b['limites']}</b> &agrave; port&eacute;e
    d'une fronti&egrave;re
    &middot; <kbd>?</kbd> pour les raccourcis
  </div>
</header>
<main>
  <div class="filtres">
    <button data-f="tous" aria-pressed="true">Tous</button>
    <button data-f="limites" aria-pressed="false">Sur une fronti&egrave;re</button>
    <button data-f="forces" aria-pressed="false">Mes corrections</button>
  </div>
  {''.join(corps)}
</main>
<div id="alerte" role="alert" hidden></div>
<footer>
  <audio id="lecteur" controls preload="none"></audio>
  <span id="encours">Espace pour &eacute;couter, 1 &agrave; 6 pour ranger</span>
  <span>Rien n'est d&eacute;plac&eacute; : ce classement pr&eacute;pare la bascule.</span>
</footer>
<div class="aide" id="aide" hidden onclick="basculerAide()">
  <div class="boite" onclick="event.stopPropagation()">
    <h3>Raccourcis</h3>
    <dl>
      <dt><kbd>Espace</kbd></dt><dd>&eacute;couter, ou pause</dd>
      <dt><kbd>J</kbd> <kbd>K</kbd></dt><dd>morceau suivant, pr&eacute;c&eacute;dent</dd>
      <dt><kbd>1</kbd>&hellip;<kbd>6</kbd></dt><dd>ranger dans le bac, puis avancer</dd>
      <dt><kbd>Entr&eacute;e</kbd></dt><dd>sauter au prochain cas de fronti&egrave;re</dd>
      <dt><kbd>Echap</kbd></dt><dd>fermer</dd>
    </dl>
  </div>
</div>
<script>{JS.replace('__BACS__', json.dumps(BACS))}</script></body></html>"""


# --------------------------------------------------------------------------- serveur

class Handler(ra.Handler):
    # `index` reste ce qu'attend serve_audio() de review_analyse : cle -> chemin.
    # Les enregistrements complets vivent a cote, dans `fiches`. Echanger `index`
    # le temps d'une requete casserait des deux lectures concurrentes (le serveur
    # est multi-thread, et le prefetch tire pendant que le morceau joue).
    index = {}
    fiches = {}

    @classmethod
    def indexer(cls, rows):
        cls.fiches = {r["key"]: r for r in rows}
        cls.index = {r["key"]: r["path"] for r in rows}

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        if p.path in ("/", "/index.html"):
            rows = lignes()
            Handler.indexer(rows)
            return self._send(200, rendre(rows))
        if p.path == "/audio":
            return self.serve_audio(q.get("k", [""])[0])
        return self._send(404, b"nope")

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/decision":
            return self._send(404, b"nope")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, b"json invalide")
        cle = (payload.get("key") or "").strip()
        bac = (payload.get("bac") or "").strip()
        if cle not in Handler.fiches:
            return self._send(404, b"cle inconnue")
        if bac not in BACS:
            return self._send(400, b"bac inconnu")

        dec = charger()
        prop = Handler.fiches[cle]["propose"]
        # Revenir sur la proposition efface la correction plutot que d'enregistrer
        # une egalite : le morceau ne doit pas compter comme corrige a la main.
        if bac == prop:
            dec.pop(cle, None)
        else:
            dec[cle] = bac
        ecrire(dec)
        rows = lignes()
        Handler.indexer(rows)
        return self._json({"retenu": bac, "force": bac != prop, "bilan": bilan(rows)})


# --------------------------------------------------------------------------- main

def rapport(rows):
    b = bilan(rows)
    print("%d morceaux, %d destinations corrigees a la main, %d cas limites\n"
          % (b["total"], b["forces"], b["limites"]))
    for bac in BACS:
        n = b["par_bac"][bac]
        print("  %-11s %4d  (%4.1f%%)" % (bac, n, 100 * n / b["total"] if b["total"] else 0))
    forces = [r for r in rows if r["force"]]
    if forces:
        print("\nCorrections a la main :")
        for r in forces[:30]:
            print("  %-46s %s -> %s" % (r["nom"][:46], r["propose"], r["retenu"]))
        if len(forces) > 30:
            print("  ... et %d autres" % (len(forces) - 30))


def exporter(rows):
    """Le plan de bascule, relisible hors de l'interface avant de l'executer."""
    with open(EXPORT_PATH, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["fichier", "bac_actuel", "bac_propose", "bac_retenu",
                    "corrige_main", "bpm", "couleur", "agressivite", "genre"])
        for r in rows:
            w.writerow([r["nom"], r["source"], r["propose"], r["retenu"],
                        "oui" if r["force"] else "", f"{r['bpm']:.1f}",
                        f"{r['happy']:.2f}", f"{r['agressif']:.2f}", r["genre"]])
    print("%d lignes ecrites dans %s" % (len(rows), EXPORT_PATH))
    # Tous changent de dossier : les six bacs sont neufs. Ce qui compte, c'est
    # la part que la grille decide seule et celle que tu as reprise a la main.
    b = bilan(rows)
    print("Les %d changent de dossier (les six bacs sont neufs)." % b["total"])
    print("%d tranches par la grille, %d repris a la main."
          % (b["total"] - b["forces"], b["forces"]))


def verifier_js():
    """Le JS est une chaine Python : une apostrophe de travers le casse en
    entier et la page part muette, sans que rien ne le signale cote serveur.
    C'est arrive une fois. Si node est la, on relit avant d'ouvrir le port."""
    import re
    import shutil
    import subprocess
    import tempfile
    node = shutil.which("node")
    if not node:
        return True
    js = re.search(r"<script>(.*?)</script>", rendre([]), re.S)
    if not js:
        return True
    chemin = os.path.join(tempfile.gettempdir(), "classify_new_verif.js")
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.write(js.group(1))
    try:
        r = subprocess.run([node, "--check", chemin], capture_output=True, text=True)
    finally:
        os.remove(chemin)
    if r.returncode:
        print("JAVASCRIPT CASSE, la page serait inerte :")
        print(r.stderr.strip()[:600])
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--rapport", action="store_true")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    if args.reset:
        if os.path.exists(DECISIONS_PATH):
            os.remove(DECISIONS_PATH)
            print("Corrections effacees, la grille reprend la main partout.")
        else:
            print("Aucune correction a effacer.")
        return

    rows = lignes()
    Handler.indexer(rows)
    if not rows:
        print("metadata.json est vide.")
        return
    if args.export:
        return exporter(rows)
    rapport(rows)
    if args.rapport:
        return

    if not verifier_js():
        return 1
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"\nClassement : {url}")
    print("Aucun fichier n'est deplace. Ferme cette fenetre pour arreter.\n")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nArrete. Corrections conservees dans classify_new_decisions.json.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    sys.exit(main() or 0)
