#!/usr/bin/env python3
"""
Detecte et remplace les pochettes "logo de site" (heydj.pro, ClapCrate.com,
TorrentDay, mypromosound.com...), sur la station AzuraCast comme sur le disque.

clean_local_tracks.py ne remplace une cover que si le morceau n'en a aucune :
une banniere de site est une cover, donc elle passe. Et rien ne repassait
jamais sur les morceaux deja en ligne. D'ou cet outil, qui couvre les deux.

Detection : empreinte perceptuelle (dHash 64 bits), avec une tolerance de
BLOCK_TOLERANCE bits pour attraper les recadrages d'un meme visuel. Le
regroupement seul ne tranche pas (compilations et artworks de label partagent
legitimement une image), d'ou le rapport visuel : l'oeil valide, le script
applique.

Station :
    python fix_artwork.py scan                 # empreinte + rapport HTML
    # cocher les vignettes fautives, coller la liste dans bad_art_hashes.txt
    python fix_artwork.py fix                  # dry-run
    python fix_artwork.py fix --apply          # ecrit sur la station
    python fix_artwork.py fix --apply --fill-missing   # + morceaux sans pochette

Disque (New_prog, avant upload SFTP) :
    python fix_artwork.py local-scan
    python fix_artwork.py local-fix --apply

Les caches artwork_scan*.json evitent de retelecharger les images a chaque
passe ; `scan --refresh` reconstruit de zero.
"""
import argparse
import base64
import collections
import hashlib
import html
import io
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)

SCAN_PATH = os.path.join(TOOLS_DIR, 'artwork_scan.json')
REPORT_PATH = os.path.join(TOOLS_DIR, 'artwork_review.html')
LOCAL_SCAN_PATH = os.path.join(TOOLS_DIR, 'artwork_scan_local.json')
LOCAL_REPORT_PATH = os.path.join(TOOLS_DIR, 'artwork_review_local.html')
BLOCKLIST_PATH = os.path.join(TOOLS_DIR, 'bad_art_hashes.txt')
LOCAL_ROOT = os.getenv('KALBASS_NEW_PROG',
                       r'C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog')

API_BASE = os.getenv('AZURACAST_BASE_URL', 'https://kalbassfm.duckdns.org')
STATION_ID = os.getenv('AZURACAST_STATION_ID', '1')
UA = 'Mozilla/5.0 (KalbassFM artwork fixer)'

MIN_ARTISTS = 2         # groupes affiches dans le rapport
MATCH_MIN_SCORE = 0.6   # score artiste+titre minimum pour accepter un match
LOOKUP_DELAY_SEC = 3.2  # throttle : API iTunes limitee (~20 req/min)
BLOCK_TOLERANCE = 8     # distance de Hamming max avec une empreinte blocklistee


def api_key():
    try:
        from azuracast_config import AZURACAST_API_KEY
    except ImportError:
        sys.exit("azuracast_config.py introuvable (cle API AzuraCast). "
                 "AzuraCast -> profil -> My API Keys.")
    return AZURACAST_API_KEY


def api_request(path, method='GET', body=None, content_type=None):
    req = urllib.request.Request(
        API_BASE + '/api' + path, data=body, method=method,
        headers={'X-API-Key': api_key(), 'Accept': 'application/json', 'User-Agent': UA})
    if content_type:
        req.add_header('Content-Type', content_type)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return json.loads(raw.decode('utf-8')) if raw else None


