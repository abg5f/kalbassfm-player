#!/usr/bin/env python3
"""Revue du fonds : morceaux trop sombres, trop techno, et les deux bacs DnB — sur la bibliotheque EN LIGNE.

Comble le seul vrai manque du pipeline : jusqu'ici les arbitrages ne portaient
que sur la file d'ingestion. Une fois un morceau sur AzuraCast, rien ne
permettait de le retirer sans passer par l'interface web du serveur.

SELECTION — deux axes verifies corrects (contrairement a mood.party et
mood.relaxed, dont l'extracteur lit la mauvaise classe du softmax) :

    sombre : mood.happy < 0.20 ET mood.aggressive > 0.25
    techno : genre de tete techno/trance/hardcore ET mood.happy < 0.25

DEUX SORTS, et ils ne sont pas symetriques :

    GARDER    — ne fait rien du tout, le morceau reste ou il est.
    SUPPRIMER — retire d'AzuraCast (fichier + entree bibliotheque, via l'API,
                IRREVERSIBLE), deplace la copie locale dans New_prog/_a_revoir/
                (RECUPERABLE) et retire l'entree de metadata.json.

Le local n'est jamais efface : si l'oreille se trompe, le fichier est encore la.
Le serveur, lui, ne pardonne pas — d'ou la confirmation explicite avant
d'appliquer, et le fait que rien ne parte tant que le bouton n'est pas presse.

Usage :
    python review_dark.py
    python review_dark.py --port 8139
    python review_dark.py --rapport   # compte les decisions, sans serveur
    python review_dark.py --reset
"""
import argparse
import html
import json
import ntpath
import os
import shutil
import sys
import threading
import urllib.parse
import webbrowser
from collections import OrderedDict
from datetime import date
from http.server import ThreadingHTTPServer

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)

import analyse_new_tracks as ana  # noqa: E402
import review_analyse as ra  # noqa: E402  (moteur audio : Range, cache, lecteur unique)
import sync_library as sl  # noqa: E402  (appel API AzuraCast + media_id)
import azuracast_upload as up  # noqa: E402  (envoi SFTP vers le nouveau bac)
import classify_bins  # noqa: E402  (liste des bacs — source de verite unique)

DECISIONS_PATH = os.path.join(TOOLS_DIR, "review_dark_decisions.json")
DEFAULT_PORT = 8139

SEUIL_HAPPY_SOMBRE = 0.20
SEUIL_AGGRESSIF = 0.25
SEUIL_HAPPY_TECHNO = 0.25
GENRES_DURS = ("techno", "trance", "hardcore", "gabber", "hardstyle", "schranz")
# Les deux bacs DnB, a trancher en bloc : le liquid est revendique par la
# station ("100% House & some Liquid DnB"), la jungle non. Ce qui les separe
# n'est PAS la couleur (medianes 0.09 et 0.10, les deux sont sombres par
# nature) mais l'AGRESSIVITE : 0.05 en liquid contre 0.24 en jungle.
BACS_DNB = ("8_jungle", "9_liquid")
SEUIL_LIQUIDE = 0.15   # sous ce seuil, l'agressivite est celle du liquid


# --------------------------------------------------------------------------- selection

def happy(t):
    return float((t.get("mood") or {}).get("happy", 0.0))


def aggressif(t):
    return float((t.get("mood") or {}).get("aggressive", 0.0))


def genre_tete(t):
    g = t.get("genres") or []
    if not g:
        return ""
    label = g[0][0] if isinstance(g[0], (list, tuple)) else str(g[0])
    return label.split("---")[-1].strip()


def bac_de(t):
    return ntpath.basename(ntpath.dirname(t.get("path") or ""))


def motifs(t):
    """Pourquoi ce morceau est propose — affiche tel quel dans la page."""
    out = []
    if happy(t) < SEUIL_HAPPY_SOMBRE and aggressif(t) > SEUIL_AGGRESSIF:
        out.append(f"sombre (couleur {happy(t):.2f}, agressivite {aggressif(t):.2f})")
    if any(k in genre_tete(t).lower() for k in GENRES_DURS) and happy(t) < SEUIL_HAPPY_TECHNO:
        out.append(f"{genre_tete(t)} (couleur {happy(t):.2f})")
    bac = bac_de(t)
    if bac in BACS_DNB:
        doux = aggressif(t) < SEUIL_LIQUIDE
        out.append(f"DnB, agressivite {aggressif(t):.2f} : "
                   f"{'proche du liquid' if doux else 'plutot dur'}")
    return out


