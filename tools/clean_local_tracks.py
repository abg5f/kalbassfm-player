#!/usr/bin/env python3
"""
Nettoie les MP3 fraichement copies depuis Rekordbox (titres/artistes/noms de
fichiers pollues par des sites de telechargement, cover art = logo du site).

- Nettoie les tags ID3 (titre/artiste/album) et le nom de fichier.
- Detecte les covers "logo de site" (meme image chez >= N artistes distincts)
  et les supprime.
- Pour les morceaux sans cover (ou dont la cover vient d'etre supprimee),
  cherche une vraie pochette via l'API iTunes Search (gratuite, sans cle) et
  l'embarque si le match est raisonnablement sur ; sinon laisse vide.

Par defaut : dry-run (rien n'est modifie). Ajouter --apply pour executer.
"""
import os
import re
import sys
import json
import time
import hashlib
import urllib.request
import urllib.parse
from collections import defaultdict

from mutagen import File as MFile
from mutagen.id3 import ID3, APIC

DEFAULT_ROOTS = [
    r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog\1_morning",
    r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog\2_afternoon",
    r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog\3_evening",
    r"C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog\4_night",
]
arg_roots = [a for a in sys.argv[1:] if not a.startswith('--')]
ROOTS = arg_roots if arg_roots else DEFAULT_ROOTS
APPLY = '--apply' in sys.argv

LOGO_THRESHOLD = 4          # meme image chez >= N artistes distincts -> logo de site
ITUNES_MIN_SCORE = 0.6      # score minimum artiste+titre pour accepter un match
ITUNES_DELAY_SEC = 3.2      # throttle : API iTunes limitee (~20 req/min)

TLDS = r'(?:com|net|org|io|me|ru|cc|info|fr|co|biz|yt|tv|to|fm|kz|xyz|club|site|online|live|link|zip|top|pro|mobi|re|vip)'
PATTERNS = [
    re.compile(r'(?i)[\[\(\{][^\]\)\}]*(?:www\.|https?://|[a-z0-9-]+\.' + TLDS + r'\b)[^\]\)\}]*[\]\)\}]'),
    re.compile(r'(?i)(?:https?://)?www\.[a-z0-9.-]+[a-z0-9]'),
    re.compile(r'(?i)\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.' + TLDS + r'\b'),
]


def clean(s):
    if not s:
        return s
    for p in PATTERNS:
        s = p.sub('', s)
    s = re.sub(r'[\[\(\{]\s*[\]\)\}]', '', s)
    s = s.replace('_', ' ')
    s = re.sub(r'\s{2,}', ' ', s)
    s = re.sub(r'\s+([.,])', r'\1', s)
    return s.strip(' -./').strip()


def tokens(s):
    s = clean(s or '').lower()
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return set(t for t in s.split() if len(t) > 1)


def overlap(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a)


def itunes_lookup(artist, title):
    """Retourne (artwork_bytes, artwork_url) ou (None, None)."""
    query = f"{artist} {title}".strip()
    if not query:
        return None, None
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode({
        'term': query, 'media': 'music', 'entity': 'song', 'limit': 5,
    })
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (KalbassFM cleaner)'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"    [iTunes] erreur requete : {e}")
        return None, None

    target_artist = tokens(artist)
    target_title = tokens(title)
    best = None
    best_score = 0.0
    for res in data.get('results', []):
        score = (overlap(target_artist, tokens(res.get('artistName', ''))) +
                 overlap(target_title, tokens(res.get('trackName', '')))) / 2
        if score > best_score:
            best_score = score
            best = res

    if not best or best_score < ITUNES_MIN_SCORE:
        return None, None

    art_url = best.get('artworkUrl100', '')
    if not art_url:
        return None, None
    art_url_hd = re.sub(r'\d+x\d+bb', '600x600bb', art_url)

    img_req = urllib.request.Request(art_url_hd, headers={'User-Agent': 'Mozilla/5.0 (KalbassFM cleaner)'})
    try:
        with urllib.request.urlopen(img_req, timeout=10) as r:
            img_bytes = r.read()
        return img_bytes, art_url_hd
    except Exception as e:
        print(f"    [iTunes] erreur telechargement image : {e}")
        return None, None