def multipart(field, filename, data, mime='image/jpeg'):
    """Encode un upload de fichier unique (l'API art attend du multipart/form-data)."""
    boundary = '----KalbassFM' + uuid.uuid4().hex
    body = b''.join([
        ('--%s\r\n' % boundary).encode(),
        ('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (field, filename)).encode(),
        ('Content-Type: %s\r\n\r\n' % mime).encode(),
        data,
        ('\r\n--%s--\r\n' % boundary).encode(),
    ])
    return body, 'multipart/form-data; boundary=%s' % boundary


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_image(urls, tries=3):
    """Premiere URL qui repond, avec reessai.

    Le CDN Deezer renvoie des 403 passagers quand on l'enchaine trop vite :
    une pochette valable etait perdue une fois sur trente sans ce reessai.
    """
    for attempt in range(tries):
        for url in urls:
            if not url:
                continue
            try:
                return fetch(url, timeout=20), url
            except Exception as e:
                last = e
        time.sleep(1.5 * (attempt + 1))
    print('    image indisponible : %s' % last)
    return None, None


# --------------------------------- empreintes ---------------------------------

def dhash(im, size=8):
    """Empreinte perceptuelle : gradient horizontal sur une vignette 9x8.

    Insensible au reencodage et au redimensionnement, contrairement a un md5 :
    le meme logo reexporte par deux sites donne la meme empreinte.
    """
    im = im.convert('L').resize((size + 1, size), Image.LANCZOS)
    px = list(im.getdata())
    bits = 0
    for row in range(size):
        base = row * (size + 1)
        for col in range(size):
            bits = (bits << 1) | (px[base + col] < px[base + col + 1])
    return '%016x' % bits


# ----------------------------------- scan -----------------------------------

def fetch_media_list():
    rows, page = [], 1
    while True:
        d = api_request('/station/%s/files?per_page=250&page=%d' % (STATION_ID, page))
        rows += d['rows']
        print('  page %d/%d -> %d fichiers' % (page, d['total_pages'], len(rows)))
        if page >= d['total_pages']:
            return rows
        page += 1


def cmd_scan(args):
    print('Station : %s (id %s)' % (API_BASE, STATION_ID))
    print('Liste des medias...')
    rows = fetch_media_list()

    cache = {}
    if os.path.exists(SCAN_PATH) and not args.refresh:
        for rec in json.load(open(SCAN_PATH, encoding='utf-8')):
            if not rec.get('error'):
                cache[rec['id']] = rec
        print('Cache : %d pochettes deja empreintees (--refresh pour tout refaire)' % len(cache))

    lock, done = threading.Lock(), [0]

    def work(row):
        # Le cache est invalide des qu'AzuraCast reecrit l'art : l'URL porte
        # art_updated_at, donc une URL identique = image identique.
        rec = {'id': row['id'], 'path': row['path'], 'artist': row.get('artist') or '',
               'title': row.get('title') or '', 'album': row.get('album') or '',
               'art': row.get('art')}
        # Sans art embarque, AzuraCast sert quand meme une URL, vers son image
        # generique -- reconnaissable a l'absence d'horodatage art_updated_at.
        # La distinguer evite de la prendre pour une pochette a remplacer et de
        # relancer indefiniment une recherche qui a deja echoue. Teste avant le
        # cache : les scans anterieurs ne portaient pas ce marqueur.
        if rec['art'] and not re.search(r'-\d+\.(jpe?g|png)$', rec['art']):
            rec['no_art'] = True
            return rec

        old = cache.get(row['id'])
        if old and old.get('art') == row.get('art') and old.get('dhash'):
            return old
        if rec['art']:
            try:
                data = fetch(rec['art'], timeout=45)
                im = Image.open(io.BytesIO(data))
                rec.update(md5=hashlib.md5(data).hexdigest(), bytes=len(data),
                           w=im.size[0], h=im.size[1], dhash=dhash(im))
            except Exception as e:
                rec['error'] = str(e)
        with lock:
            done[0] += 1
            if done[0] % 100 == 0:
                print('  %d/%d' % (done[0], len(rows)))
        return rec

    print('Telechargement + empreinte des pochettes...')
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        recs = list(ex.map(work, rows))

    json.dump(recs, open(SCAN_PATH, 'w', encoding='utf-8'), ensure_ascii=False)
    errors = [r for r in recs if r.get('error')]
    print('\n%d medias, %d erreur(s) -> %s' % (len(recs), len(errors), SCAN_PATH))
    build_report(recs, args.min_artists)


# -------------------------------- scan local --------------------------------

def cmd_local_scan(args):
    """Meme detection, mais sur les MP3 du disque (avant upload SFTP).

    Les banniere de site arrivent par le disque : les voir ici, c'est les
    arreter avant qu'elles n'atteignent la station.
    """
    from mutagen import File as MFile
    from mutagen.id3 import ID3

    roots = args.roots or [LOCAL_ROOT]
    files = []
    for base in roots:
        for root, _dirs, names in os.walk(base):
            files += [os.path.join(root, n) for n in sorted(names)
                      if n.lower().endswith('.mp3')]
    print('%d fichiers MP3 dans %s' % (len(files), ', '.join(roots)))

    recs = []
    for i, path in enumerate(files, 1):
        rec = {'file': path, 'path': os.path.relpath(path, roots[0]),
               'artist': '', 'title': '', 'album': ''}
        try:
            easy = MFile(path, easy=True)
            if easy is not None and easy.tags:
                for k in ('artist', 'title', 'album'):
                    rec[k] = (easy.tags.get(k) or [''])[0]
            apics = ID3(path).getall('APIC')
            if apics:
                data = apics[0].data
                im = Image.open(io.BytesIO(data))
                rec.update(md5=hashlib.md5(data).hexdigest(), bytes=len(data),
                           w=im.size[0], h=im.size[1], dhash=dhash(im))
        except Exception as e:
            rec['error'] = str(e)
        recs.append(rec)
        if i % 200 == 0:
            print('  %d/%d' % (i, len(files)))

    json.dump(recs, open(LOCAL_SCAN_PATH, 'w', encoding='utf-8'), ensure_ascii=False)
    sans = sum(1 for r in recs if not r.get('dhash'))
    print('\n%d fichiers, %d sans pochette -> %s' % (len(recs), sans, LOCAL_SCAN_PATH))
    build_report(recs, args.min_artists, LOCAL_REPORT_PATH, 'disque local')


def cmd_local_fix(args):
    from mutagen.id3 import ID3, APIC

    if not os.path.exists(LOCAL_SCAN_PATH):
        sys.exit('%s absent : lancer `local-scan` d abord.' % LOCAL_SCAN_PATH)
    recs = json.load(open(LOCAL_SCAN_PATH, encoding='utf-8'))
    bad = load_blocklist()
    targets = [r for r in recs if is_blocked(r.get('dhash'), bad)]
    print('Blocklist : %d empreinte(s)' % len(bad))
    print('Cibles    : %d fichier(s)' % len(targets))
    print('Mode      : %s\n' % ('APPLICATION REELLE' if args.apply
                                else 'DRY-RUN (rien ne sera modifie)'))
    if args.limit:
        targets = targets[:args.limit]

    stats = collections.defaultdict(int)
    for i, r in enumerate(targets, 1):
        label = '[%d/%d] %s - %s' % (i, len(targets), r['artist'], r['title'])
        img, src = (None, None)
        if not args.strip_only:
            img, src = lookup_itunes(r['artist'], r['title'])
            if not img:
                img, src = lookup_deezer(r['artist'], r['title'])
            time.sleep(LOOKUP_DELAY_SEC)
        print('%s\n    -> %s' % (label, src or 'rien de fiable, cover retiree'))
        stats['remplacees' if img else 'supprimees'] += 1
        if args.apply:
            try:
                tags = ID3(r['file'])
                tags.delall('APIC')
                if img:
                    tags.add(APIC(encoding=3, mime='image/jpeg', type=3,
                                  desc='Cover', data=img))
                tags.save()
            except Exception as e:
                print('    ERREUR ecriture : %s' % e)
                stats['erreurs'] += 1
                stats['remplacees' if img else 'supprimees'] -= 1

    print('\n=== Resume ===')
    print('  Pochettes remplacees : %d' % stats['remplacees'])
    print('  Pochettes retirees   : %d' % stats['supprimees'])
    print('  Erreurs              : %d' % stats['erreurs'])
    if not args.apply:
        print('\nRelancez avec --apply pour ecrire sur les fichiers.')
    else:
        print('\nRe-uploadez les fichiers touches en SFTP pour propager sur la station.')


def suspect_groups(recs, min_artists, min_files=1):
    """Groupes de pochettes identiques.

    min_artists=2 isole les logos evidents ; min_artists=1 sort TOUTES les
    pochettes distinctes. Une banniere collee sur un seul morceau (ou sur
    plusieurs morceaux du meme artiste) n'existe que dans ce second mode --
    c'est ce qui a laisse passer mypromosound.com et TorrentDay.
    """
    groups = collections.defaultdict(list)
    for r in recs:
        if r.get('dhash'):
            groups[r['dhash']].append(r)
    out = [(h, g) for h, g in groups.items()
           if len(g) >= min_files and len({x['artist'].strip().lower() for x in g}) >= min_artists]
    return sorted(out, key=lambda kv: len(kv[1]), reverse=True)


def art_bytes(rec):
    """Octets de la pochette d'un enregistrement, station (URL) ou local (APIC)."""
    if rec.get('art'):
        return fetch(rec['art'], timeout=30)
    from mutagen.id3 import ID3
    return ID3(rec['file']).getall('APIC')[0].data


def thumb_data_uri(rec, size=200):
    try:
        im = Image.open(io.BytesIO(art_bytes(rec))).convert('RGB')
        im.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, 'JPEG', quality=72)
        return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ''