def candidats():
    """Les morceaux a revoir, groupes par bac, du plus sombre au moins sombre."""
    meta = ana.load_metadata()
    rows = []
    for t in meta:
        m = motifs(t)
        if not m:
            continue
        chemin = t.get("path") or ""
        rows.append({
            "key": ana.key_of(chemin),
            "nom": ntpath.basename(chemin),
            "bac": bac_de(t),
            "path": chemin,
            "bpm": round(float(t.get("bpm") or 0), 0),
            "happy": round(happy(t), 2),
            "aggressif": round(aggressif(t), 2),
            "genre": genre_tete(t),
            "motifs": m,
            # Un fichier absent en local ne peut pas etre ecoute : on le signale
            # plutot que de servir un lecteur qui repondra 404.
            "jouable": os.path.exists(ana.LOCAL(chemin)),
        })
    rows.sort(key=lambda r: (r["bac"], r["happy"]))
    par_bac = OrderedDict()
    for r in rows:
        par_bac.setdefault(r["bac"], []).append(r)
    return par_bac


# --------------------------------------------------------------------------- decisions

def charger():
    """{cle: {"decision": "garder"|"supprimer"|None, "bac": "3_house"|None}}.

    Tolere l'ancienne forme plate ({cle: "garder"}) : ce fichier est de l'etat
    de travail, le migrer silencieusement vaut mieux que de perdre des
    decisions deja prises a l'oreille.
    """
    if not os.path.exists(DECISIONS_PATH):
        return {}
    try:
        with open(DECISIONS_PATH, encoding="utf-8") as fh:
            brut = json.load(fh) or {}
    except (json.JSONDecodeError, OSError):
        return {}
    out = {}
    for k, v in brut.items():
        if isinstance(v, str):
            v = {"decision": v, "bac": None}
        if not isinstance(v, dict):
            continue
        d = v.get("decision") if v.get("decision") in ("garder", "supprimer") else None
        b = v.get("bac") if v.get("bac") in classify_bins.NEW_BINS else None
        if d or b:
            out[k] = {"decision": d, "bac": b}
    return out


def poser(key, champ, valeur):
    """Ecrit un champ sans effacer l'autre : choisir un bac ne doit pas annuler
    un « garder » deja rendu, et inversement."""
    dec = charger()
    e = dict(dec.get(key) or {"decision": None, "bac": None})
    e[champ] = valeur or None
    dec[key] = e
    ecrire(dec)
    return dec


def ecrire(d):
    propre = {k: v for k, v in d.items() if v.get("decision") or v.get("bac")}
    with open(DECISIONS_PATH, "w", encoding="utf-8") as fh:
        json.dump(propre, fh, ensure_ascii=False, indent=1, sort_keys=True)


def bilan(par_bac, dec):
    total = a_supprimer = a_deplacer = tranches = 0
    for v in par_bac.values():
        for r in v:
            total += 1
            e = dec.get(r["key"]) or {}
            bouge = bool(e.get("bac")) and e["bac"] != r["bac"]
            if e.get("decision") or bouge:
                tranches += 1
            if e.get("decision") == "supprimer":
                a_supprimer += 1
            elif bouge:
                a_deplacer += 1
    return {"total": total, "tranches": tranches, "a_supprimer": a_supprimer,
            "a_deplacer": a_deplacer, "gardes": tranches - a_supprimer - a_deplacer}


# --------------------------------------------------------------------------- suppression

