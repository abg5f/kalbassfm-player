#!/usr/bin/env python3
"""Simulation de la nouvelle repartition house : ecouter, valider, corriger.

But : decider si la grille proposee tient a l'oreille AVANT de reorganiser 1097
fichiers, neuf playlists AzuraCast et l'horloge de la station.

LA GRILLE TESTEE — deux axes verifies independants (correlations +0.01 / -0.06 /
+0.03 sur les 1097 morceaux house), le tempo pour l'heure, la couleur pour la
texture :

    house_sunrise   BPM < 120
    house_solaire   120-127 et mood.happy >= 0.45
    house_deep      120-127 et mood.happy <  0.45
    house_club      BPM >= 127

`mood.happy` est le seul axe de couleur disponible et il est CORRECT (le modele
declare ["happy","non_happy"], le code lit bien l'indice 0). C'est justement ce
qu'on vient verifier : si les desaccords se concentrent sur la frontiere
happy=0.45, l'axe ne s'entend pas et la grille doit retomber sur le genre.

ECHANTILLONNAGE — 20 morceaux par bac, moitie/moitie :
    10 "coeur"     : loin des seuils, ce que le bac contient typiquement.
    10 "frontiere" : collees au seuil. C'est la que la grille se valide ; un
                     tirage purement aleatoire ne montrerait que des evidences.
Le taux d'accord est calcule separement sur les deux, parce qu'ils ne disent pas
la meme chose : un desaccord au coeur condamne le bac, un desaccord en frontiere
demande juste de deplacer le seuil.

Aucun fichier n'est deplace, aucune playlist touchee : ce script ne fait
qu'ecrire des reponses dans simulation_bins.json.

Usage :
    python simulate_bins.py
    python simulate_bins.py --par-bac 30 --port 8138
    python simulate_bins.py --rapport      # taux d'accord, sans serveur
    python simulate_bins.py --reset
"""
import argparse
import html
import json
import ntpath
import os
import random
import sys
import threading
import urllib.parse
import webbrowser
from collections import OrderedDict
from http.server import ThreadingHTTPServer

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)

import analyse_new_tracks as ana  # noqa: E402
import review_analyse as ra  # noqa: E402  (moteur audio : Range, cache, lecteur unique)

REPONSES_PATH = os.path.join(TOOLS_DIR, "simulation_bins.json")
DEFAULT_PORT = 8138
GRAINE = 20260908          # tirage reproductible : reouvrir la page ne rebat pas les cartes

BPM_BAS, BPM_HAUT = 120.0, 127.0
HAPPY_SEUIL = 0.45
BACS = ["house_sunrise", "house_solaire", "house_deep", "house_club"]
LIBELLE = {
    "house_sunrise": "Sunrise — lent, 6-10h et 2-5h",
    "house_solaire": "Solaire — plein jour, 10-18h",
    "house_deep": "Deep — soir, 18-22h",
    "house_club": "Club — nuit, 22-2h",
}

# Bacs actuels dont on tire l'echantillon (la famille house au sens large).
SOURCE = ("1_chill", "2_groove", "3_house", "4_deep", "5_clubhouse")


# --------------------------------------------------------------------------- grille

def bpm_de(t):
    return float(t.get("bpm") or 0.0)


def happy_de(t):
    return float((t.get("mood") or {}).get("happy", 0.0))


def bac_propose(t):
    b = bpm_de(t)
    if b < BPM_BAS:
        return "house_sunrise"
    if b >= BPM_HAUT:
        return "house_club"
    return "house_solaire" if happy_de(t) >= HAPPY_SEUIL else "house_deep"


def marge(t):
    """Distance normalisee au seuil le plus proche. 0 = pile sur la frontiere.

    Les deux axes n'ont pas la meme echelle : on ramene 8 BPM et 0.25 de happy
    a la meme unite, sinon le tempo ecraserait toujours la couleur.
    """
    b, h = bpm_de(t), happy_de(t)
    d_bas = abs(b - BPM_BAS) / 8.0
    d_haut = abs(b - BPM_HAUT) / 8.0
    if b < BPM_BAS:
        return d_bas
    if b >= BPM_HAUT:
        return d_haut
    return min(d_bas, d_haut, abs(h - HAPPY_SEUIL) / 0.25)


