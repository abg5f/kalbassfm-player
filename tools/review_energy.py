#!/usr/bin/env python3
"""Revue des morceaux TROP energiques / repetitifs / eloignes de la house.

Objectif d'antenne : KALBASSFM est une radio house. Les titres qui tapent trop
fort, qui tournent en boucle sur deux barres ou qui derivent vers la techno
dure / la jungle agressive sont ceux qui font partir un auditeur en cours
d'ecoute. Ce script les remonte pour que tu les REECOUTES EN LOCAL (les mp3
sont sur ton PC) avant de decider, un par un, ce qui sort de la rotation.

Rien n'est decide automatiquement : le script classe et propose, tu coches.

    python review_energy.py list                     # top 60 en console
    python review_energy.py list --bac 6_techno      # un bac en particulier
    python review_energy.py report                   # rapport HTML a cocher (lecteurs audio locaux)
    python review_energy.py m3u                      # playlist .m3u pour VLC/foobar
    python review_energy.py apply                    # dry-run de la selection cochee
    python review_energy.py apply --apply            # sort les titres de l'antenne
    python review_energy.py apply --apply --delete   # suppression definitive cote AzuraCast

COMMENT LE SCORE EST CONSTRUIT
------------------------------
La formule vit dans track_gate.py (WEIGHTS/BADGES/houseness), qui l'applique
aussi a un morceau isole avant qu'il n'entre en rotation — ce script et le
filtre du triage notent donc exactement de la meme facon.

Meme philosophie que classify_bins.py : aucun seuil absolu, tout est en
PERCENTILES de la bibliotheque reelle (l'echelle d'energie d'Essentia est
compressee — p95 global ~0.29 — et depend du mastering des morceaux).
Quatre axes, tous entre 0 et 1 :

  intensite    rang d'energie (0.5*rms + 0.3*bpm + 0.2*party, formule du
               pipeline, importee de classify_bins pour rester la seule
               source de verite)
  monotonie    rang INVERSE de dynamic_complexity (Essentia : ecart moyen au
               niveau global, en dB). Un morceau tres compresse, sans respiration
               ni breakdown, est un mur de son : c'est le meilleur marqueur
               objectif du "trop repetitif" dont on dispose sans re-analyse.
  ecart_house  1 - "houseness" : score Discogs des genres de la famille
               house/disco/garage, corrige par l'ecart de tempo au coeur
               house (118-132 BPM).
  agressivite  rang de mood.aggressive.

  score = 0.30*intensite + 0.25*monotonie + 0.25*ecart_house + 0.20*agressivite

NON RETENU : danceability. Mesuree sur la bibliotheque, elle est saturee
(p10 = 0.95, mediane 0.99) — elle ne separe rien et alourdirait le score.

FILTRE D'ENTREE : seuls les morceaux au-dessus du percentile --energie-min
(0.60 par defaut, soit les 40% les plus energiques) entrent dans la revue.
Sans ce filtre, un ambient tres compresse remonterait par la monotonie seule,
alors que ce n'est pas ce qu'on cherche a ecarter ici.

LIMITE HERITEE (deja documentee dans classify_bins.py) : le rms mesure le
NIVEAU DE MASTERING autant que l'energie musicale, et le BPM du DnB est
souvent detecte en demi-tempo (86 pour 172). Un titre lent mais mixe fort peut
donc entrer dans la liste sans meriter le badge 🔥. C'est voulu : le script
PROPOSE une file d'ecoute, le BPM et les badges sont affiches a cote, et c'est
l'oreille qui tranche. Ne jamais appliquer la liste sans l'avoir ecoutee.

CE QUE "SORTIR DE L'ANTENNE" VEUT DIRE
--------------------------------------
Par defaut, `apply` retire le morceau de TOUTES ses playlists (playlists: [])
sans toucher au fichier : il ne passe plus, il reste dans la bibliotheque
AzuraCast, et un simple deplacement (UI, ou /search puis "Deplacer" sur le bot
Telegram) le remet en rotation. C'est reversible, contrairement a --delete.

Avec --delete, le fichier est supprime d'AzuraCast (fichier + entree
bibliotheque, irreversible), l'entree correspondante est retiree de
metadata.json, et le mp3 LOCAL est deplace dans New_prog/_ecartes/<bac>/ : tu
le gardes sur le PC pour l'ecoute, et les bacs locaux restent iso avec le
serveur (sinon la prochaine synchro PC -> radio le reuploaderait aussitot).
"""
import argparse
import html
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)
from classify_bins import NEW_BINS, compute_energies, top_genre  # noqa: E402
# Formule du score : definie une seule fois, dans track_gate.py, qui l'applique
# aussi a un morceau isole (filtre d'entree du triage / yt2slskd).
from track_gate import BADGES, WEIGHTS, houseness  # noqa: E402

