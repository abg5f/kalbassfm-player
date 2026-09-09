#!/usr/bin/env python3
"""Interface unique du pipeline d'ingestion : triage, analyse, arbitrage, envoi.

Rassemble en une page ce qui etait reparti entre deux .bat et un rapport HTML
mort :

    1. TRIAGE    — nettoyage CLAPCRATE + Essentia + classement dans les bacs,
                   sortie affichee en direct (c'est le long : ~1 h).
    2. ANALYSE   — verdicts (trop energique / repetitif / loin de la house).
    3. ARBITRAGE — ecoute des morceaux, on confirme ou on renverse le verdict,
                   et on change le bac quand le classement s'est trompe.
    4. ENVOI     — applique tout : range les ecartes, deplace EN LOCAL les bacs
                   modifies, puis envoie sur AzuraCast.

POURQUOI UN SERVEUR ET PAS UN FICHIER HTML : `analyse_report.html` et
`review_energy.py` s'ouvrent en `file://`, ce qui suffit a lire mais pas a
ecrire ni a lancer quoi que ce soit. Le serveur n'ecoute que sur 127.0.0.1 et
ne sert que les fichiers de la file d'attente — aucun chemin arbitraire ne
passe a travers.

L'ENVOI EST LA SEULE ACTION IRREVERSIBLE de cette page : un morceau parti sur
AzuraCast peut etre a l'antenne dans les minutes qui suivent. Il exige donc une
confirmation explicite cote navigateur, qui remplace le `o/N` de analyse.bat.
Tout le reste (arbitrages, changements de bac) n'est que de l'intention ecrite
dans analyse_overrides.json : rien ne bouge sur le disque avant l'envoi.

Usage :
    python review_analyse.py            # ouvre l'interface
    python review_analyse.py --port 8137
    python review_analyse.py --reset    # efface les arbitrages et sort
"""
import argparse
import html
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)

import azuracast_upload  # noqa: E402
import track_gate  # noqa: E402
import analyse_new_tracks as ana  # noqa: E402
import classify_bins  # noqa: E402  (liste des bacs — source de verite unique)

OVERRIDES_PATH = ana.OVERRIDES_PATH
load_overrides = ana.load_overrides
DEFAULT_PORT = 8137

WSL_TOOLS = "/mnt/c/Users/ph.dufourcq/Documents/0_Claude Code/3_Radiofm/tools"

# Les trois etapes lancables depuis la page. `danger` marque celle qui sort de
# la machine : elle seule exige une confirmation.
JOBS = {
    "triage": {
        "label": "Triage",
        "danger": False,
        "steps": [
            ("Nettoyage CLAPCRATE",
             [sys.executable, os.path.join(TOOLS_DIR, "clean_clapcrate_full.py"), "--apply"]),
            ("Classement Essentia (long)",
             ["wsl", "-e", "bash", "-c",
              f"source ~/essentia-env/bin/activate && python3 '{WSL_TOOLS}/triage_new_tracks.py'"]),
        ],
    },
    "analyse": {
        "label": "Analyse",
        "danger": False,
        "steps": [("Verdicts (simulation)",
                   [sys.executable, os.path.join(TOOLS_DIR, "analyse_new_tracks.py"),
                    "--no-browser"])],
    },
    "envoi": {
        "label": "Envoi AzuraCast",
        "danger": True,
        "steps": [("Application + envoi",
                   [sys.executable, os.path.join(TOOLS_DIR, "analyse_new_tracks.py"),
                    "--apply", "--no-browser"])],
    },
}


# --------------------------------------------------------------------------- travaux