REPORT_CSS = """
 :root { color-scheme: dark; }
 body { background:#0d0d0d; color:#e8e8e8; margin:0; padding:24px;
        font:14px/1.5 ui-monospace,Menlo,Consolas,monospace; }
 h1 { font-size:20px; letter-spacing:.06em; margin:0 0 4px; }
 .lede { color:#9a9a9a; max-width:74ch; margin:0 0 24px; }
 .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:16px; }
 .card { background:#161616; border:1px solid #262626; border-radius:8px; padding:12px; }
 .card.known { border-color:#e8c547; }
 .card img { width:100%; aspect-ratio:1; object-fit:cover; border-radius:4px; background:#000; }
 .pick { display:block; margin-bottom:8px; cursor:pointer; color:#e8c547; }
 .meta { display:flex; flex-direction:column; gap:2px; margin-top:8px; font-size:12px; }
 .meta code { color:#7ec8ff; } .meta span { color:#8a8a8a; }
 details { margin-top:8px; font-size:12px; } summary { cursor:pointer; color:#8a8a8a; }
 details ul { padding-left:16px; max-height:220px; overflow:auto; }
 details li { margin-bottom:6px; }
 .p { display:block; color:#6a6a6a; font-size:11px; }
 .out { position:sticky; bottom:0; background:#0d0d0d; border-top:1px solid #262626;
        padding:16px 0; margin-top:24px; }
 textarea { width:100%; height:140px; background:#161616; color:#e8e8e8;
            border:1px solid #262626; border-radius:6px; padding:10px; font:inherit; }
 button { background:#e8c547; color:#111; border:0; border-radius:6px; padding:8px 14px;
          font:inherit; font-weight:700; cursor:pointer; margin-top:8px; }
"""