def axe_frontiere(t):
    """Quel seuil ce morceau teste — pour savoir lequel bouger en cas de desaccord."""
    b, h = bpm_de(t), happy_de(t)
    cands = [(abs(b - BPM_BAS) / 8.0, "tempo 120"), (abs(b - BPM_HAUT) / 8.0, "tempo 127")]
    if BPM_BAS <= b < BPM_HAUT:
        cands.append((abs(h - HAPPY_SEUIL) / 0.25, "couleur 0.45"))
    return min(cands)[1]


# --------------------------------------------------------------------------- echantillon

def charger_echantillon(par_bac):
    """20 par bac : les 10 marges les plus larges, les 10 plus etroites.

    Tire dans un vivier plus grand que necessaire puis melange, pour que deux
    lancements ne donnent pas exactement les memes titres tout en restant
    reproductibles (graine fixe).
    """
    metadata = ana.load_metadata()
    vivier = []
    for t in metadata:
        if ntpath.basename(ntpath.dirname(t.get("path") or "")) not in SOURCE:
            continue
        if not bpm_de(t):
            continue
        chemin = ana.LOCAL(t.get("path") or "")
        if not os.path.exists(chemin):
            continue        # un morceau injouable ne se valide pas a l'oreille
        vivier.append(t)

    rnd = random.Random(GRAINE)
    par_groupe = OrderedDict((b, []) for b in BACS)
    for bac in BACS:
        cands = [t for t in vivier if bac_propose(t) == bac]
        cands.sort(key=marge)
        n = par_bac // 2
        proches = cands[: n * 3]
        loin = cands[-n * 3:]
        rnd.shuffle(proches)
        rnd.shuffle(loin)
        for t in proches[:n]:
            par_groupe[bac].append((t, "frontiere"))
        for t in loin[:par_bac - n]:
            par_groupe[bac].append((t, "coeur"))
    return par_groupe


def cle_de(t):
    return ana.key_of(t.get("path"))


# --------------------------------------------------------------------------- reponses