class Job:
    """Un seul travail a la fois, sa sortie conservee ligne a ligne.

    Un seul, parce que les trois etapes ecrivent toutes dans metadata.json :
    deux en parallele se marcheraient dessus.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.name = None
        self.status = "idle"       # idle | running | done | failed
        self.lines = []
        self.rc = None
        self.started = None

    def snapshot(self, since=0):
        with self.lock:
            return {
                "name": self.name,
                "status": self.status,
                "rc": self.rc,
                "total": len(self.lines),
                "lines": self.lines[since:],
                "elapsed": round(time.time() - self.started) if self.started else 0,
            }

    def start(self, name):
        with self.lock:
            if self.status == "running":
                return False
            self.name, self.status, self.lines = name, "running", []
            self.rc, self.started = None, time.time()
        threading.Thread(target=self._run, args=(name,), daemon=True).start()
        return True

    def _emit(self, line):
        with self.lock:
            self.lines.append(line)
            # Garde-fou memoire : un triage d'une heure produit beaucoup de
            # lignes, et la page n'en affiche qu'une fenetre de toute facon.
            if len(self.lines) > 4000:
                del self.lines[:1000]

    def _run(self, name):
        rc = 0
        try:
            for label, cmd in JOBS[name]["steps"]:
                self._emit(f"=== {label} ===")
                # PYTHONUNBUFFERED : sans lui, l'enfant detecte un tube et
                # passe en tampon de bloc — sa sortie n'arrive qu'a la fin.
                # C'est ce qui a laisse l'envoi du 2026-09-08 muet pendant
                # 35 minutes alors qu'il televersait normalement.
                env = dict(os.environ, PYTHONUNBUFFERED="1")
                proc = subprocess.Popen(
                    cmd, cwd=TOOLS_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
                )
                for line in proc.stdout:
                    self._emit(line.rstrip("\n"))
                rc = proc.wait()
                if rc != 0:
                    self._emit(f"[ECHEC] {label} — code {rc}")
                    break
                self._emit(f"[OK] {label}")
        except Exception as exc:                       # noqa: BLE001
            self._emit(f"[ERREUR] {exc}")
            rc = -1
        with self.lock:
            self.rc = rc
            self.status = "done" if rc == 0 else "failed"


JOB = Job()


# --------------------------------------------------------------------------- etat

def save_overrides(data):
    clean = {k: v for k, v in data.items() if v.get("decision") or v.get("bin")}
    with open(OVERRIDES_PATH, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, ensure_ascii=False, indent=1, sort_keys=True)


def set_override(key, field, value):
    """Pose (ou retire) un champ d'arbitrage sans ecraser l'autre.

    Choisir un bac ne doit pas annuler un « garder » deja rendu, et
    inversement : les deux decisions sont independantes.
    """
    ov = load_overrides()
    entry = dict(ov.get(key) or {"decision": None, "bin": None})
    entry[field] = value or None
    ov[key] = entry
    save_overrides(ov)
    return ov


def build_rows():
    """Verdicts courants + arbitrages. Reutilise `analyse_new_tracks.judge()` :
    meme file, meme reference, meme formule — sinon la page mentirait sur ce
    que l'envoi va faire."""
    queue = azuracast_upload.load_pending_review()
    if not queue:
        return [], "Aucun morceau en attente de verdict. Lance le triage, puis l'analyse."
    ref = track_gate.load_reference()
    metadata = ana.load_metadata()
    ov = load_overrides()
    rows, _orphans = ana.judge(queue, metadata, ref, strict=False, overrides=ov)

    out = []
    for r in rows:
        key = ana.key_of(r["path"])
        decision = (ov.get(key) or {}).get("decision")
        # `auto` vient du verdict BRUT du gate, jamais de `held` : judge() y a
        # deja applique l'arbitrage, s'en servir ferait changer de section le
        # morceau qu'on vient de trancher.
        auto = {"reject": "ecarte", "review": "ecouter"}.get(r["verdict"], "ok")
        out.append({
            "key": key,
            "name": os.path.basename((r["path"] or "").replace("\\", "/")),
            "slot": r.get("slot") or "-",
            "slot_auto": r.get("slot_auto") or r.get("slot") or "-",
            "bin_override": r.get("bin_override"),
            "verdict": r["verdict"],
            "score": round(float(r["score"]), 3),
            "reasons": r["reasons"],
            "auto": auto,
            "decision": decision,
            "final": decision if decision else auto,
            "path": r["path"],
        })
    out.sort(key=lambda r: (r["slot"], -r["score"]))
    return out, None


def stats(rows):
    a_trancher = [r for r in rows if r["auto"] in ("ecarte", "ecouter")]
    return {
        "total": len(rows),
        "auto_ecarte": sum(1 for r in rows if r["auto"] == "ecarte"),
        "auto_ecouter": sum(1 for r in rows if r["auto"] == "ecouter"),
        "auto_ok": sum(1 for r in rows if r["auto"] == "ok"),
        "a_trancher": len(a_trancher),
        "tranches": sum(1 for r in a_trancher if r["decision"]),
        "final_ok": sum(1 for r in rows if r["final"] in ("ok", "ecouter")),
        "final_ecarte": sum(1 for r in rows if r["final"] == "ecarte"),
        "rebinned": sum(1 for r in rows if r.get("bin_override")),
    }