REPORT_JS = """
 const out = document.getElementById('out');
 function sync() {
   out.value = [...document.querySelectorAll('input:checked')]
     .map(i => i.value + '  # ' + i.closest('.card').querySelector('.meta b').textContent)
     .join('\\n');
   document.querySelectorAll('.card').forEach(c =>
     c.classList.toggle('known', c.querySelector('input').checked));
 }
 document.addEventListener('change', sync); sync();
"""


def build_report(recs, min_artists, out_path=REPORT_PATH, label='station'):
    groups = suspect_groups(recs, min_artists)
    known = load_blocklist()
    print('\n%d groupe(s) (%d fichiers). Rapport en cours...'
          % (len(groups), sum(len(g) for _, g in groups)))

    with ThreadPoolExecutor(max_workers=8) as ex:
        thumbs = list(ex.map(lambda kv: thumb_data_uri(kv[1][0]), groups))

    cards = []
    for (h, g), thumb in zip(groups, thumbs):
        artists = {x['artist'] or '?' for x in g}
        tracks = ''.join(
            '<li>%s &mdash; %s<span class="p">%s</span></li>'
            % (html.escape(x['artist'] or '?'), html.escape(x['title'] or '?'),
               html.escape(x['path'])) for x in g)
        checked = ' checked' if is_blocked(h, known) else ''
        cards.append(
            '<section class="card%s">'
            '<label class="pick"><input type="checkbox" value="%s"%s> pochette a remplacer</label>'
            '<img src="%s" alt="">'
            '<div class="meta"><code>%s</code><b>%d fichiers / %d artistes</b>'
            '<span>%s&times;%s</span></div>'
            '<details><summary>voir les morceaux</summary><ul>%s</ul></details>'
            '</section>'
            % (' known' if checked else '', h, checked, thumb, h, len(g), len(artists),
               g[0].get('w', '?'), g[0].get('h', '?'), tracks))

    doc = (
        '<!doctype html><html lang="fr"><meta charset="utf-8">'
        '<title>KALBASSFM - pochettes (%s)</title>'
        '<style>%s</style>'
        '<h1>Revue des pochettes &mdash; %s &mdash; %d groupes</h1>'
        '<p class="lede">Cochez toute image qui n\'est pas une vraie pochette (banniere de '
        'site, logo de tracker, placeholder), copiez la liste en bas dans '
        '<code>tools/bad_art_hashes.txt</code>, puis lancez <code>fix --apply</code>. '
        'Les compilations et artworks de label partages sont legitimes : ne pas cocher. '
        'Les cartes bordees de jaune sont deja dans la blocklist.</p>'
        '<div class="grid">%s</div>'
        '<div class="out"><textarea id="out" readonly></textarea>'
        '<button onclick="navigator.clipboard.writeText(document.getElementById(\'out\').value)">'
        'Copier</button></div>'
        '<script>%s</script></html>'
        % (label, REPORT_CSS, label, len(groups), ''.join(cards), REPORT_JS))
    open(out_path, 'w', encoding='utf-8').write(doc)
    print('Rapport -> %s' % out_path)