def supprimer(rows):
    """Retire d'AzuraCast puis met la copie locale de cote. Dans cet ordre :
    si l'API echoue, le fichier local reste en place et l'operation peut etre
    rejouee telle quelle — l'inverse laisserait un morceau a l'antenne sans
    copie locale, exactement le genre de fantome qu'on vient de nettoyer."""
    hold = ana.LOCAL(ana.HOLD_FOLDER)
    os.makedirs(hold, exist_ok=True)
    meta = ana.load_metadata()
    faits, echecs, lignes = [], [], []
    par_bac = {}
    for r in rows:
        par_bac.setdefault(r["bac"], []).append(r)

    for bac, lot in par_bac.items():
        st, data = sl.call("GET", f"/station/{sl.STATION}/files/list?currentDirectory={bac}")
        if st != 200:
            for r in lot:
                echecs.append((r["nom"], f"liste {bac} indisponible ({st})"))
            continue
        brut = data["rows"] if isinstance(data, dict) and "rows" in data else data
        medias = {x["path"].split("/", 1)[-1]: x["media"]["id"]
                  for x in brut if x.get("type") == "media"}
        for r in lot:
            mid = medias.get(r["nom"])
            if mid is not None:
                s, res = sl.call("DELETE", f"/station/{sl.STATION}/file/{mid}")
                if s not in (200, 204):
                    echecs.append((r["nom"], f"AzuraCast {s}"))
                    continue
            # mid absent = deja retire du serveur : on poursuit cote local.
            src = ana.LOCAL(r["path"])
            if os.path.exists(src):
                dest = os.path.join(hold, r["nom"])
                base, ext = os.path.splitext(dest)
                i = 2
                while os.path.exists(dest):
                    dest = f"{base}_{i}{ext}"
                    i += 1
                shutil.move(src, dest)
            lignes.append(f"{r['nom']}\trevue-sombre\t{date.today()}\t"
                          f"{', '.join(r['motifs'])}\n")
            meta = [e for e in meta if ana.key_of(e.get("path")) != r["key"]]
            faits.append(r["nom"])

    if lignes:
        with open(ana.LOCAL(ana.HOLD_LOG), "a", encoding="utf-8") as fh:
            fh.writelines(lignes)
        ana.save_metadata(meta)
    return faits, echecs


def deplacer(rows):
    """Change le bac d'un morceau DEJA en ligne : local et AzuraCast ensemble.

    Ordre : envoyer d'abord dans le nouveau bac, supprimer l'ancien ensuite,
    bouger le local en dernier. A chaque etape, un echec laisse un etat
    rattrapable — et le morceau n'est jamais absent de l'antenne, meme une
    seconde. L'ordre inverse le ferait disparaitre entre la suppression et
    l'envoi.
    """
    meta = ana.load_metadata()
    faits, echecs = [], []
    transport, sftp = up.open_sftp()
    if sftp is None:
        return [], [(r["nom"], "SFTP indisponible") for r in rows]
    try:
        for r in rows:
            cible, source = r["cible"], r["bac"]
            local = ana.LOCAL(r["path"])
            if not os.path.exists(local):
                echecs.append((r["nom"], "copie locale introuvable"))
                continue
            # 1. envoi dans le nouveau bac
            try:
                up.upload(sftp, cible, local)
            except up.RemoteAlreadyExists:
                pass          # deja la : le deplacement a ete amorce, on poursuit
            except Exception as e:                      # noqa: BLE001
                echecs.append((r["nom"], f"envoi vers {cible} : {e}"))
                continue
            # 2. retrait de l'ancien bac cote serveur
            st, data = sl.call("GET",
                               f"/station/{sl.STATION}/files/list?currentDirectory={source}")
            if st == 200:
                brut = data["rows"] if isinstance(data, dict) and "rows" in data else data
                mid = {x["path"].split("/", 1)[-1]: x["media"]["id"]
                       for x in brut if x.get("type") == "media"}.get(r["nom"])
                if mid is not None:
                    s, _ = sl.call("DELETE", f"/station/{sl.STATION}/file/{mid}")
                    if s not in (200, 204):
                        echecs.append((r["nom"], f"ancien exemplaire non retire ({s})"))
            # 3. deplacement local + metadata
            dest_dir = os.path.join(ana.LOCAL(ana.NEW_PROG), cible)
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, r["nom"])
            if not os.path.exists(dest):
                shutil.move(local, dest)
            for e in meta:
                if ana.key_of(e.get("path")) == r["key"]:
                    e["path"] = dest
            faits.append(f"{r['nom']} : {source} -> {cible}")
    finally:
        sftp.close()
        transport.close()
    if faits:
        ana.save_metadata(meta)
    return faits, echecs


# --------------------------------------------------------------------------- page

CSS = ra.CSS + """
.row{grid-template-columns:1fr 420px}
.row.d-garder{border-left-color:var(--ok);opacity:.55}
.row.d-supprimer{border-left-color:var(--bad);opacity:.55}
.row.injouable .nm{color:var(--dim);font-style:italic}
.row.d-deplace{border-left-color:var(--acc)}
select.bin{background:var(--line);color:var(--txt);border:1px solid transparent;
border-radius:6px;padding:6px 7px;font-size:12px;font-family:inherit;cursor:pointer}
select.bin:hover{border-color:var(--acc)}
select.bin.moved{border-color:var(--acc);color:var(--acc);font-weight:600}
.mot{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;
background:#3a2020;color:#e0a0a0;margin-right:5px}
"""