# --------------------------------------------------------------------------- page

CSS = """
:root{--bg:#14161a;--card:#1c1f26;--line:#2a2f3a;--txt:#e6e8ec;--dim:#9aa3b2;
--ok:#4caf50;--warn:#e0b23c;--bad:#e0574c;--acc:#5b9dd9}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:9;background:var(--bg);
border-bottom:1px solid var(--line);padding:12px 20px}
h1{margin:0 0 7px;font-size:18px}
.bar{height:7px;border-radius:4px;background:var(--line);overflow:hidden;margin:7px 0 5px}
.bar>i{display:block;height:100%;background:var(--ok);transition:width .3s}
.counts{color:var(--dim);font-size:13px}
.counts b{color:var(--txt)}
main{padding:16px 20px 86px;max-width:1240px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:13px 15px;margin-bottom:18px}
.panel h3{margin:0 0 10px;font-size:14px}
.steps{display:flex;gap:9px;flex-wrap:wrap;align-items:center}
.log{margin-top:11px;background:#0e1014;border:1px solid var(--line);border-radius:6px;
padding:9px 11px;font:12px/1.45 ui-monospace,Consolas,monospace;color:#c8cdd6;
max-height:260px;overflow:auto;white-space:pre-wrap;word-break:break-word}
.log .err{color:var(--bad)}
.log .good{color:var(--ok)}
h2{font-size:15px;margin:24px 0 8px;padding-bottom:5px;border-bottom:1px solid var(--line)}
h2 .n{color:var(--dim);font-weight:400}
.bacgrp{margin-bottom:4px}
.bachdr{display:flex;align-items:center;gap:8px;color:var(--acc);font-size:13px;
font-weight:600;margin:14px 0 7px;cursor:pointer;user-select:none}
.bachdr .c{color:var(--dim);font-weight:400}
.bachdr .caret{transition:transform .15s;display:inline-block}
.bachdr.closed .caret{transform:rotate(-90deg)}
.row{display:grid;grid-template-columns:1fr 380px;gap:12px;align-items:center;
background:var(--card);border:1px solid var(--line);border-left:3px solid var(--line);
border-radius:7px;padding:9px 12px;margin-bottom:7px}
.row.f-ok{border-left-color:var(--ok)}
.row.f-ecouter{border-left-color:var(--warn)}
.row.f-ecarte{border-left-color:var(--bad)}
.row.moved{opacity:.62}
.nm{font-weight:600;word-break:break-word}
.meta{color:var(--dim);font-size:12px;margin-top:2px}
.badge{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;
background:var(--line);margin-right:4px;white-space:nowrap}
footer .player{display:flex;align-items:center;gap:10px;flex:1;min-width:0}
footer audio{height:34px;width:330px;flex:none}
#nowplaying{color:var(--txt);font-size:12.5px;overflow:hidden;text-overflow:ellipsis;
white-space:nowrap}
button.play{padding:6px 11px;font-size:13px}
.row.playing{border-color:var(--acc);background:#20262f}
.row.playing .nm{color:var(--acc)}
.acts{display:flex;gap:6px;justify-content:flex-end;align-items:center}
button{background:var(--line);color:var(--txt);border:1px solid transparent;
border-radius:6px;padding:7px 12px;cursor:pointer;font-size:13px;font-family:inherit}
button:hover:not(:disabled){border-color:var(--acc)}
button:disabled{opacity:.45;cursor:default}
button.on-ok{background:var(--ok);color:#0d1a0e;font-weight:600}
button.on-bad{background:var(--bad);color:#2a0c09;font-weight:600}
button.undo{padding:7px 9px;color:var(--dim)}
button.danger{background:var(--bad);color:#2a0c09;font-weight:600}
select.bin{background:var(--line);color:var(--txt);border:1px solid transparent;
border-radius:6px;padding:6px 7px;font-size:12px;font-family:inherit;cursor:pointer}
select.bin:hover{border-color:var(--acc)}
select.bin.moved{border-color:var(--acc);color:var(--acc);font-weight:600}
.pill{font-size:12px;color:var(--dim)}
.empty{color:var(--dim);padding:8px 2px}
.hint{color:var(--dim);font-size:12.5px;margin:-2px 0 6px}
.hint b{color:var(--txt)}
.hint code{background:var(--line);padding:1px 5px;border-radius:4px}
footer{position:fixed;bottom:0;left:0;right:0;background:var(--card);
border-top:1px solid var(--line);padding:8px 20px;font-size:13px;color:var(--dim);
display:flex;gap:14px;align-items:center;z-index:9}
@media (max-width:1050px){
  .row{grid-template-columns:1fr;gap:8px}
  .acts{justify-content:flex-start;flex-wrap:wrap}
}
"""