# ------------------------- recherche d'une vraie pochette -------------------------

TLDS = (r'(?:com|net|org|io|me|ru|cc|info|fr|co|biz|yt|tv|to|fm|kz|xyz|club|site|'
        r'online|live|link|zip|top|pro|mobi|re|vip)')
NOISE = [
    re.compile(r'(?i)[\[\(\{][^\]\)\}]*(?:www\.|https?://|[a-z0-9-]+\.' + TLDS + r'\b)[^\]\)\}]*[\]\)\}]'),
    re.compile(r'(?i)(?:https?://)?www\.[a-z0-9.-]+[a-z0-9]'),
    re.compile(r'(?i)\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.' + TLDS + r'\b'),
    re.compile(r'(?i)\s*[\(\[]\s*(?:original|extended|radio|club|dub)?\s*(?:mix|edit|version)\s*[\)\]]'),
    re.compile(r'(?i)\s+\d{2,3}$'),  # BPM colle en fin de titre
]


def strip_noise(s):
    for p in NOISE:
        s = p.sub(' ', s or '')
    return re.sub(r'\s{2,}', ' ', s).strip(' -_.')


def toks(s):
    s = re.sub(r'[^a-z0-9 ]', ' ', strip_noise(s).lower())
    return {t for t in s.split() if len(t) > 1}


def overlap(a, b):
    return len(a & b) / len(a) if a and b else 0.0


def best_match(candidates, artist, title, get_artist, get_title):
    ta, tt = toks(artist), toks(title)
    best, score = None, 0.0
    for res in candidates:
        s = (overlap(ta, toks(get_artist(res))) + overlap(tt, toks(get_title(res)))) / 2
        if s > score:
            best, score = res, s
    return best if score >= MATCH_MIN_SCORE else None