JS = r"""
document.addEventListener('click', e => {
  const b = e.target.closest('.acts button');
  if(!b) return;
  const row = b.closest('.row');
  if(b.dataset.d === 'play') return play(row);
  decide(row, b.dataset.d === 'undo' ? '' : b.dataset.d);
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
document.addEventListener('change', async e => {
  const sel = e.target.closest('select.bin');
  if(!sel) return;
  const row = sel.closest('.row');
  const r = await fetch('/bac', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({key: row.dataset.k, bac: sel.value})});
  if(!r.ok){ alert('Echec : ' + r.status); return; }
  const st = await r.json();
  sel.classList.toggle('moved', st.deplace);
  // Une decision explicite (garder / supprimer) l'emporte visuellement sur le
  // simple changement de bac : c'est elle qui decide du sort du morceau.
  if(!row.className.includes('d-garder') && !row.className.includes('d-supprimer'))
    row.classList.toggle('d-deplace', st.deplace);
  maj(st.bilan);
});
async function decide(row, d){
  const r = await fetch('/decision', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({key: row.dataset.k, decision: d})});
  if(!r.ok){ alert('Echec : ' + r.status); return; }
  const st = await r.json();
  row.className = 'row' + (st.decision ? ' d-' + st.decision : '')
                + (row.dataset.jouable === '0' ? ' injouable' : '');
  row.querySelectorAll('.acts button').forEach(b => {
    b.classList.toggle('on-ok', b.dataset.d === 'garder' && st.decision === 'garder');
    b.classList.toggle('on-bad', b.dataset.d === 'supprimer' && st.decision === 'supprimer');
    if(b.dataset.d === 'undo') b.style.display = st.decision ? '' : 'none';
  });
  maj(st.bilan);
}
function maj(b){
  const set = (id,v) => { const e=document.getElementById(id); if(e) e.textContent=v; };
  set('n-tranches', b.tranches); set('n-total', b.total);
  set('n-suppr', b.a_supprimer); set('n-gardes', b.gardes); set('n-depl', b.a_deplacer);
  document.getElementById('barfill').style.width =
      (b.total ? 100*b.tranches/b.total : 0) + '%';
  const btn = document.getElementById('btn-appliquer');
  btn.textContent = libelle(b);
  btn.disabled = (b.a_supprimer + b.a_deplacer) === 0;
}
function libelle(b){
  const p = [];
  if(b.a_supprimer) p.push('supprimer ' + b.a_supprimer);
  if(b.a_deplacer)  p.push('déplacer ' + b.a_deplacer);
  return p.length ? 'Appliquer : ' + p.join(', ') : 'Rien à appliquer';
}
document.addEventListener('play', e => {
  document.querySelectorAll('audio').forEach(a => { if(a !== e.target) a.pause(); });
}, true);
document.addEventListener('click', e => {
  const h = e.target.closest('.bachdr');
  if(h){ h.classList.toggle('closed'); h.nextElementSibling.hidden = h.classList.contains('closed'); }
});
async function appliquer(){
  const s = document.getElementById('n-suppr').textContent;
  const d = document.getElementById('n-depl').textContent;
  if(!confirm("Appliquer maintenant ?\n\n"
    + s + " a supprimer : retires d'AzuraCast (fichier ET entree de\n"
    + "bibliotheque, IRREVERSIBLE), copie locale mise dans _a_revoir/.\n\n"
    + d + " a deplacer : envoyes dans le nouveau bac, ancien exemplaire\n"
    + "retire du serveur, fichier local et metadata suivent.\n\n"
    + "Les morceaux marques \"garder\" ne bougent pas.")) return;
  const btn = document.getElementById('btn-appliquer');
  btn.disabled = true; btn.textContent = 'Application en cours...';
  const r = await fetch('/appliquer', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({confirm:'oui'})});
  const res = await r.json();
  alert(res.supprimes + ' supprime(s), ' + res.deplaces + ' deplace(s), '
        + res.echecs.length + ' echec(s).'
        + (res.echecs.length ? '\n\n' + res.echecs.map(e => e[0] + ' : ' + e[1]).join('\n') : ''));
  location.reload();
}
"""