def charger_reponses():
    if not os.path.exists(REPONSES_PATH):
        return {}
    try:
        with open(REPONSES_PATH, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def ecrire_reponses(d):
    with open(REPONSES_PATH, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1, sort_keys=True)


def bilan(groupes, reponses):
    """Taux d'accord global, par bac, et separement coeur / frontiere."""
    tot = {"repondu": 0, "accord": 0, "total": 0}
    par_bac, par_type = {}, {"coeur": [0, 0], "frontiere": [0, 0]}
    desaccords_axe = {}
    for bac, items in groupes.items():
        a = r = 0
        for t, typ in items:
            tot["total"] += 1
            rep = reponses.get(cle_de(t))
            if not rep:
                continue
            tot["repondu"] += 1
            r += 1
            ok = rep.get("verdict") == "ok"
            if ok:
                a += 1
                tot["accord"] += 1
            par_type[typ][1] += 1
            if ok:
                par_type[typ][0] += 1
            if not ok and typ == "frontiere":
                axe = axe_frontiere(t)
                desaccords_axe[axe] = desaccords_axe.get(axe, 0) + 1
        par_bac[bac] = {"repondu": r, "accord": a, "total": len(items)}
    return {
        "global": tot,
        "par_bac": par_bac,
        "coeur": {"accord": par_type["coeur"][0], "repondu": par_type["coeur"][1]},
        "frontiere": {"accord": par_type["frontiere"][0], "repondu": par_type["frontiere"][1]},
        "desaccords_par_axe": desaccords_axe,
    }


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "—"


# --------------------------------------------------------------------------- page

CSS = ra.CSS + """
.sim .row{grid-template-columns:1fr 300px}
.tag{font-size:11px;padding:1px 7px;border-radius:10px;margin-left:6px}
.tag.frontiere{background:#3a2f1a;color:#e0b23c}
.tag.coeur{background:#1d2b1f;color:#4caf50}
.bacprop{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;
background:#22303d;color:#5b9dd9;font-weight:600;margin-right:7px}
.row.rep-ok,.row.rep-non{opacity:.55}
.row.rep-ok{border-left-color:var(--ok)}
.row.rep-non{border-left-color:var(--bad)}
.bilan{display:flex;gap:22px;flex-wrap:wrap;margin-top:8px}
.bilan div{font-size:13px}
.bilan b{font-size:17px;color:var(--txt)}
select.corr{background:var(--line);color:var(--txt);border:1px solid transparent;
border-radius:6px;padding:6px 7px;font-size:12px;font-family:inherit;cursor:pointer}
select.corr[data-actif="1"]{border-color:var(--bad);color:var(--bad);font-weight:600}
"""

JS = r"""
document.addEventListener('click', e => {
  const b = e.target.closest('.acts button');
  if(!b) return;
  const row = b.closest('.row');
  if(b.dataset.d === 'play') return play(row);
  repondre(row, b.dataset.d, null);
});
document.addEventListener('change', e => {
  const s = e.target.closest('select.corr');
  if(s) repondre(s.closest('.row'), 'non', s.value);
});
const player = document.getElementById('player');
function play(row){
  document.querySelectorAll('.row.playing').forEach(r => r.classList.remove('playing'));
  row.classList.add('playing');
  document.getElementById('nowplaying').textContent = row.querySelector('.nm').textContent;
  player.src = '/audio?k=' + encodeURIComponent(row.dataset.k);
  player.play().catch(() => {});
  const l = [...document.querySelectorAll('.row')], nx = l[l.indexOf(row) + 1];
  if(nx && !nx.dataset.pf){ nx.dataset.pf = 1;
    fetch('/audio?k=' + encodeURIComponent(nx.dataset.k), {headers:{Range:'bytes=0-524287'}})
      .then(r => r.arrayBuffer()).catch(() => {}); }
}
async function repondre(row, verdict, correction){
  const r = await fetch('/reponse', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({key: row.dataset.k, verdict: verdict, correction: correction})});
  if(!r.ok){ alert('Echec : ' + r.status); return; }
  const d = await r.json();
  row.classList.remove('rep-ok','rep-non');
  if(d.verdict) row.classList.add(d.verdict === 'ok' ? 'rep-ok' : 'rep-non');
  row.querySelectorAll('.acts button[data-d="ok"],.acts button[data-d="non"]').forEach(b => {
    b.classList.toggle('on-ok', b.dataset.d === 'ok' && d.verdict === 'ok');
    b.classList.toggle('on-bad', b.dataset.d === 'non' && d.verdict === 'non');
  });
  const s = row.querySelector('select.corr');
  if(s){ s.dataset.actif = d.correction ? '1' : '0'; if(d.correction) s.value = d.correction; }
  maj(d.bilan);
}
function maj(b){
  const set = (id,v) => { const e = document.getElementById(id); if(e) e.textContent = v; };
  set('n-repondu', b.global.repondu + ' / ' + b.global.total);
  set('n-accord', b.global.repondu ? Math.round(100*b.global.accord/b.global.repondu) + '%' : '—');
  set('n-coeur', b.coeur.repondu ? Math.round(100*b.coeur.accord/b.coeur.repondu) + '%' : '—');
  set('n-frontiere', b.frontiere.repondu ? Math.round(100*b.frontiere.accord/b.frontiere.repondu) + '%' : '—');
  const ax = Object.entries(b.desaccords_par_axe).sort((a,c)=>c[1]-a[1])
      .map(([k,v]) => k + ' (' + v + ')').join(', ');
  set('n-axes', ax || '—');
  document.getElementById('barfill').style.width =
      (b.global.total ? 100*b.global.repondu/b.global.total : 0) + '%';
}
document.addEventListener('play', e => {
  document.querySelectorAll('audio').forEach(a => { if(a !== e.target) a.pause(); });
}, true);

// Reprendre : 80 morceaux ne s'ecoutent pas d'une traite, et rien n'est plus
// agacant que de rechercher a la main ou on s'est arrete.
function reprendre(){
  const n = document.querySelector('.row.todo');
  if(!n){ alert('Tout est ecoute.'); return; }
  n.scrollIntoView({block:'center', behavior:'smooth'});
  n.style.outline = '2px solid var(--acc)';
  setTimeout(() => { n.style.outline = ''; }, 1800);
}
// Au chargement, on se place directement sur la premiere non ecoutee.
addEventListener('load', () => {
  const n = document.querySelector('.row.todo');
  if(n && document.querySelector('.row.rep-ok, .row.rep-non')) n.scrollIntoView({block:'center'});
});
"""


def rendre(groupes, reponses):
    b = bilan(groupes, reponses)
    corps = []
    for bac, items in groupes.items():
        faits = sum(1 for tt, _ in items if reponses.get(cle_de(tt)))
        corps.append(f'<h2>{html.escape(LIBELLE[bac])} '
                     f'<span class="n">({faits}/{len(items)} &eacute;cout&eacute;s)</span></h2>')
        for t, typ in items:
            k = cle_de(t)
            rep = reponses.get(k) or {}
            v = rep.get("verdict")
            cls = " rep-ok" if v == "ok" else (" rep-non" if v == "non" else " todo")
            # Presélectionner le bac propose : sans `selected`, le navigateur
            # affiche la premiere option de la liste (sunrise) sur TOUTES les
            # lignes, ce qui laisse croire que tout est classe en sunrise.
            courant = rep.get("correction") or bac
            opts = "".join(
                f'<option value="{o}"{" selected" if o == courant else ""}>'
                f'{o.replace("house_", "")}</option>' for o in BACS)
            corps.append(f"""
<div class="row{cls}" data-k="{html.escape(k, quote=True)}">
  <div>
    <div class="nm">{html.escape(ntpath.basename(t.get('path') or ''))}</div>
    <div class="meta"><span class="bacprop">{bac.replace("house_", "")}</span>
      {bpm_de(t):.0f} BPM &middot; couleur {happy_de(t):.2f}
      <span class="tag {typ}">{typ}</span>
      <span class="badge">marge {marge(t):.2f}</span></div>
  </div>
  <div class="acts">
    <button class="play" data-d="play" title="Ecouter">&#9654;</button>
    <button class="{'on-ok' if v == 'ok' else ''}" data-d="ok">D'accord</button>
    <button class="{'on-bad' if v == 'non' else ''}" data-d="non">Non</button>
    <select class="corr" data-actif="{1 if rep.get('correction') else 0}"
            title="Le bac qui conviendrait">{opts}</select>
  </div>
</div>""")
    g = b["global"]
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<title>KALBASSFM - Simulation de repartition</title>
<style>{CSS}</style></head><body>
<header>
  <h1>KALBASSFM &mdash; Simulation de la nouvelle r&eacute;partition</h1>
  <div class="bar"><i id="barfill" style="width:{100*g['repondu']/g['total'] if g['total'] else 0}%"></i></div>
  <div class="bilan">
    <div>&eacute;cout&eacute;s <b id="n-repondu">{g['repondu']} / {g['total']}</b></div>
    <div>accord global <b id="n-accord">{pct(g['accord'], g['repondu'])}</b></div>
    <div>au c&oelig;ur <b id="n-coeur">{pct(b['coeur']['accord'], b['coeur']['repondu'])}</b></div>
    <div>en fronti&egrave;re <b id="n-frontiere">{pct(b['frontiere']['accord'], b['frontiere']['repondu'])}</b></div>
    <div>seuils contest&eacute;s <b id="n-axes">&mdash;</b></div>
  </div>
</header>
<main class="sim">
  <div class="panel">
    <h3>Comment lire &ccedil;a</h3>
    <div class="hint">
      Un d&eacute;saccord <b>au c&oelig;ur</b> condamne le bac : la grille se trompe sur ce qu'il contient.
      Un d&eacute;saccord <b>en fronti&egrave;re</b> demande seulement de d&eacute;placer un seuil &mdash; regarde
      alors quel seuil revient dans &laquo;&nbsp;seuils contest&eacute;s&nbsp;&raquo;.
      Rien n'est d&eacute;plac&eacute; ni envoy&eacute; par cette page.
    </div>
  </div>
  {''.join(corps)}
</main>
<footer>
  <button id="reprendre" onclick="reprendre()">Reprendre o&ugrave; j'en &eacute;tais</button>
  <div class="player">
    <audio id="player" controls preload="none"></audio>
    <span id="nowplaying">Clique sur &#9654; pour &eacute;couter</span>
  </div>
  <span>Simulation seule &mdash; aucun fichier, aucune playlist touch&eacute;s.</span>
</footer>
<script>{JS}</script></body></html>"""


# --------------------------------------------------------------------------- serveur

class Handler(ra.Handler):
    """Herite le moteur audio de review_analyse (Range, cache, prefetch)."""
    index = {}
    groupes = OrderedDict()
    propose = {}

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        if p.path in ("/", "/index.html"):
            return self._send(200, rendre(Handler.groupes, charger_reponses()))
        if p.path == "/bilan":
            return self._json(bilan(Handler.groupes, charger_reponses()))
        if p.path == "/audio":
            return self.serve_audio(q.get("k", [""])[0])
        return self._send(404, b"nope")

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/reponse":
            return self._send(404, b"nope")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, b"json invalide")
        key = (payload.get("key") or "").strip()
        verdict = (payload.get("verdict") or "").strip()
        correction = payload.get("correction")
        if key not in Handler.index:
            return self._send(404, b"cle inconnue")
        if verdict not in ("ok", "non"):
            return self._send(400, b"verdict invalide")
        if correction and correction not in BACS:
            return self._send(400, b"bac inconnu")

        rep = charger_reponses()
        entree = dict(rep.get(key) or {})
        # Reposer le menu sur le bac propose, c'est etre d'accord — pas
        # enregistrer un desaccord vers la meme destination.
        propose = Handler.propose.get(key)
        if verdict == "non" and correction and correction == propose:
            verdict, correction = "ok", None
        entree["verdict"] = verdict
        # Un "d'accord" efface la correction : garder les deux serait contradictoire.
        entree["correction"] = correction if verdict == "non" else None
        rep[key] = entree
        ecrire_reponses(rep)
        return self._json({"verdict": verdict, "correction": entree["correction"],
                           "bilan": bilan(Handler.groupes, rep)})


# --------------------------------------------------------------------------- main

def afficher_rapport(groupes, reponses):
    b = bilan(groupes, reponses)
    g = b["global"]
    print(f"Ecoutes : {g['repondu']} / {g['total']}")
    print(f"Accord global : {pct(g['accord'], g['repondu'])}")
    print(f"  au coeur     : {pct(b['coeur']['accord'], b['coeur']['repondu'])}"
          f"  ({b['coeur']['repondu']} ecoutes)")
    print(f"  en frontiere : {pct(b['frontiere']['accord'], b['frontiere']['repondu'])}"
          f"  ({b['frontiere']['repondu']} ecoutes)")
    print("\nPar bac :")
    for bac, s in b["par_bac"].items():
        print(f"  {bac:16} {pct(s['accord'], s['repondu']):>5}  ({s['repondu']}/{s['total']} ecoutes)")
    if b["desaccords_par_axe"]:
        print("\nSeuils contestes :")
        for axe, n in sorted(b["desaccords_par_axe"].items(), key=lambda x: -x[1]):
            print(f"  {axe:14} {n} desaccord(s)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--par-bac", type=int, default=20, help="morceaux par bac (defaut 20)")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--rapport", action="store_true", help="afficher le bilan et sortir")
    ap.add_argument("--reset", action="store_true", help="effacer les reponses et sortir")
    args = ap.parse_args()

    if args.reset:
        if os.path.exists(REPONSES_PATH):
            os.remove(REPONSES_PATH)
            print("Reponses effacees.")
        else:
            print("Aucune reponse a effacer.")
        return

    groupes = charger_echantillon(args.par_bac)
    Handler.groupes = groupes
    Handler.index = {cle_de(t): t.get("path") for items in groupes.values() for t, _ in items}
    Handler.propose = {cle_de(t): bac for bac, items in groupes.items() for t, _ in items}
    total = sum(len(v) for v in groupes.values())
    if not total:
        print("Echantillon vide — metadata.json ne contient aucun morceau house jouable.")
        return
    for bac, items in groupes.items():
        print(f"{bac:16} {len(items):3} morceaux")

    if args.rapport:
        print()
        afficher_rapport(groupes, charger_reponses())
        return

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"\nSimulation : {url}")
    print("Aucun fichier n'est deplace. Ferme cette fenetre pour arreter.\n")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nArrete. Reponses conservees dans simulation_bins.json.")
        afficher_rapport(groupes, charger_reponses())
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