def lookup_itunes(artist, title):
    q = ('%s %s' % (strip_noise(artist), strip_noise(title))).strip()
    if not q:
        return None, None
    url = 'https://itunes.apple.com/search?' + urllib.parse.urlencode(
        {'term': q, 'media': 'music', 'entity': 'song', 'limit': 5})
    try:
        data = json.loads(fetch(url).decode('utf-8'))
    except Exception as e:
        print('    [iTunes] %s' % e)
        return None, None
    best = best_match(data.get('results', []), artist, title,
                      lambda r: r.get('artistName', ''), lambda r: r.get('trackName', ''))
    if not best or not best.get('artworkUrl100'):
        return None, None
    return fetch_image([re.sub(r'\d+x\d+bb', '600x600bb', best['artworkUrl100'])])


def lookup_deezer(artist, title):
    """Filet de securite : le catalogue underground manque souvent chez Apple."""
    q = ('%s %s' % (strip_noise(artist), strip_noise(title))).strip()
    if not q:
        return None, None
    url = 'https://api.deezer.com/search?' + urllib.parse.urlencode({'q': q, 'limit': 5})
    try:
        data = json.loads(fetch(url).decode('utf-8'))
    except Exception as e:
        print('    [Deezer] %s' % e)
        return None, None
    best = best_match(data.get('data', []), artist, title,
                      lambda r: (r.get('artist') or {}).get('name', ''),
                      lambda r: r.get('title', ''))
    if not best:
        return None, None
    album = best.get('album') or {}
    return fetch_image([album.get('cover_xl'), album.get('cover_big'),
                        album.get('cover_medium')])


# ------------------------------------ fix ------------------------------------

def load_blocklist():
    if not os.path.exists(BLOCKLIST_PATH):
        return set()
    out = set()
    for line in open(BLOCKLIST_PATH, encoding='utf-8'):
        line = line.split('#')[0].strip().lower()
        if re.fullmatch(r'[0-9a-f]{16}', line):
            out.add(line)
    return out


def is_blocked(h, blocklist, tol=BLOCK_TOLERANCE):
    """Vrai si l'empreinte est a <= tol bits d'une entree de la blocklist.

    Les sites re-cadrent leur banniere (heydj.pro existe en 744x744 et en
    836x744) : l'egalite stricte rate ces variantes, qui restent a 5 bits
    l'une de l'autre. Mesure sur cette bibliotheque : deux pochettes
    reellement differentes tombent a <= 8 bits dans 0,035 % des cas.
    """
    if not h:
        return False
    n = int(h, 16)
    return any(bin(n ^ int(b, 16)).count('1') <= tol for b in blocklist)