def main():
    mode = 'APPLICATION REELLE' if APPLY else 'DRY-RUN (rien ne sera modifie)'
    print("Dossiers : " + ", ".join(ROOTS))
    print(f"Mode     : {mode}\n")

    mp3_files = []
    for base in ROOTS:
        for root, dirs, files in os.walk(base):
            for f in sorted(files):
                if f.lower().endswith('.mp3'):
                    mp3_files.append(os.path.join(root, f))
    print(f"{len(mp3_files)} fichiers MP3 trouves.\n")

    # ── Passe 1 : indexer les covers par hash pour detecter les logos de site ──
    print("Analyse des cover art (detection des logos de site)...")
    cover_groups = defaultdict(lambda: {'files': [], 'artists': set()})
    file_covers = {}
    for path in mp3_files:
        try:
            tags = ID3(path)
        except Exception:
            file_covers[path] = None
            continue
        apics = tags.getall('APIC')
        if not apics:
            file_covers[path] = None
            continue
        h = hashlib.md5(apics[0].data).hexdigest()
        file_covers[path] = h
        easy = MFile(path, easy=True)
        artist = (easy.tags.get('artist') or ['?'])[0] if easy and easy.tags else '?'
        cover_groups[h]['files'].append(path)
        cover_groups[h]['artists'].add(artist)

    bad_hashes = {h for h, g in cover_groups.items() if len(g['artists']) >= LOGO_THRESHOLD}
    print(f"  -> {len(bad_hashes)} image(s) suspecte(s) (logo de site) detectee(s), "
          f"presentes sur {sum(len(cover_groups[h]['files']) for h in bad_hashes)} fichiers.\n")

    # ── Passe 2 : nettoyage tags/nom de fichier + gestion cover ──
    report = []
    stats = defaultdict(int)

    for path in mp3_files:
        fname = os.path.basename(path)
        line_prefix = f"[{fname}]"
        changed_tag = False

        try:
            audio = MFile(path, easy=True)
        except Exception as e:
            print(f"{line_prefix} ERREUR lecture tags : {e}")
            continue

        title = artist = ''
        if audio and audio.tags is not None:
            for tag in ('title', 'artist', 'album'):
                vals = audio.tags.get(tag)
                if not vals:
                    continue
                new = clean(vals[0])
                if tag == 'title':
                    title = new
                if tag == 'artist':
                    artist = new
                if new and new != vals[0]:
                    print(f"{line_prefix} TAG {tag} : {vals[0]!r} -> {new!r}")
                    if APPLY:
                        audio.tags[tag] = new
                    changed_tag = True
                    stats['tags_nettoyes'] += 1
            if APPLY and changed_tag:
                audio.save()

        # Nom de fichier (le prefixe NNN_ de position, s'il existe, est preserve
        # tel quel -- clean() remplace les "_" par des espaces et le casserait sinon)
        stem, ext = os.path.splitext(fname)
        pos_match = re.match(r'^(\d{3}_)(.*)$', stem)
        pos_prefix, stem_to_clean = pos_match.groups() if pos_match else ('', stem)
        new_stem = pos_prefix + clean(stem_to_clean)
        new_path = path
        if new_stem and new_stem != stem:
            candidate = os.path.join(os.path.dirname(path), new_stem + ext)
            if os.path.exists(candidate):
                print(f"{line_prefix} nom deja pris, fichier non renomme : {new_stem + ext}")
            else:
                print(f"{line_prefix} RENOMME -> {new_stem + ext}")
                if APPLY:
                    os.rename(path, candidate)
                    new_path = candidate
                stats['fichiers_renommes'] += 1

        # Cover art
        cover_hash = file_covers.get(path)
        needs_new_cover = False
        if cover_hash is not None and cover_hash in bad_hashes:
            print(f"{line_prefix} cover suspecte (logo de site) -> suppression")
            if APPLY:
                try:
                    t = ID3(new_path)
                    t.delall('APIC')
                    t.save()
                except Exception as e:
                    print(f"    ERREUR suppression cover : {e}")
            stats['covers_supprimees'] += 1
            needs_new_cover = True
        elif cover_hash is None:
            needs_new_cover = True

        if needs_new_cover and (title or artist):
            time.sleep(ITUNES_DELAY_SEC)
            img_bytes, art_url = itunes_lookup(artist, title)
            if img_bytes:
                print(f"{line_prefix} cover trouvee via iTunes -> {art_url}")
                if APPLY:
                    try:
                        t = ID3(new_path)
                        t.delall('APIC')
                        t.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img_bytes))
                        t.save()
                    except Exception as e:
                        print(f"    ERREUR embarquement cover : {e}")
                stats['covers_remplacees'] += 1
            else:
                print(f"{line_prefix} aucune cover fiable trouvee -> laisse vide")
                stats['covers_laissees_vides'] += 1

        report.append(line_prefix)

    print("\n=== Resume ===")
    print(f"  Tags nettoyes         : {stats['tags_nettoyes']}")
    print(f"  Fichiers renommes     : {stats['fichiers_renommes']}")
    print(f"  Covers supprimees     : {stats['covers_supprimees']}")
    print(f"  Covers remplacees     : {stats['covers_remplacees']}")
    print(f"  Covers laissees vides : {stats['covers_laissees_vides']}")
    if not APPLY:
        print("\nRelancez avec --apply pour executer ces changements.")


if __name__ == '__main__':
    main()