JS = r"""
// --- arbitrages -----------------------------------------------------------
// Delegation plutot qu'un onclick par bouton : le nom de fichier sert de cle,
// et une apostrophe dedans ("Trus'me", "If It Don't Turn You On") casserait
// toute chaine JS interpolee dans un attribut.
document.addEventListener('click', e => {
  const btn = e.target.closest('.acts button');
  if(btn){
    const row = btn.closest('.row');
    if(!row) return;
    if(btn.dataset.d === 'play') play(row);
    else decide(row.dataset.k, btn.dataset.d === 'undo' ? '' : btn.dataset.d);
    return;
  }
  const hdr = e.target.closest('.bachdr');
  if(hdr) toggleBac(hdr);
});

// --- lecteur unique -------------------------------------------------------
// Un seul element <audio> pour toute la page : 254 lecteurs, c'etait 254
// pipelines media instancies par le navigateur, et c'est ce qui rendait
// l'interface lente. Le serveur, lui, repond en 2 ms.
const player = document.getElementById('player');
function play(row){
  const k = row.dataset.k;
  document.querySelectorAll('.row.playing').forEach(r => r.classList.remove('playing'));
  row.classList.add('playing');
  document.getElementById('nowplaying').textContent = row.querySelector('.nm').textContent;
  player.src = '/audio?k=' + encodeURIComponent(k);
  player.play().catch(() => {});
  prefetchSuivant(row);
}
// On tire les 512 premiers Ko du morceau suivant dans le cache HTTP : on
// descend la liste, c'est presque toujours le prochain ecoute. Une seule
// petite requete, contre les 254 du prechauffage precedent.
let dejaPrefetch = new Set();
function prefetchSuivant(row){
  const lignes = [...document.querySelectorAll('.row')];
  const nx = lignes[lignes.indexOf(row) + 1];
  if(!nx) return;
  const k = nx.dataset.k;
  if(dejaPrefetch.has(k)) return;
  dejaPrefetch.add(k);
  fetch('/audio?k=' + encodeURIComponent(k), {headers: {Range: 'bytes=0-524287'}})
    .then(r => r.arrayBuffer()).catch(() => {});
}

// --- deplier un bac -------------------------------------------------------
// Les 236 deja valides ne sont pas dans la page au chargement : leurs lignes
// n'arrivent qu'a l'ouverture du bac, puis restent en cache DOM.
async function toggleBac(hdr){
  const grp = hdr.nextElementSibling;
  const ouvrir = hdr.classList.contains('closed');
  hdr.classList.toggle('closed', !ouvrir);
  grp.hidden = !ouvrir;
  if(ouvrir && grp.dataset.lazy){
    const sec = grp.closest('[data-section]').dataset.section;
    grp.innerHTML = '<div class="empty">chargement…</div>';
    const r = await fetch('/rows?section=' + encodeURIComponent(sec)
                          + '&bac=' + encodeURIComponent(grp.dataset.bac));
    grp.innerHTML = r.ok ? await r.text() : '<div class="empty">echec du chargement</div>';
    if(r.ok) delete grp.dataset.lazy;
  }
}
document.addEventListener('change', async e => {
  const sel = e.target.closest('select.bin');
  if(!sel) return;
  const row = sel.closest('.row');
  const r = await post('/bin', {key: row.dataset.k, bin: sel.value});
  if(!r) return;
  sel.classList.toggle('moved', r.bin_override);
  moveRowToBac(row, r.bin);
  refreshCounts(r.stats);
});
async function post(url, body){
  const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'},
                             body: JSON.stringify(body)});
  if(!r.ok){ alert('Echec (' + r.status + ') : ' + await r.text()); return null; }
  return r.json();
}
async function decide(key, d){
  const st = await post('/decision', {key:key, decision:d});
  if(!st) return;
  paint(key, st.final, st.decision);
  refreshCounts(st.stats);
}
function paint(key, final, decision){
  const row = document.querySelector('[data-k="'+CSS.escape(key)+'"]');
  if(!row) return;
  row.className = 'row f-' + final + (final !== row.dataset.auto ? ' moved' : '');
  row.querySelectorAll('.acts button').forEach(b => {
    b.classList.remove('on-ok','on-bad');
    if(b.dataset.d === decision) b.classList.add(decision==='ok'?'on-ok':'on-bad');
    if(b.dataset.d === 'undo') b.style.display = decision ? '' : 'none';
  });
}
// Le morceau doit rejoindre visuellement le bac choisi, sinon on ne sait plus
// ce que contient chaque bac au moment d'envoyer.
function moveRowToBac(row, bac){
  const section = row.closest('[data-section]');
  if(!section) return;
  const from = row.parentElement;
  let grp = section.querySelector('.bacgrp[data-bac="'+CSS.escape(bac)+'"]');
  if(!grp){
    const hdr = document.createElement('div');
    hdr.className = 'bachdr';
    hdr.innerHTML = '<span class="caret">&#9662;</span> ' + bac + ' <span class="c">(0)</span>';
    grp = document.createElement('div');
    grp.className = 'bacgrp'; grp.dataset.bac = bac;
    section.append(hdr, grp);
  }
  // Un bac encore replie garde son contenu paresseux : on n'y insere pas la
  // ligne, on incremente seulement son compteur — sinon il s'ouvrirait a
  // moitie rempli, avec une ligne dedans et le reste manquant.
  if(grp.dataset.lazy){
    row.remove();
    const c = grp.previousElementSibling && grp.previousElementSibling.querySelector('.c');
    if(c) c.textContent = '(' + ((parseInt(c.textContent.replace(/\D/g,''),10)||0) + 1) + ')';
  } else {
    grp.appendChild(row);
  }
  [from, grp].forEach(g => {
    if(!g || g.dataset.lazy) return;
    const c = g.previousElementSibling && g.previousElementSibling.querySelector('.c');
    if(c) c.textContent = '(' + g.children.length + ')';
  });
}
function refreshCounts(s){
  const set = (id,v) => { const e=document.getElementById(id); if(e) e.textContent=v; };
  set('done', s.tranches); set('todo', s.a_trancher);
  set('fok', s.final_ok); set('fko', s.final_ecarte); set('reb', s.rebinned);
  const pct = s.a_trancher ? Math.round(100*s.tranches/s.a_trancher) : 100;
  const bf = document.getElementById('barfill');
  if(bf) bf.style.width = pct + '%';
  const b = document.getElementById('btn-envoi');
  if(b) b.textContent = 'Envoyer ' + s.final_ok + ' morceaux vers AzuraCast';
}
// --- pipeline -------------------------------------------------------------
const JOBLABEL = {triage:'Triage', analyse:'Analyse', envoi:'Envoi AzuraCast'};
let seen = 0;
async function run(job){
  if(job === 'envoi'){
    const s = document.getElementById('fok').textContent;
    const k = document.getElementById('fko').textContent;
    const r = document.getElementById('reb').textContent;
    if(!confirm("Envoyer " + s + " morceaux sur AzuraCast ?\n\n"
      + k + " seront ranges dans _a_revoir/.\n"
      + r + " changement(s) de bac seront appliques EN LOCAL aussi.\n\n"
      + "Un morceau envoye peut passer a l'antenne dans les minutes qui suivent.\n"
      + "C'est la seule action de cette page qui ne se defait pas.")) return;
  }
  const r = await post('/run', {job: job, confirm: job === 'envoi' ? 'oui' : ''});
  if(!r) return;
  seen = 0;
  document.getElementById('log').textContent = '';
  setBusy(true);
  poll();
}
function setBusy(on){
  document.querySelectorAll('.steps button, #btn-envoi').forEach(b => b.disabled = on);
  document.getElementById('logwrap').hidden = false;
}
async function poll(){
  const d = await (await fetch('/log?since=' + seen)).json();
  seen = d.total;
  if(d.lines.length){
    const log = document.getElementById('log');
    for(const l of d.lines){
      const div = document.createElement('div');
      if(/^\[ECHEC\]|^\[ERREUR\]|ECHEC/.test(l)) div.className = 'err';
      else if(/^\[OK\]|^===/.test(l)) div.className = 'good';
      div.textContent = l;
      log.appendChild(div);
    }
    log.scrollTop = log.scrollHeight;
  }
  document.getElementById('jobstate').textContent =
      d.status === 'running' ? (JOBLABEL[d.name] || d.name) + ' en cours — ' + d.elapsed + ' s'
    : d.status === 'done'    ? 'Termine.'
    : d.status === 'failed'  ? 'Echec (code ' + d.rc + ').' : '';
  if(d.status === 'running'){ setTimeout(poll, 1000); return; }
  setBusy(false);
  // L'etat des morceaux a change : on recharge pour repartir du vrai.
  if(d.status === 'done') setTimeout(() => location.reload(), 1500);
}
// Reprend l'affichage si un travail tourne deja (page rouverte en cours de route).
fetch('/log?since=0').then(r=>r.json()).then(d=>{
  if(d.status === 'running'){ setBusy(true); poll(); }
});
"""




