# KALBASSFM — Graphe de connaissances

> Généré le 2026-07-09, mis à jour le 2026-07-16, 2026-07-17, le 2026-07-20 (3 fois) puis le 2026-07-21 (3 fois) via `/graphify` (codebase complet : player, serverless, outillage, docs de planification).

## Vue d'ensemble

- **62 nœuds**, **109 relations**, **8 communautés** détectées.
- Le graphe couvre : le player web (`index.html`, layout desktop réorganisé, Top 5 retiré), les fonctions serverless (`api/chat.js`, `api/telegram.js`, `api/supporters.js`, `api/flappy.js` — chat live/bot admin/dons/mini-jeux, Upstash Redis), le **jeu "devine le BPM" intégré au chat** (`BpmGuesserFeature`, table `api/bpm-table.json` générée par `tools/export_bpm_table.py`), le **pseudo persistant choisi par l'auditeur** (`ChatNicknameFeature`, hash `chat:pseudos`), l'**horloge à bacs pondérés** (8 bacs, `classify_bins.py`), le pipeline d'ingestion (avec file de retry SFTP), la playlist Jingles native AzuraCast, la PWA, l'infra (AzuraCast/Icecast/Liquidsoap/VPS/Vercel/DuckDNS), les intégrations externes (Buy Me a Coffee, API Claude), les documents `.planning/`, l'**incident de quota Upstash** du 2026-07-21 et sa résolution, et le plan (non codé) du système de vote de playlist par genre.

## Communautés

| Communauté | Membres clés |
|---|---|
| Player / Frontend | index.html, layout desktop, sw.js, manifest, PWA, égaliseur, chat live, popup contact, now-playing, Supporters, Vibe Streak, bandeau épinglé, Request, Flappy Kalbass |
| Infra / Streaming | AzuraCast, Icecast, Liquidsoap, VPS, DuckDNS, GitHub, Vercel, Admin API, playlist Jingles |
| Serverless / API (chat + bot Telegram admin + Flappy + BPM) | api/chat.js, api/telegram.js, api/supporters.js, api/flappy.js, Upstash Redis, chat live, bot admin, réponse admin, badge supporter, renommage modérateur, pseudo choisi par l'auditeur, jeu BPM, incident quota Upstash, vote playlist (planifié) |
| Intégrations externes (dons, IA) | Buy Me a Coffee, API Claude, api/supporters.js |
| Outillage / Pipeline musique | pipeline Rekordbox, import-rekordbox.ps1, clean_local_tracks.py, RaiDrive, iTunes Search API, triage (file de retry SFTP), export_bpm_table.py, migrations |
| Pipeline Essentia / Grille 8 bacs | analyze_essentia.py, classify_bins.py, migrate_grid.py, resync_metadata.py, build_rotation.py (superseded) |
| Planning / Business | PROJECT.md, ROADMAP.md, PLAN.md, REQUIREMENTS.md, EXECUTION_CHECKLIST.md, STATE.md, SACEM |
| Contexte de session | CONTEXT.md, README.md |

## God nodes (les plus connectés)

1. **index.html** (degré 16) — hub de toutes les features front (now-playing, chat live, layout desktop, Supporters, Vibe Streak, bandeau épinglé, Request, Flappy Kalbass, pseudo persistant, PWA).
2. **api/chat.js** (degré 12) — chat live + modération + renommage (admin et auditeur) + jeu BPM (BpmGuesserFeature) + annonce Flappy + détection d'erreur Upstash. Devient le nœud serveur le plus connecté avec l'ajout du pseudo choisi par l'auditeur.
3. **ChatFeature** (degré 11) — panneau chat live, cible de la plupart des features de modération, du jeu BPM et du choix de pseudo.
4. **api/telegram.js** (degré 11) — bot admin, toutes les commandes (reply, supporters, renommage modérateur, bandeau épinglé + auto-pin pause, /ask Claude, suppression bibliothèque), résilience handleCallback, kill-switch Redis.
5. **AzuraCast** (degré 10) — cœur de l'infra streaming ET de la programmation (l'horloge est exécutée par ses playlists Shuffled + poids).
6. **ProgrammeGrid / Horloge à bacs pondérés** (degré 8) — grille 8 bacs, remplace les 4 créneaux à ordre figé.
7. **tools/classify_bins.py** — source de vérité unique de la classification (seuils auto-calibrés par percentiles).

## Note — 2026-07-21 : incident de quota Upstash et suppression du Top 5

Le plan gratuit Upstash (500k commandes/mois) a été épuisé plusieurs fois : le polling front (chat, Top 5, supporters) représentait ~99% des commandes (lectures), contre ~1% pour les écritures admin. Symptômes en prod : chat/Top 5/supporters clignotant vers un état vide (une erreur Upstash était traitée silencieusement comme une liste vide) et boutons de suppression Telegram sans effet visible. Résolution en plusieurs étapes : espacement du polling, détection explicite des erreurs Upstash, coupure temporaire complète (`REDIS_PAUSED`) le temps de la réflexion, **suppression définitive du Top 5/vote** (`api/reactions.js`, plus gros consommateur), puis passage d'Upstash en Pay As You Go — `REDIS_PAUSED` repassé à `false`. Voir le nœud `RedisQuotaIncident` pour le détail.

## Note — 2026-07-21 (suite) : jeu "devine le BPM" et incident de prod associé

