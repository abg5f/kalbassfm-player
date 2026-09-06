# KALBASSFM — Web Player

Player web pour **KALBASSFM**, webradio 100% électronique diffusant électro, disco, funk et house 24/7.

🎧 **Live** → [kalbassfm-player.vercel.app](https://kalbassfm-player.vercel.app/)
📡 **Stream** → `kalbassfm.duckdns.org` (Icecast / AzuraCast)

---

## Fonctionnalités

- Lecteur audio avec flux HTTPS en temps réel
- Titre en cours + pochette d'album
- Égaliseur réactif au son (Web Audio API — désactivé sur mobile pour survivre à l'écran verrouillé)
- Compteur d'auditeurs en direct
- Historique des titres joués
- Recherche YouTube du morceau en cours
- Réactions 🔥
- Panneau Mixtapes : les DJ sets publiés en podcast, avec **mini-lecteur** (barre de progression déplaçable, −15 s / +30 s, pause qui garde la position)
- Minuteur de sommeil
- Partage du titre en cours
- Bandeau de financement (30 €/mois) — fermable, revient au bout de 30 jours
- Bot Telegram admin : `/search <artiste ou titre>` cherche dans la bibliothèque et propose, pour le résultat choisi, l'ajout à la **file d'attente**, le déplacement de playlist, la sortie d'antenne ou la suppression ; `/queue` montre la file à venir et son avance (~25-30 min). L'ajout à la file emprunte le mécanisme de **demande de titre** d'AzuraCast (seule voie d'écriture dans la file) : « Autoriser les demandes de titres » doit être actif sur la station, et « Inclure dans les demandes » sur la playlist du morceau — sinon le bot relaie tel quel le refus d'AzuraCast
- Candidature DJ « Submit a mix » (nom, email, lien du set en HQ, style, Instagram/SoundCloud optionnels) → notification Telegram admin + archive Redis, relue avec `/submissions`
- Annonce d'une mixtape programmée dans le chat live avec les liens sociaux du DJ (bouton 📣 sous `/submissions`) — les liens ne sont cliquables que dans les messages admin
- Grille de programme "horloge à bacs pondérés" (heure Martinique UTC-4) :
  - 6h–9h : Lever (chill, downtempo, jungle douce)
  - 9h–13h : Groove solaire (disco, funk, soul, nu-disco)
  - 13h–17h : Alizés (house éclectique, UK garage)
  - 17h–20h : Sunset (deep/melodic house)
  - 20h–23h : Warm-up (tech house, house club)
  - 23h–2h : Peak (techno) — ponctué de jungle/DnB
  - 2h–6h : Nuit profonde (deep/minimal/dub techno) — ponctué de jungle/DnB

  Chaque fenêtre mélange un bac dominant et 1-2 bacs invités (poids AzuraCast),
  en mode Shuffled avec séparation artiste 120 min : aucune journée ne ressemble
  à la précédente.

## PWA

Installable sur mobile et desktop :
- `manifest.webmanifest` + `sw.js`
- Icônes 192px / 512px (mascotte calebasse Kalbass)
- Instructions d'installation iOS incluses dans l'interface
- Raccourci permanent dans le header

## Stack

| Couche | Techno |
|--------|--------|
| Player | HTML / CSS / JS vanilla |
| Audio | Web Audio API + `<audio>` natif |
| Déploiement | Vercel (auto sur push GitHub) |
| Streaming | AzuraCast + Icecast + Liquidsoap sur VPS Ubuntu |
| Serverless | `api/` (chat live, supporters, candidatures DJ, bot Telegram admin, Flappy Kalbass — Vercel KV/Upstash Redis) |

## Infrastructure

```
VPS 167.233.226.128 (Ubuntu / Docker)
  └── AzuraCast
        ├── Icecast (diffusion)
        ├── Liquidsoap (AutoDJ)
        └── ~370+ morceaux, 4 playlists par créneau horaire

Vercel
  └── kalbassfm-player.vercel.app
        └── Player statique + fonctions serverless (chat, supporters, candidatures DJ, bot admin, Flappy)

Domaine : kalbassfm.duckdns.org (DuckDNS + Let's Encrypt auto-renouvelé)
```

## Outils locaux (`tools/`)

L'ingestion se fait en **deux étapes distinctes**, dans cet ordre. Le triage classe, l'analyse juge et met en ligne. Rien n'atteint l'antenne sans être passé par la seconde.

- `triage_new_tracks.py` (+ `triage.bat`) — **étape 1, classer** : nettoyage tags/covers, dédoublonnage, analyse Essentia, classement dans le bon bac, inscription dans `metadata.json` et dans la file d'attente `pending_review.json`. **N'ouvre aucune connexion SFTP** : ce qui sort d'ici est sur le disque, pas à la radio.
- `analyse_new_tracks.py` (+ `analyse.bat`) — **étape 2, juger puis envoyer** : reprend la file, note chaque titre avec la grille de `track_gate.py` (trop énergique ? trop répétitif ? trop loin de la house ?) et envoie sur AzuraCast ce qui passe. Un `reject` part dans `New_prog/_a_revoir/` avec le motif du verdict et sort de `metadata.json` ; un `review` passe en ligne mais reste signalé (`--strict` l'écarte aussi). Aucune re-analyse — les descripteurs sont déjà en base, donc pas de WSL et quelques secondes. Dry-run par défaut. Régénère `api/bpm-table.json` en fin de course, une fois `metadata.json` dans son état définitif.
  ```
  python analyse_new_tracks.py                    # verdicts seuls, rien ne bouge
  python analyse_new_tracks.py --apply            # applique et met en ligne
  python analyse_new_tracks.py --apply --strict   # écarte aussi les « à écouter »
  python analyse_new_tracks.py --requeue "titre.mp3"   # renvoie un écarté dans _incoming
  ```
  **Pourquoi l'envoi est de ce côté du verdict :** un morceau posé sur le serveur peut passer à l'antenne dans les minutes qui suivent. Si le triage envoyait tout, un titre jugé trop dur le lendemain aurait déjà tourné.
- `azuracast_upload.py` — envoi SFTP et files d'attente, partagés par les deux étapes. `pending_review.json` (classé, pas encore jugé) et `pending_uploads.json` (jugé bon, envoi échoué) ne disent pas la même chose : `sync_library.py` les distingue pour ne jamais proposer d'écarter un morceau qui attend simplement son tour.
- `classify_bins.py` — source de vérité de la grille : 8 bacs, classification genre-d'abord/énergie-ensuite, seuils auto-calibrés par percentiles
- `analyze_essentia.py` — analyse BPM/énergie/genre/mood (WSL2, modèles TensorFlow)
- `migrate_grid.py` / `resync_metadata.py` — migrations one-shot (grille 4→8 bacs, réparation metadata)
- `clean_local_tracks.py` — nettoie tags et noms de fichiers, détecte les pochettes de sites pirates et les remplace via iTunes Search API
- `fix_artwork.py` — chasse aux **bannières de site** (heydj.pro, ClapCrate, TorrentDay, mypromosound…) là où `clean_local_tracks.py` ne va pas : sur la station en ligne (API AzuraCast) **et** sur le disque. Empreinte perceptuelle (dHash, tolérance 8 bits pour les recadrages), regroupement, rapport visuel à cocher, puis remplacement via iTunes + Deezer. Les empreintes validées vivent dans `bad_art_hashes.txt`, que le triage consulte aussi pour refuser ces images à l'ingestion.
  ```
  python fix_artwork.py scan                        # station : empreinte + rapport HTML
  python fix_artwork.py fix --apply                 # remplace les bannières
  python fix_artwork.py fix --apply --fill-missing  # + morceaux sans aucune pochette
  python fix_artwork.py local-scan                  # disque : New_prog
  python fix_artwork.py local-fix --apply           # écrit dans les MP3 (re-upload SFTP ensuite)
  ```
  **Politique « dans le doute, on retire »** (une pochette par défaut prend le relais) : `--suspects` cible tout ce qui est douteux sans rien cocher — même image portée par plusieurs artistes, ou vignette plus petite que `--min-size` — et `--strip-only` retire au lieu de chercher un remplacement.
  ```
  python fix_artwork.py fix --suspects --strip-only            # dry-run station
  python fix_artwork.py fix --suspects --strip-only --apply
  python fix_artwork.py local-fix --suspects --strip-only --apply   # disque
  ```
- `track_gate.py` — **filtre d'entrée** : dit d'un morceau candidat s'il a sa place à l'antenne, avec la même grille que `review_energy.py` mais appliquée à un titre isolé. Deux niveaux : `screen` (avant téléchargement, texte seul — genre annoncé, BPM collé au nom, durée : attrape hardcore, psytrance, sets d'une heure, intros de 40 s) et `audit` (après téléchargement, vraie analyse Essentia — un extrait de 60-90 s suffit). Trois verdicts : `keep` / `review` / `reject`, aucun n'efface quoi que ce soit.
  ```
  python track_gate.py refresh                        # fige la distribution de la bibliothèque
  python track_gate.py refresh --exclude tools/energy_review_selection.txt   # après un nettoyage : cale les seuils sur ce que tu as écarté
  python track_gate.py screen "Artist - Title 174" --duration 3600
  python track_gate.py screen --stdin < candidats.txt # un JSON par ligne, pour un outil d'acquisition
  python track_gate.py audit extrait.mp3
  ```
  C'est `analyse_new_tracks.py` (étape 2 de l'ingestion) qui l'applique aux nouveaux morceaux ; un outil externe type yt2slskd l'appelle en `--stdin` ou importe `screen_text()` / `audit_descriptors()`.
- `sync_library.py` — **remet le PC et AzuraCast iso dans les deux sens** après une session de nettoyage : ce que tu as supprimé depuis le bot Telegram et qui traîne encore sur le PC, ce que tu as supprimé sur le PC et qui tourne encore à l'antenne, plus les entrées orphelines de `metadata.json`. Croise la vue API (médias indexés) et la vue SFTP (fichiers réels) pour ne jamais confondre une suppression volontaire avec un fichier simplement pas encore scanné par AzuraCast. Dry-run par défaut ; les mp3 retirés des bacs locaux sont rangés dans `New_prog/_ecartes/<bac>/`, pas effacés.
  ```
  python sync_library.py                        # rapport, rien n'est écrit
  python sync_library.py --apply                # applique les deux sens
  python sync_library.py --apply --only-server  # ne touche qu'à AzuraCast
  ```
- `review_energy.py` — **revue des morceaux trop énergiques / répétitifs / éloignés de la house** (ceux qui font partir un auditeur en cours d'écoute). Score en percentiles sur quatre axes — intensité, monotonie (`dynamic_complexity`), écart à la house (genres Discogs + tempo), agressivité — puis rapport HTML à cocher **avec un lecteur audio par titre pointant les mp3 locaux**, ou export `.m3u` pour VLC/foobar. La sélection cochée sort de l'antenne (retirée de toutes les playlists, fichier conservé) ou est supprimée pour de bon.
  ```
  python review_energy.py list                    # top 60 en console
  python review_energy.py report                  # rapport HTML à cocher
  python review_energy.py m3u --bac 6_techno      # playlist d'écoute d'un bac
  python review_energy.py select                  # écrit la sélection d'un coup (après écoute)
  python review_energy.py apply                   # dry-run de la sélection
  python review_energy.py apply --apply           # sortie d'antenne (réversible)
  python review_energy.py apply --apply --delete  # suppression + mp3 local rangé dans _ecartes/
  ```
- `make_og_image.py` — génère `og-image.png`, la vignette de partage (Open Graph / annuaires type TuneIn)
- `import-rekordbox.ps1` — matche les exports `.txt` Rekordbox aux fichiers audio
- `build_rotation.py` / `export_rotation.py` — ⚠️ superseded (l'ordonnancement est délégué à AzuraCast)

Pipeline : **téléchargements → `_incoming` → `triage.bat` → `New_prog/<bac>` → upload SFTP → AzuraCast (Shuffled + poids + séparation artiste)**

## Roadmap

- [ ] Connecter Upstash KV pour les réactions 🔥 partagées entre auditeurs
- [ ] Synchro hebdomadaire PC → radio (WinSCP + tâche planifiée Windows)
- [ ] Jingles générés avec ElevenLabs
- [ ] Déclaration SACEM webradio
- [ ] Domaine payant (optionnel — bascule rapide depuis DuckDNS)