def badges(r):
    return "".join(f'<span class="badge">{html.escape(x)}</span>'
                   for x in r["reasons"]) or '<span class="badge">score global</span>'

def row_html(r):
    """Une ligne de morceau. Au niveau module parce que /rows la sert
    aussi a l'ouverture d'un bac : la page initiale et le chargement
    paresseux doivent produire exactement le meme balisage."""
    moved = " moved" if r["final"] != r["auto"] else ""
    k = html.escape(r["key"], quote=True)
    options = "".join(
        f'<option value="{b}"{" selected" if b == r["slot"] else ""}>{b}'
        f'{" (auto)" if b == r["slot_auto"] else ""}</option>'
        for b in classify_bins.NEW_BINS)
    undo_style = "" if r["decision"] else ' style="display:none"'
    return f"""
<div class="row f-{r['final']}{moved}" data-k="{k}" data-auto="{r['auto']}">
  <div>
<div class="nm">{html.escape(r['name'])}</div>
<div class="meta">score {r['score']} &middot; {badges(r)}</div>
  </div>
  <div class="acts">
<button class="play" data-d="play" title="Ecouter">&#9654;</button>
<select class="bin{' moved' if r.get('bin_override') else ''}"
        title="Bac de destination — local ET AzuraCast">{options}</select>
<button class="{'on-ok' if r['decision'] == 'ok' else ''}" data-d="ok">Garder</button>
<button class="{'on-bad' if r['decision'] == 'ecarte' else ''}" data-d="ecarte">Ecarter</button>
<button class="undo" data-d="undo"{undo_style}
        title="Revenir au verdict automatique">&#8630;</button>
  </div>
</div>"""