def rendre(par_bac, dec):
    b = bilan(par_bac, dec)
    corps = []
    for bac, items in par_bac.items():
        faits = sum(1 for r in items if dec.get(r["key"]))
        corps.append(f'<div class="bachdr"><span class="caret">&#9662;</span> {html.escape(bac)}'
                     f' <span class="c">({faits}/{len(items)} tranch&eacute;s)</span></div>'
                     f'<div class="bacgrp">')
        for r in items:
            e = dec.get(r["key"]) or {}
            d = e.get("decision")
            courant = e.get("bac") or r["bac"]
            bouge = courant != r["bac"]
            opts = "".join(
                f'<option value="{b}"{" selected" if b == courant else ""}>{b}'
                f'{" (actuel)" if b == r["bac"] else ""}</option>'
                for b in classify_bins.NEW_BINS)
            cls = ((" d-" + d) if d else (" d-deplace" if bouge else ""))                 + ("" if r["jouable"] else " injouable")
            mots = "".join(f'<span class="mot">{html.escape(m)}</span>' for m in r["motifs"])
            corps.append(f"""
<div class="row{cls}" data-k="{html.escape(r['key'], quote=True)}"
     data-jouable="{1 if r['jouable'] else 0}">
  <div>
    <div class="nm">{html.escape(r['nom'])}{'' if r['jouable'] else ' — absent en local'}</div>
    <div class="meta">{r['bpm']:.0f} BPM &middot; {html.escape(r['genre'])} &middot; {mots}</div>
  </div>
  <div class="acts">
    <button class="play" data-d="play" title="Ecouter"{'' if r['jouable'] else ' disabled'}>&#9654;</button>
    <select class="bin{' moved' if bouge else ''}" title="Bac de destination — local ET AzuraCast">{opts}</select>
    <button class="{'on-ok' if d == 'garder' else ''}" data-d="garder">Garder</button>
    <button class="{'on-bad' if d == 'supprimer' else ''}" data-d="supprimer">Supprimer</button>
    <button class="undo" data-d="undo"{'' if d else ' style="display:none"'}>&#8630;</button>
  </div>
</div>""")
        corps.append("</div>")
    pct = 100 * b["tranches"] / b["total"] if b["total"] else 0
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<title>KALBASSFM - Revue du fonds</title>
<style>{CSS}</style></head><body>
<header>
  <h1>KALBASSFM &mdash; Revue du fonds</h1>
  <div class="bar"><i id="barfill" style="width:{pct}%"></i></div>
  <div class="counts">
    <b id="n-tranches">{b['tranches']}</b> / <b id="n-total">{b['total']}</b> tranch&eacute;s
    &nbsp;&middot;&nbsp; &agrave; supprimer : <b id="n-suppr">{b['a_supprimer']}</b>
    &nbsp;&middot;&nbsp; &agrave; d&eacute;placer : <b id="n-depl">{b['a_deplacer']}</b>
    &nbsp;&middot;&nbsp; gard&eacute;s : <b id="n-gardes">{b['gardes']}</b>
  </div>
</header>
<main>
  <div class="panel">
    <h3>Ce que fait chaque bouton</h3>
    <div class="hint">
      Trois populations ici : les morceaux <b>trop sombres</b>, les <b>trop techno</b>,
      et les <b>deux bacs DnB</b> (jungle et liquid) &agrave; trancher en bloc.
      Pour ces derniers, l'axe qui d&eacute;cide n'est pas la couleur mais
      l'<b>agressivit&eacute;</b> : m&eacute;diane 0.05 en liquid contre 0.24 en jungle.<br><br>
      <b>Garder</b> ne fait rien du tout, le morceau reste o&ugrave; il est.<br>
      <b>Supprimer</b> le retire d'AzuraCast (fichier et entr&eacute;e de biblioth&egrave;que,
      <b>irr&eacute;versible</b>) et d&eacute;place la copie locale dans <code>_a_revoir/</code>,
      donc <b>r&eacute;cup&eacute;rable</b>. Rien ne part tant que tu n'as pas cliqu&eacute;
      sur le bouton rouge en bas.
    </div>
  </div>
  {''.join(corps)}