Le BPM n'existe pas dans les métadonnées exposées par l'API AzuraCast (`custom_fields` vide, vérifié en direct). `tools/export_bpm_table.py` lit les tags ID3 réels (mutagen) pour associer le BPM déjà calculé par Essentia à l'artiste+titre exact qu'AzuraCast affiche → `api/bpm-table.json` (749/825 morceaux). `api/chat.js` matche le morceau en cours contre cette table dès qu'un message ressemble à un guess numérique, et répond via le pseudo réservé `BPM GUESSER` (vert fluo). Le déploiement a d'abord cassé `/api/chat` en prod (500, chat invisible pour tous) à cause d'un chargement JSON via `fs.readFileSync(import.meta.url)` qui ne s'est pas comporté comme attendu une fois la fonction empaquetée par Vercel — corrigé par un import JSON statique avec assertion (`with { type: 'json' }`), vérifié cette fois par chargement réel du module en local (pas seulement `node --check`).

## Note — 2026-07-21 (suite) : pseudo persistant fusionné depuis une branche externe

Branche `claude/chat-persistent-user-id-7iol95` (créée après le dernier commit de `main`, fusionnée sans conflit) : bouton "Set nickname" au-dessus du chat, pseudo choisi par l'auditeur stocké dans le hash Redis `chat:pseudos` (clientId → pseudo) et en miroir `localStorage`. Coexiste avec `ChatRenameFeature` (modération admin) : priorité finale = badge supporter > renommage forcé par l'admin > pseudo choisi par l'auditeur > `Listener-XXXX` par défaut. Voir le nœud `ChatNicknameFeature`.

## Comment explorer

- `graphify query "<mot-clé>"` — ex. `graphify query "telegram"`, `graphify query "classify"`
- `graphify path "index.html" "AzuraCastAdminAPI"` — chemin entre deux nœuds
- `graphify explain "ProgrammeGrid"` — résumé + connexions d'un nœud
- `graphify community "serverless-api"` — lister les membres d'une communauté
- `graphify god-nodes` — lister les hubs

## Notes

- Ce graphe est une snapshot manuelle (pas d'outil `graphify` CLI exécuté — construit/mis à jour par lecture directe des fichiers du repo). Relancer `/graphify` après des changements significatifs.
- **La programmation a changé de paradigme le 2026-07-16** : plus aucun ordre de lecture calculé localement (préfixes `NNN_` supprimés, `build_rotation.py`/`export_rotation.py` superseded). Les 8 bacs sont des dossiers/playlists AzuraCast en mode Shuffled avec poids et plannings qui se chevauchent (dominant + invités), séparation artiste 120 min, ponctuation jungle 1/14 chansons la nuit. La variété quotidienne est native — aucune régénération à faire, jamais.
- La classification (`classify_bins.py`) est genre-d'abord/énergie-ensuite avec seuils **auto-calibrés par percentiles par famille** — s'adapte seule à l'évolution de la bibliothèque. Vetos structurels : techno/jungle énergiques ne peuvent jamais tomber dans les bacs du matin.
- Le **bot Telegram admin** (`api/telegram.js`, 2026-07-17) : /skip, /msg, /jingle, /ban, /unban, /pause_chat, /resume_chat + modération par boutons inline sur chaque notification de message du chat. Un seul admin autorisé. `/jingle` a nécessité deux correctifs en prod : les jingles sont des voix off sans le mot "jingle" dans leur titre (filtre par marqueur "kalbass fm" à la place) + AzuraCast rejette les requêtes API sans `User-Agent` crédible (détection anti-crawler côté `SubmitAction`).
- **Interface passée en anglais** (2026-07-17, tard) : UI complète, meta og/twitter, manifest PWA. Messages admin affichés en gras via un flag `admin:true` posé exclusivement côté serveur (infalsifiable par un client). Chat animé par des messages automatiques (7 transitions horloge + rappel vote/jour) postés paresseusement au fil des GET avec verrou Redis, sans cron. La liste de chat a une hauteur fixe (plus `max-height`) pour ne jamais se redimensionner à l'arrivée de nouveaux messages.
- Le vote par morceau et le chat live suivent le patron polling+Redis (pas de WebSocket) — patron par défaut pour toute feature "partagée entre auditeurs".
- La playlist `JinglesFeature` reste gérée nativement côté AzuraCast, hors pipeline Python.
- **Session 2026-07-20** : ajout de `api/supporters.js` (webhook Buy Me a Coffee signé HMAC → remerciement auto dans le chat + panneau Supporters + notif Telegram), extension massive de `api/telegram.js` (reply admin avec citation, gestion supporters manuelle, reset Top 5 par epoch, bandeau épinglé, /np /stats, suppression bibliothèque AzuraCast, `/ask` vers l'API Claude, badge visuel supporter dans le chat), plafond de vote 10/auditeur/morceau sur `api/reactions.js`, Vibe Streak (fidélité locale), reconnexion audio durcie, et deux itérations de réorganisation du layout desktop (sidebar qui scrolle en bloc, puis Top 5 sous Historique / Supporters mis en avant).
- **Ajout tardif (même session)** : `SupporterBadgeFeature` — un supporter marqué manuellement par l'admin (`/mark_supporter <clientId> <nom>`, même patron que `/ban`) voit son pseudo et sa couleur (`--accent-2`, nouvelle variable) distingués dans le chat live. Aucun lien automatique don↔clientId n'existe (pas de comptes) : rapprochement 100% manuel, cohérent avec le reste du modèle de modération du projet.