def render(rows, stat, notice=None):

    DEFAUT = {
        "ecarte": ("Non tranch&eacute; ici = <b>reste &eacute;cart&eacute;</b>, "
                   "rang&eacute; dans <code>_a_revoir/</code> et jamais envoy&eacute;."),
        "ecouter": ("Non tranch&eacute; ici = <b>part en ligne</b>. Le verdict "
                    "&laquo;&nbsp;&agrave; &eacute;couter&nbsp;&raquo; signale, il ne bloque pas."),
        "ok": "Non tranch&eacute; ici = <b>part en ligne</b>.",
    }

    def section(title, which, hint):
        items = [r for r in rows if r["auto"] == which]
        head = (f'<h2>{title} <span class="n">({len(items)})</span></h2>'
                f'<div class="hint">{DEFAUT[which]}</div>')
        if not items:
            return head + f'<div class="empty">{hint}</div>'
        by_bac = OrderedDict()
        for r in items:
            by_bac.setdefault(r["slot"], []).append(r)
        # Les sections signalees sont petites (5 + 13) : on les rend tout de
        # suite, c'est la ou le travail se fait. Les 236 deja valides restent
        # replies et ne sont demandes qu'a l'ouverture — c'est ce qui faisait
        # 254 lignes et 4000 noeuds dans le DOM.
        lazy = which == "ok"
        body = []
        for bac in sorted(by_bac):
            grp = by_bac[bac]
            closed = " closed" if lazy else ""
            content = "" if lazy else "".join(row_html(r) for r in grp)
            body.append(
                f'<div class="bachdr{closed}"><span class="caret">&#9662;</span> {html.escape(bac)}'
                f' <span class="c">({len(grp)})</span></div>'
                f'<div class="bacgrp" data-bac="{html.escape(bac, quote=True)}"'
                f'{" data-lazy=1 hidden" if lazy else ""}>{content}</div>')
        return head + f'<div data-section="{which}">' + "".join(body) + "</div>"

    pct = round(100 * stat["tranches"] / stat["a_trancher"]) if stat["a_trancher"] else 100
    banner = f'<div class="panel">{html.escape(notice)}</div>' if notice else ""
    body = banner if notice else (
        section("&Eacute;cart&eacute;s par le score", "ecarte", "Aucun morceau rejet&eacute;.")
        + section("&Agrave; &eacute;couter", "ecouter", "Aucun morceau en attente d'&eacute;coute.")
        + section("Pass&eacute;s sans r&eacute;serve", "ok", "Aucun."))
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<title>KALBASSFM - Pipeline d'ingestion</title>
<style>{CSS}</style></head><body>
<header>
  <h1>KALBASSFM &mdash; Pipeline d'ingestion</h1>
  <div class="bar"><i id="barfill" style="width:{pct}%"></i></div>
  <div class="counts">
    <b id="done">{stat['tranches']}</b> / <b id="todo">{stat['a_trancher']}</b> signal&eacute;s tranch&eacute;s
    &nbsp;&middot;&nbsp; {stat['total']} jug&eacute;s
    &nbsp;&middot;&nbsp; ira en ligne : <b id="fok">{stat['final_ok']}</b>
    &nbsp;&middot;&nbsp; &eacute;cart&eacute; : <b id="fko">{stat['final_ecarte']}</b>
    &nbsp;&middot;&nbsp; bac chang&eacute; : <b id="reb">{stat['rebinned']}</b>
  </div>