METADATA_PATH = os.path.join(TOOLS_DIR, "metadata.json")
REPORT_PATH = os.path.join(TOOLS_DIR, "energy_review.html")
M3U_PATH = os.path.join(TOOLS_DIR, "energy_review.m3u")
SELECTION_PATH = os.path.join(TOOLS_DIR, "energy_review_selection.txt")
LOCAL_ROOT = os.getenv("KALBASS_NEW_PROG",
                       r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog")
QUARANTINE = "_ecartes"

BASE = os.getenv("AZURACAST_BASE_URL", "https://kalbassfm.duckdns.org") + "/api"
STATION = os.getenv("AZURACAST_STATION_ID", "1")


# ------------------------------- mesures -------------------------------

def ranks(values):
    """Rang normalise 0-1 de chaque valeur (ex aequo : meme rang moyen)."""
    n = len(values)
    if n < 2:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        r = (i + j) / 2 / (n - 1)
        for k in range(i, j + 1):
            out[order[k]] = r
        i = j + 1
    return out


def bin_of(track):
    return os.path.basename(os.path.dirname(track.get("path", "").replace("\\", "/")))


def filename_of(track):
    return os.path.basename(track.get("path", "").replace("\\", "/"))


def artist_title(track):
    """Artiste/titre depuis le nom de fichier : metadata.json ne stocke que le
    chemin, et le pipeline de triage garantit "Artiste - Titre[ BPM].mp3"."""
    stem = os.path.splitext(filename_of(track))[0]
    stem = re.sub(r"\s+\d{2,3}$", "", stem)  # BPM colle en fin de nom
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()
    return "?", stem.strip()


def score_library(tracks):
    """Ajoute a chaque morceau ses quatre axes et son score de risque."""
    energies = compute_energies(tracks)
    intensite = ranks(energies)
    monotonie = [1.0 - r for r in ranks([t.get("dynamic_complexity", 0.0) for t in tracks])]
    agressivite = ranks([(t.get("mood") or {}).get("aggressive", 0.0) for t in tracks])
    ecart = [1.0 - houseness(t) for t in tracks]

    scored = []
    for t, e, i, m, a, x in zip(tracks, energies, intensite, monotonie, agressivite, ecart):
        axes = {"intensite": i, "monotonie": m, "ecart_house": x, "agressivite": a}
        artist, title = artist_title(t)
        scored.append({
            "path": t.get("path", ""),
            "bac": bin_of(t),
            "file": filename_of(t),
            "artist": artist,
            "title": title,
            "bpm": float(t.get("bpm") or 0.0),
            "energy": e,
            "dyn": float(t.get("dynamic_complexity") or 0.0),
            "genre": top_genre(t.get("genres")),
            "axes": axes,
            "score": sum(WEIGHTS[k] * v for k, v in axes.items()),
        })
    scored.sort(key=lambda s: -s["score"])
    return scored


def badges_of(row):
    return [(icon, label) for key, mini, icon, label in BADGES if row["axes"][key] >= mini]


def select(scored, args):
    rows = [r for r in scored if r["axes"]["intensite"] >= args.energie_min]
    if args.bac:
        wanted = set(args.bac)
        rows = [r for r in rows if r["bac"] in wanted]
    return rows[:args.top]


def load_tracks():
    if not os.path.exists(METADATA_PATH):
        sys.exit("metadata.json introuvable — lance d'abord analyze_essentia.py.")
    with open(METADATA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------- commandes -------------------------------

def cmd_list(args):
    rows = select(score_library(load_tracks()), args)
    if not rows:
        print("Aucun morceau ne passe les filtres.")
        return
    print(f"{len(rows)} morceau(x) a revoir — du plus risque au moins risque.\n")
    print(f"{'#':>3}  {'score':>5}  {'bac':<12} {'BPM':>5}  {'nrj':>4} {'mono':>4} {'hors':>4} {'agr':>4}  titre")
    for i, r in enumerate(rows, 1):
        a = r["axes"]
        print(f"{i:>3}  {r['score']:.3f}  {r['bac']:<12} {r['bpm']:>5.0f}  "
              f"{a['intensite']:.2f} {a['monotonie']:.2f} {a['ecart_house']:.2f} {a['agressivite']:.2f}  "
              f"{r['artist']} — {r['title']} "
              f"{''.join(icon for icon, _ in badges_of(r))}")
    print("\nnrj=intensite  mono=monotonie (peu de dynamique)  hors=ecart a la house  agr=agressivite")
    print(f"Rapport a cocher : python {os.path.basename(__file__)} report")


def cmd_select(args):
    """Ecrit la selection sans passer par le rapport : apres une ecoute
    complete, cocher 120 cases une par une n'apporte rien."""
    rows = select(score_library(load_tracks()), args)
    if not rows:
        print("Aucun morceau ne passe les filtres — selection inchangee.")
        return
    lines = [f"{r['bac']}/{r['file']}" for r in rows]
    mode = "a" if args.append else "w"
    if args.append and os.path.exists(SELECTION_PATH):
        with open(SELECTION_PATH, encoding="utf-8") as fh:
            known = {l.strip() for l in fh}
        lines = [l for l in lines if l not in known]
    with open(SELECTION_PATH, mode, encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"{len(lines)} morceau(x) {'ajoutes a' if args.append else 'ecrits dans'} {SELECTION_PATH}")
    print(f"Verifie avec : python {os.path.basename(__file__)} apply")


def cmd_m3u(args):
    rows = select(score_library(load_tracks()), args)
    lines = ["#EXTM3U"]
    for r in rows:
        lines.append(f"#EXTINF:-1,{r['artist']} - {r['title']}")
        lines.append(r["path"])
    with open(M3U_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"{len(rows)} morceau(x) -> {M3U_PATH}")
    print("Ouvre-le dans VLC/foobar pour ecouter la selection dans l'ordre du score.")


def file_uri(path):
    """file:/// utilisable par le lecteur <audio> du rapport, depuis le PC."""
    return "file:///" + urllib.parse.quote(path.replace("\\", "/"), safe="/:")


REPORT_CSS = """
:root{color-scheme:dark;--bg:#111417;--card:#1b2026;--line:#2c333c;--ink:#e8edf2;--dim:#93a1b0;--hot:#ff6b3d}
*{box-sizing:border-box}
body{margin:0;padding:24px;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,Segoe UI,sans-serif}
h1{font-size:20px;margin:0 0 4px}
.lede{color:var(--dim);max-width:75ch;margin:0 0 16px}
.bar{position:sticky;top:0;z-index:2;display:flex;gap:12px;flex-wrap:wrap;align-items:center;
     padding:12px;margin:0 0 16px;background:#161a1f;border:1px solid var(--line);border-radius:10px}
.bar label{color:var(--dim)}
select,button{background:#232a31;color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:6px 10px;font:inherit}
button{cursor:pointer}
.count{margin-left:auto;color:var(--hot);font-weight:600}
.row{display:grid;grid-template-columns:34px 1fr 320px;gap:14px;align-items:center;
     padding:10px 12px;margin-bottom:8px;background:var(--card);border:1px solid var(--line);border-radius:10px}
.row.out{border-color:var(--hot);background:#241a17}
.rank{color:var(--dim);text-align:right}
.t{font-weight:600}
.t .by{color:var(--dim);font-weight:400}
.meta{color:var(--dim);font-size:12.5px;margin-top:2px}
.tag{display:inline-block;margin-right:6px;padding:1px 7px;border:1px solid var(--line);border-radius:99px}
audio{width:100%;height:34px}
.pick{display:flex;gap:6px;align-items:center;margin-top:6px;color:var(--dim);cursor:pointer;font-size:12.5px}
.bars{display:flex;gap:3px;margin-top:6px}
.bars i{height:4px;border-radius:2px;background:#39424c}
.out-panel{position:sticky;bottom:0;margin-top:18px;padding:12px;background:#161a1f;border:1px solid var(--line);border-radius:10px}
textarea{width:100%;height:110px;background:#0d1013;color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:8px;font:12px/1.4 ui-monospace,Consolas,monospace}
code{background:#0d1013;padding:1px 5px;border-radius:4px}
"""

REPORT_JS = """
var KEY='kalbass-energy-review';
var saved=JSON.parse(localStorage.getItem(KEY)||'[]');
function rows(){return Array.prototype.slice.call(document.querySelectorAll('.row'))}
function sync(){
  var picked=[];
  rows().forEach(function(r){
    var c=r.querySelector('input');
    r.classList.toggle('out',c.checked);
    if(c.checked)picked.push(c.value);
  });
  localStorage.setItem(KEY,JSON.stringify(picked));
  document.getElementById('out').value=picked.join('\\n');
  document.getElementById('count').textContent=picked.length+' a sortir';
}
function filter(){
  var bac=document.getElementById('fbac').value, badge=document.getElementById('fbadge').value;
  rows().forEach(function(r){
    var okBac=!bac||r.dataset.bac===bac;
    var okBadge=!badge||r.dataset.badges.indexOf(badge)>=0;
    r.style.display=(okBac&&okBadge)?'':'none';
  });
}
rows().forEach(function(r){
  var c=r.querySelector('input');
  if(saved.indexOf(c.value)>=0)c.checked=true;
  c.addEventListener('change',sync);
});
document.getElementById('fbac').addEventListener('change',filter);
document.getElementById('fbadge').addEventListener('change',filter);
document.getElementById('copy').addEventListener('click',function(){
  navigator.clipboard.writeText(document.getElementById('out').value);
});
document.getElementById('all').addEventListener('click',function(){
  rows().forEach(function(r){if(r.style.display!=='none')r.querySelector('input').checked=true});sync();
});
document.getElementById('clear').addEventListener('click',function(){
  rows().forEach(function(r){r.querySelector('input').checked=false});sync();
});
sync();
"""


def cmd_report(args):
    rows = select(score_library(load_tracks()), args)
    if not rows:
        print("Aucun morceau ne passe les filtres — rien a mettre dans le rapport.")
        return

    cards = []
    for i, r in enumerate(rows, 1):
        bl = badges_of(r)
        tags = "".join('<span class="tag">%s %s</span>' % (icon, html.escape(label)) for icon, label in bl)
        bars = "".join(
            '<i style="flex:%d;background:%s" title="%s %d%%"></i>'
            % (max(1, int(r["axes"][k] * 100)), color, k, round(r["axes"][k] * 100))
            for k, color in (("intensite", "#ff6b3d"), ("monotonie", "#f0c040"),
                             ("ecart_house", "#5aa9e6"), ("agressivite", "#c86bd8")))
        cards.append(
            '<div class="row" data-bac="%s" data-badges="%s">'
            '<div class="rank">%d</div>'
            '<div><div class="t">%s <span class="by">— %s</span></div>'
            '<div class="meta">%s · %.0f BPM · %s · score %.3f</div>'
            '<div class="meta">%s</div>'
            '<div class="bars">%s</div></div>'
            '<div><audio controls preload="none" src="%s"></audio>'
            '<label class="pick"><input type="checkbox" value="%s"> sortir de la radio</label></div>'
            '</div>'
            % (html.escape(r["bac"]), html.escape("".join(icon for icon, _ in bl)), i,
               html.escape(r["artist"]), html.escape(r["title"]),
               html.escape(r["bac"]), r["bpm"], html.escape(r["genre"] or "?"), r["score"],
               tags or '<span class="tag">aucun signal fort</span>', bars,
               html.escape(file_uri(r["path"])), html.escape(r["bac"] + "/" + r["file"])))

    bacs = sorted({r["bac"] for r in rows})
    bac_opts = "".join('<option value="%s">%s</option>' % (html.escape(b), html.escape(b)) for b in bacs)
    badge_opts = "".join('<option value="%s">%s %s</option>' % (icon, icon, html.escape(label))
                         for _, _, icon, label in BADGES)

    doc = (
        '<!doctype html><html lang="fr"><meta charset="utf-8">'
        '<title>KALBASSFM — morceaux a revoir</title><style>%s</style>'
        '<h1>Morceaux a revoir — %d titres</h1>'
        '<p class="lede">Classes du plus risque au moins risque pour l\'ecoute : trop energiques, '
        'trop repetitifs (peu de dynamique), ou trop loin de la house. <b>Ecoute-les ici</b> — les '
        'lecteurs pointent tes fichiers locaux — et coche ceux qui doivent sortir de la rotation. '
        'Puis colle la liste du bas dans <code>tools/energy_review_selection.txt</code> et lance '
        '<code>python review_energy.py apply --apply</code> (les titres quittent l\'antenne sans etre '
        'supprimes ; ajoute <code>--delete</code> pour les effacer vraiment). '
        'Tes coches sont memorisees dans ce navigateur. Apres une ecoute complete, '
        '<code>python review_energy.py select</code> ecrit la liste entiere d\'un coup, '
        'sans avoir a cocher.</p>'
        '<div class="bar">'
        '<label>bac <select id="fbac"><option value="">tous</option>%s</select></label>'
        '<label>signal <select id="fbadge"><option value="">tous</option>%s</select></label>'
        '<button id="all">Tout cocher</button>'
        '<button id="clear">Tout decocher</button>'
        '<span class="count" id="count"></span></div>'
        '%s'
        '<div class="out-panel"><textarea id="out" readonly></textarea>'
        '<button id="copy">Copier la selection</button></div>'
        '<script>%s</script></html>'
        % (REPORT_CSS, len(rows), bac_opts, badge_opts, "".join(cards), REPORT_JS))
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"{len(rows)} morceau(x) -> {REPORT_PATH}")
    print("Ouvre ce fichier depuis ton PC : les lecteurs audio lisent directement tes mp3 locaux.")


# ------------------------------- AzuraCast -------------------------------

def api_key():
    try:
        from azuracast_config import AZURACAST_API_KEY
    except ImportError:
        sys.exit("azuracast_config.py introuvable (cle API AzuraCast). "
                 "AzuraCast -> profil -> My API Keys.")
    return AZURACAST_API_KEY


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("X-API-Key", api_key())
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            return r.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:400]