</main>
<footer>
  <button class="danger" id="btn-appliquer" onclick="appliquer()"
          {'disabled' if not b['a_supprimer'] else ''}>
    Supprimer {b['a_supprimer']} morceaux</button>
  <div class="player">
    <audio id="player" controls preload="none"></audio>
    <span id="nowplaying">Clique sur &#9654; pour &eacute;couter</span>
  </div>
</footer>
<script>{JS}</script></body></html>"""


# --------------------------------------------------------------------------- serveur

class Handler(ra.Handler):
    index = {}
    par_bac = OrderedDict()

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        if p.path in ("/", "/index.html"):
            Handler.par_bac = candidats()
            Handler.index = {r["key"]: r["path"] for v in Handler.par_bac.values() for r in v}
            return self._send(200, rendre(Handler.par_bac, charger()))
        if p.path == "/audio":
            return self.serve_audio(q.get("k", [""])[0])
        return self._send(404, b"nope")

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, b"json invalide")

        if p == "/decision":
            key = (payload.get("key") or "").strip()
            d = (payload.get("decision") or "").strip()
            if key not in Handler.index:
                return self._send(404, b"cle inconnue")
            if d not in ("garder", "supprimer", ""):
                return self._send(400, b"decision invalide")
            dec = poser(key, "decision", d)      # le bac choisi est conserve
            return self._json({"decision": d or None, "bilan": bilan(Handler.par_bac, dec)})

        if p == "/bac":
            key = (payload.get("key") or "").strip()
            bac = (payload.get("bac") or "").strip()
            if key not in Handler.index:
                return self._send(404, b"cle inconnue")
            if bac not in classify_bins.NEW_BINS:
                return self._send(400, b"bac inconnu")
            actuel = next((r["bac"] for v in Handler.par_bac.values()
                           for r in v if r["key"] == key), None)
            # Revenir au bac d'origine efface le choix plutot que d'enregistrer
            # une egalite : le morceau ne doit pas compter comme deplace.
            dec = poser(key, "bac", None if bac == actuel else bac)
            return self._json({"deplace": bac != actuel,
                               "bilan": bilan(Handler.par_bac, dec)})

        if p == "/appliquer":
            # Sortie du systeme et irreversible cote serveur : jamais sur un
            # simple clic, comme l'envoi AzuraCast de review_analyse.py.
            if payload.get("confirm") != "oui":
                return self._send(403, b"confirmation requise")
            dec = charger()
            tous = [r for v in Handler.par_bac.values() for r in v]
            a_suppr, a_depl = [], []
            for r in tous:
                e = dec.get(r["key"]) or {}
                if e.get("decision") == "supprimer":
                    a_suppr.append(r)
                elif e.get("bac") and e["bac"] != r["bac"]:
                    # Un morceau supprime n'a pas de bac de destination : la
                    # suppression prime, le choix de bac devient sans objet.
                    a_depl.append(dict(r, cible=e["bac"]))
            faits_s, echecs_s = supprimer(a_suppr)
            faits_d, echecs_d = deplacer(a_depl)
            for nom in faits_s:
                dec.pop(ana.key_of(nom), None)
            for ligne in faits_d:
                dec.pop(ana.key_of(ligne.split(" : ")[0]), None)
            ecrire(dec)
            return self._json({"supprimes": len(faits_s), "deplaces": len(faits_d),
                               "echecs": echecs_s + echecs_d})

        return self._send(404, b"nope")


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--rapport", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    if args.reset:
        if os.path.exists(DECISIONS_PATH):
            os.remove(DECISIONS_PATH)
            print("Decisions effacees.")
        else:
            print("Aucune decision a effacer.")
        return

    par_bac = candidats()
    Handler.par_bac = par_bac
    Handler.index = {r["key"]: r["path"] for v in par_bac.values() for r in v}
    dec = charger()
    b = bilan(par_bac, dec)
    for bac, items in par_bac.items():
        injouables = sum(1 for r in items if not r["jouable"])
        print("  %-13s %3d morceau(x)%s" % (bac, len(items),
              f"  ({injouables} sans copie locale)" if injouables else ""))
    print(f"\n{b['total']} candidat(s) — {b['tranches']} tranche(s), "
          f"{b['a_supprimer']} a supprimer.")
    if args.rapport:
        return

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"\nRevue : {url}")
    print("Rien n'est supprime tant que le bouton rouge n'est pas presse.\n")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nArrete. Decisions conservees dans review_dark_decisions.json.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