</header>
<main>
  <div class="panel">
    <h3>Pipeline</h3>
    <div class="steps">
      <button onclick="run('triage')">1. Triage (~1 h)</button>
      <button onclick="run('analyse')">2. Analyse</button>
      <span class="pill" id="jobstate"></span>
    </div>
    <div id="logwrap" hidden><div class="log" id="log"></div></div>
  </div>
{body}
</main>
<footer>
  <div class="player">
    <audio id="player" controls preload="none"></audio>
    <span id="nowplaying">Clique sur &#9654; pour &eacute;couter</span>
  </div>
  <button class="danger" id="btn-envoi" onclick="run('envoi')">
    Envoyer {stat['final_ok']} morceaux vers AzuraCast</button>
  <span>Range les &eacute;cart&eacute;s, applique les changements de bac en local,
  puis envoie. Rien n'a boug&eacute; jusqu'ici.</span>
</footer>
<script>{JS}</script></body></html>"""


# --------------------------------------------------------------------------- serveur

class Handler(BaseHTTPRequestHandler):
    index = {}
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body=b"", ctype="text/html; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode(), "application/json")

    # ---------------------------------------------------------------- GET
    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        if p.path in ("/", "/index.html"):
            rows, msg = build_rows()
            Handler.index = {r["key"]: r["path"] for r in rows}
            # File vide : la page doit quand meme permettre de LANCER le triage,
            # sinon on renvoie l'utilisateur au .bat qu'on vient de remplacer.
            return self._send(200, render(rows, stats(rows), notice=msg))
        if p.path == "/state":
            rows, _ = build_rows()
            return self._json(stats(rows))
        if p.path == "/log":
            try:
                since = int(q.get("since", ["0"])[0])
            except ValueError:
                since = 0
            return self._json(JOB.snapshot(max(0, since)))
        if p.path == "/rows":
            # Lignes d'un bac, servies a l'ouverture du groupe. La page initiale
            # n'embarque que les sections signalees ; les 236 deja valides
            # arrivent ici, sinon le DOM repasse a 4000 noeuds.
            section = q.get("section", [""])[0]
            bac = q.get("bac", [""])[0]
            rows, _ = build_rows()
            Handler.index = {r["key"]: r["path"] for r in rows}
            wanted = [r for r in rows if r["auto"] == section and r["slot"] == bac]
            if not wanted:
                return self._send(404, b"bac vide ou inconnu")
            return self._send(200, "".join(row_html(r) for r in wanted))
        if p.path == "/audio":
            return self.serve_audio(q.get("k", [""])[0])
        return self._send(404, b"nope")

    def serve_audio(self, key):
        """Sert un mp3 de la file, avec Range — sans Range, pas de deplacement
        dans la barre de lecture, et juger impose d'ecouter en entier."""
        path = self.index.get(key)   # via l instance : un sous-classement (simulate_bins) garde son propre index
        if not path:
            return self._send(404, b"inconnu")
        real = ana.LOCAL(path)
        if not os.path.exists(real):
            return self._send(404, b"fichier absent du disque")
        size = os.path.getsize(real)
        ctype = mimetypes.guess_type(real)[0] or "audio/mpeg"
        start, end, partial = 0, size - 1, False
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if m:
            if m.group(1):
                start = int(m.group(1))
            if m.group(2):
                end = min(int(m.group(2)), size - 1)
            if start > end or start >= size:
                return self._send(416, b"", extra={"Content-Range": f"bytes */{size}"})
            partial = True
        length = end - start + 1
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        # Les mp3 ne bougent pas pendant une session d'arbitrage : les laisser
        # en cache evite de retelecharger 20 Mo a chaque reecoute. Le reste de
        # l'API reste en no-store (etat qui change a chaque clic).
        self.send_header("Cache-Control", "private, max-age=3600")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(real, "rb") as fh:
            fh.seek(start)
            left = length
            while left > 0:
                chunk = fh.read(min(65536, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return          # changement de morceau : normal
                left -= len(chunk)

    # ---------------------------------------------------------------- POST
    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, b"json invalide")
        if p == "/decision":
            return self.do_decision(payload)
        if p == "/bin":
            return self.do_bin(payload)
        if p == "/run":
            return self.do_run(payload)
        return self._send(404, b"nope")

    def do_decision(self, payload):
        key = (payload.get("key") or "").strip()
        decision = (payload.get("decision") or "").strip()
        if key not in Handler.index:
            return self._send(404, b"cle inconnue")
        if decision not in ("ok", "ecarte", ""):
            return self._send(400, b"decision invalide")
        set_override(key, "decision", decision)     # le bac choisi est conserve
        rows, _ = build_rows()
        row = next((r for r in rows if r["key"] == key), None)
        return self._json({"final": row["final"] if row else "ok",
                           "decision": row["decision"] if row else None,
                           "stats": stats(rows)})

    def do_bin(self, payload):
        """Change le bac. Rien ne bouge sur le disque ici : le deplacement, local
        comme distant, se fait a l'envoi — cette page n'ecrit que de l'intention."""
        key = (payload.get("key") or "").strip()
        slot = (payload.get("bin") or "").strip()
        if key not in Handler.index:
            return self._send(404, b"cle inconnue")
        if slot not in classify_bins.NEW_BINS:
            return self._send(400, b"bac inconnu")
        rows, _ = build_rows()
        row = next((r for r in rows if r["key"] == key), None)
        # Revenir au bac d'origine efface l'arbitrage plutot que d'enregistrer
        # une egalite : le morceau ne doit pas apparaitre comme deplace.
        set_override(key, "bin", None if row and slot == row["slot_auto"] else slot)
        rows, _ = build_rows()
        row = next((r for r in rows if r["key"] == key), None)
        return self._json({"bin": row["slot"] if row else slot,
                           "bin_override": bool(row and row["bin_override"]),
                           "stats": stats(rows)})

    def do_run(self, payload):
        job = (payload.get("job") or "").strip()
        if job not in JOBS:
            return self._send(400, b"travail inconnu")
        # L'envoi sort de la machine : il ne part jamais sur un clic seul.
        if JOBS[job]["danger"] and payload.get("confirm") != "oui":
            return self._send(403, b"confirmation requise")
        if not JOB.start(job):
            return self._send(409, b"un travail est deja en cours")
        return self._json({"started": job})


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-open", action="store_true",
                    help="ne pas ouvrir le navigateur (tests, second onglet)")
    ap.add_argument("--reset", action="store_true",
                    help="efface tous les arbitrages rendus, puis sort")
    args = ap.parse_args()

    if args.reset:
        if os.path.exists(OVERRIDES_PATH):
            os.remove(OVERRIDES_PATH)
            print("Arbitrages effaces — les verdicts automatiques reprennent la main.")
        else:
            print("Aucun arbitrage a effacer.")
        return

    rows, msg = build_rows()
    Handler.index = {r["key"]: r["path"] for r in rows}
    if msg:
        print(msg)
    else:
        st = stats(rows)
        print(f"{st['total']} morceau(x) juge(s) — {st['auto_ecarte']} ecarte(s), "
              f"{st['auto_ecouter']} a ecouter, {st['auto_ok']} sans reserve.")
        if st["tranches"] or st["rebinned"]:
            print(f"{st['tranches']} arbitrage(s), {st['rebinned']} bac(s) "
                  f"change(s) deja enregistre(s).")

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"\nInterface : {url}")
    print("Seul le bouton d'envoi met quelque chose en ligne. Ferme cette fenetre pour arreter.\n")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nArrete. Arbitrages conserves dans analyse_overrides.json.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