def remote_media(bin_name):
    """{nom_fichier: media_id} du bac sur AzuraCast (meme appel que prune_deleted_tracks)."""
    q = urllib.parse.quote(bin_name)
    status, data = call("GET", f"/station/{STATION}/files/list?currentDirectory={q}")
    if status != 200:
        raise SystemExit(f"Impossible de lister {bin_name}/ : {status} {data}")
    rows = data["rows"] if isinstance(data, dict) and "rows" in data else data
    return {r["path"].split("/", 1)[-1]: r["media"]["id"] for r in rows if r.get("type") == "media"}


def loose_key(name):
    """Cle de comparaison tolerante : casse, espaces et forme Unicode."""
    return unicodedata.normalize("NFC", name).casefold().strip()


def read_selection():
    if not os.path.exists(SELECTION_PATH):
        sys.exit(f"{SELECTION_PATH} introuvable — coche des morceaux dans le rapport "
                 f"(commande `report`), copie la liste et colle-la dans ce fichier.")
    out = []
    with open(SELECTION_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip().replace("\\", "/")
            if not line or line.startswith("#"):
                continue
            bac, _, name = line.rpartition("/")
            out.append((bac, name))
    return out


def cmd_apply(args):
    wanted = read_selection()
    if not wanted:
        sys.exit("Selection vide.")

    # Le catalogue complet (9 appels) plutot que les seuls bacs cites : un
    # morceau deplace cote serveur (UI AzuraCast, bouton "Deplacer" du bot)
    # n'est plus dans le bac que metadata.json lui connait, et serait declare
    # introuvable a tort — donc laisse a l'antenne alors qu'on vient de
    # l'ecarter a l'ecoute.
    catalog = {b: remote_media(b) for b in NEW_BINS}
    # Index secondaire, insensible a la casse et normalise NFC/NFD : les noms
    # de fichiers accentues ne s'ecrivent pas octet pour octet de la meme
    # facon selon le systeme qui les a poses (constate sur les titres
    # japonais/scandinaves de la bibliotheque).
    loose = {}
    for b, files in catalog.items():
        for name, media_id in files.items():
            loose.setdefault(loose_key(name), (b, name, media_id))

    targets, moved, missing = [], [], []
    for bac, name in wanted:
        if bac and name in catalog.get(bac, {}):
            targets.append((bac, name, catalog[bac][name]))
            continue
        hit = next(((b, n, i) for b, files in catalog.items()
                    for n, i in files.items() if n == name), None) or loose.get(loose_key(name))
        if hit:
            targets.append(hit)
            if bac and hit[0] != bac:
                moved.append((bac, hit[0], name))
        else:
            missing.append(f"{bac}/{name}" if bac else name)

    action = "SUPPRIMER" if args.delete else "sortir de l'antenne"
    print(f"{len(targets)} morceau(x) a {action} :")
    for b, name, media_id in targets:
        print(f"    [{b}] {name}  (media {media_id})")
    for src, dst, name in moved:
        print(f"    [DEPLACE cote serveur] {name} : {src} -> {dst}")
    for m in missing:
        print(f"    [ABSENT d'AzuraCast] {m}")
    if missing:
        print(f"\n{len(missing)} morceau(x) sont dans metadata.json mais plus sur AzuraCast "
              f"(deja supprimes depuis le bot, ou jamais montes).\n"
              f"    python sync_library.py    remet les deux cotes iso et nettoie metadata.json.")

    if not args.apply:
        print("\nDRY-RUN — rien n'a ete modifie. Relance avec --apply.")
        return
    if not targets:
        return

    done = []
    for b, name, media_id in targets:
        if args.delete:
            status, res = call("DELETE", f"/station/{STATION}/file/{media_id}")
        else:
            # playlists: [] — le fichier reste, il ne passe plus (les playlists
            # de la station sont de type "songs", pas "folder" : la remise a
            # zero tient dans le temps).
            status, res = call("PUT", f"/station/{STATION}/file/{media_id}", {"playlists": []})
        if status not in (200, 204):
            print(f"  [ECHEC] {b}/{name} : {status} {res}")
            continue
        print(f"  [OK] {b}/{name}")
        done.append((b, name))

    if args.delete and done:
        prune_metadata(done)
        quarantine_local(done, keep=args.keep_local)

    print(f"\n{len(done)}/{len(targets)} traite(s).")
    if done and not args.delete:
        print("Ces titres ne passent plus mais restent dans la bibliotheque : "
              "un deplacement vers une playlist les remet en rotation.")


def prune_metadata(done):
    if not os.path.exists(METADATA_PATH):
        return
    with open(METADATA_PATH, encoding="utf-8") as fh:
        meta = json.load(fh)
    keys = set(done)
    before = len(meta)
    meta = [e for e in meta
            if (os.path.basename(os.path.dirname(e.get("path", "").replace("\\", "/"))),
                os.path.basename(e.get("path", "").replace("\\", "/"))) not in keys]
    if len(meta) != before:
        with open(METADATA_PATH, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=1)
        print(f"metadata.json : {before - len(meta)} entree(s) retiree(s).")


def quarantine_local(done, keep=False):
    """Deplace les mp3 supprimes vers New_prog/_ecartes/<bac>/ : on les garde
    pour l'ecoute, et les bacs locaux restent iso avec le serveur (sinon la
    prochaine synchro PC -> radio reuploaderait ce qu'on vient d'ecarter)."""
    if keep:
        print("--keep-local : les fichiers locaux ne sont pas deplaces "
              "(la prochaine synchro les reuploadera).")
        return
    moved = 0
    for bac, name in done:
        src = os.path.join(LOCAL_ROOT, bac, name)
        if not os.path.isfile(src):
            continue
        dst_dir = os.path.join(LOCAL_ROOT, QUARANTINE, bac)
        os.makedirs(dst_dir, exist_ok=True)
        try:
            os.replace(src, os.path.join(dst_dir, name))
            moved += 1
        except OSError as e:
            print(f"  [local] impossible de deplacer {bac}/{name} : {e}")
    if moved:
        print(f"{moved} fichier(s) local(aux) deplace(s) vers {os.path.join(LOCAL_ROOT, QUARANTINE)}.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, top_default):
        p.add_argument("--top", type=int, default=top_default, help="nombre de morceaux retenus")
        p.add_argument("--bac", action="append", choices=NEW_BINS, help="limiter a un bac (repetable)")
        p.add_argument("--energie-min", dest="energie_min", type=float, default=0.60,
                       metavar="P", help="percentile d'energie minimal pour entrer dans la revue "
                                         "(0.60 = les 40%% les plus energiques)")

    common(sub.add_parser("list", help="lister en console"), 60)
    common(sub.add_parser("report", help="rapport HTML a cocher, avec lecteurs audio locaux"), 120)
    common(sub.add_parser("m3u", help="playlist .m3u pour ecouter dans VLC/foobar"), 60)
    psel = sub.add_parser("select", help="ecrire directement la selection (sans cocher dans le rapport)")
    common(psel, 120)
    psel.add_argument("--append", action="store_true",
                      help="completer la selection existante au lieu de la remplacer")

    pa = sub.add_parser("apply", help="appliquer la selection cochee")
    pa.add_argument("--apply", action="store_true", help="ecrire reellement (sinon dry-run)")
    pa.add_argument("--delete", action="store_true",
                    help="supprimer definitivement au lieu de sortir de l'antenne")
    pa.add_argument("--keep-local", action="store_true",
                    help="avec --delete : ne pas deplacer les mp3 locaux vers _ecartes/")

    args = ap.parse_args()
    {"list": cmd_list, "report": cmd_report, "m3u": cmd_m3u,
     "select": cmd_select, "apply": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    main()