def cmd_fix(args):
    if not os.path.exists(SCAN_PATH):
        sys.exit('%s absent : lancer `python fix_artwork.py scan` d abord.' % SCAN_PATH)
    recs = json.load(open(SCAN_PATH, encoding='utf-8'))
    bad = load_blocklist()
    if not bad:
        sys.exit('%s vide : cocher les pochettes dans %s.' % (BLOCKLIST_PATH, REPORT_PATH))

    targets = [r for r in recs if is_blocked(r.get('dhash'), bad)]
    missing = [r for r in recs if r.get('no_art') and (r['artist'] or r['title'])]
    print('Blocklist : %d empreinte(s)' % len(bad))
    print('Bannieres : %d fichier(s)' % len(targets))
    print('Sans pochette : %d fichier(s)%s'
          % (len(missing), '' if args.fill_missing else ' (--fill-missing pour les traiter)'))
    if args.fill_missing:
        targets += missing
    print('Mode      : %s\n' % ('APPLICATION REELLE' if args.apply
                                else 'DRY-RUN (rien ne sera modifie)'))
    if args.limit:
        targets = targets[:args.limit]

    stats = collections.defaultdict(int)
    for i, r in enumerate(targets, 1):
        label = '[%d/%d] %s - %s' % (i, len(targets), r['artist'], r['title'])
        img = src = None
        if not args.strip_only:
            img, src = lookup_itunes(r['artist'], r['title'])
            if not img:
                img, src = lookup_deezer(r['artist'], r['title'])
            time.sleep(LOOKUP_DELAY_SEC)

        if img:
            print('%s\n    -> %s' % (label, src))
            stats['remplacees'] += 1
            if args.apply:
                body, ctype = multipart('file', 'cover.jpg', img)
                try:
                    api_request('/station/%s/art/%s' % (STATION_ID, r['id']), 'POST', body, ctype)
                except Exception as e:
                    print('    ERREUR upload : %s' % e)
                    stats['erreurs'] += 1
                    stats['remplacees'] -= 1
        elif r.get('no_art'):
            print('%s\n    -> rien trouve, le morceau reste sans pochette' % label)
            stats['sans_suite'] += 1
        else:
            print('%s\n    -> rien de fiable, suppression (image generique AzuraCast)' % label)
            stats['supprimees'] += 1
            if args.apply:
                try:
                    api_request('/station/%s/art/%s' % (STATION_ID, r['id']), 'DELETE')
                except Exception as e:
                    print('    ERREUR suppression : %s' % e)
                    stats['erreurs'] += 1
                    stats['supprimees'] -= 1

    print('\n=== Resume ===')
    print('  Pochettes remplacees : %d' % stats['remplacees'])
    print('  Pochettes supprimees : %d' % stats['supprimees'])
    print('  Erreurs              : %d' % stats['erreurs'])
    if not args.apply:
        print('\nRelancez avec --apply pour ecrire sur la station.')
    else:
        print('\nPensez a relancer `scan` pour rafraichir le cache d empreintes.')


def cmd_report(args):
    scan = LOCAL_SCAN_PATH if args.local else SCAN_PATH
    if not os.path.exists(scan):
        sys.exit('%s absent : lancer le scan correspondant d abord.' % scan)
    build_report(json.load(open(scan, encoding='utf-8')), args.min_artists,
                 LOCAL_REPORT_PATH if args.local else REPORT_PATH,
                 'disque local' if args.local else 'station')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('scan', help='telecharge et empreinte toutes les pochettes')
    s.add_argument('--refresh', action='store_true', help='ignore le cache')
    s.add_argument('--workers', type=int, default=16)
    s.add_argument('--min-artists', type=int, default=MIN_ARTISTS)
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser('report', help='regenere le rapport HTML depuis le cache')
    s.add_argument('--min-artists', type=int, default=MIN_ARTISTS,
                   help='1 = toutes les pochettes distinctes (defaut : %d)' % MIN_ARTISTS)
    s.add_argument('--local', action='store_true', help='rapport du scan disque')
    s.set_defaults(func=cmd_report)

    s = sub.add_parser('local-scan', help='empreinte les pochettes des MP3 du disque')
    s.add_argument('roots', nargs='*', help='dossiers a parcourir (defaut : New_prog)')
    s.add_argument('--min-artists', type=int, default=1,
                   help='1 = toutes les pochettes distinctes (defaut)')
    s.set_defaults(func=cmd_local_scan)

    s = sub.add_parser('local-fix', help='remplace les pochettes blocklistees sur le disque')
    s.add_argument('--apply', action='store_true', help='ecrit reellement dans les MP3')
    s.add_argument('--strip-only', action='store_true',
                   help='retire sans chercher de remplacement (rapide)')
    s.add_argument('--limit', type=int, help='ne traite que les N premiers (test)')
    s.set_defaults(func=cmd_local_fix)

    s = sub.add_parser('fix', help='remplace les pochettes listees dans la blocklist')
    s.add_argument('--apply', action='store_true', help='ecrit reellement sur la station')
    s.add_argument('--strip-only', action='store_true',
                   help='supprime sans chercher de remplacement (rapide)')
    s.add_argument('--limit', type=int, help='ne traite que les N premiers (test)')
    s.add_argument('--fill-missing', action='store_true',
                   help='traite aussi les morceaux sans aucune pochette')
    s.set_defaults(func=cmd_fix)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
