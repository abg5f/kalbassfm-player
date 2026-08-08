# KALBASSFM — Graphe de connaissances

> Généré le 2026-07-09, mis à jour le 2026-07-16, 2026-07-17, le 2026-07-20 (3 fois), le 2026-07-21 (3 fois), le 2026-07-24 (2 fois) le 2026-07-28 puis le 2026-08-08 via `/graphify` (codebase complet : player, serverless, outillage, docs de planification).

## Vue d'ensemble

- **74 nœuds**, **148 relations**, **8 communautés** détectées.
- Le graphe couvre : le player web (`index.html`, layout desktop réorganisé, Top 5 retiré), les fonctions serverless (`api/chat.js`, `api/telegram.js`, `api/supporters.js`, `api/flappy.js` — chat live/bot admin/dons/mini-jeux, Upstash Redis), le **jeu "devine le BPM" intégré au chat** (`BpmGuesserFeature`, table `api/bpm-table.json` générée par `tools/export_bpm_table.py`), le **pseudo persistant choisi par l'auditeur** (`ChatNicknameFeature`, hash `chat:pseudos`), la **commande Telegram `/move`** pour migrer le morceau en cours entre les 8 bacs (`MoveTrackFeature`, 2026-07-24), la sauvegarde locale de titres likés (`MyTracksFeature`, 2026-07-24) et la popup de découverte des features (`WhatsNewModal`, 2026-07-24), l'**horloge à bacs pondérés** (8 bacs, `classify_bins.py`), le pipeline d'ingestion (avec file de retry SFTP), la playlist Jingles native AzuraCast, la PWA, l'infra (AzuraCast/Icecast/Liquidsoap/VPS/Vercel/DuckDNS), les intégrations externes (Buy Me a Coffee, API Claude), les documents `.planning/`, l'**incident de quota Upstash** du 2026-07-21 et sa résolution, le plan (non codé) du système de vote de playlist par genre, et l'**émission mensuelle Mixtapes** (`MixtapesFeature`, `tools/publish_mixtape.py`, podcast AzuraCast natif + playlist `mixtape_onair`, 2026-08-08).

## Communautés

| Communauté | Membres clés |
|---|---|
| Player / Frontend | index.html, layout desktop, sw.js, manifest, PWA, égaliseur, chat live, popup contact, now-playing, Supporters, Vibe Streak, bandeau épinglé, Request, Flappy Kalbass, My tracks, popup What's new, **panneau Mixtapes + élément audio dédié** |
| Infra / Streaming | AzuraCast, Icecast, Liquidsoap, VPS, DuckDNS, GitHub, Vercel, Admin API, playlist Jingles, **podcast KALBASSFM Mixtapes, playlist mixtape_onair, duplication du média podcast** |
| Serverless / API (chat + bot Telegram admin + Flappy + BPM) | api/chat.js, api/telegram.js, api/supporters.js, api/flappy.js, Upstash Redis, chat live, bot admin, réponse admin, badge supporter, renommage modérateur, pseudo choisi par l'auditeur, jeu BPM, commande /move (migration entre bacs), incident quota Upstash, vote playlist (planifié) |
| Intégrations externes (dons, IA) | Buy Me a Coffee, API Claude, api/supporters.js |
| Outillage / Pipeline musique | pipeline Rekordbox, import-rekordbox.ps1, clean_local_tracks.py, RaiDrive, iTunes Search API, triage (file de retry SFTP), export_bpm_table.py, migrations, **publish_mixtape.py** |
| Pipeline Essentia / Grille 8 bacs | analyze_essentia.py, classify_bins.py, migrate_grid.py, resync_metadata.py, build_rotation.py (superseded) |
| Planning / Business | PROJECT.md, ROADMAP.md, PLAN.md, REQUIREMENTS.md, EXECUTION_CHECKLIST.md, STATE.md, SACEM |
| Contexte de session | CONTEXT.md, README.md |

## God nodes (les plus connectés)

1. **index.html** (degré 20) — hub de toutes les features front (now-playing, chat live, layout desktop, Supporters, Vibe Streak, bandeau épinglé, Request, Flappy Kalbass, pseudo persistant, **My tracks**, **popup What's new**, PWA). Se détache encore avec le panneau Mixtapes (2026-08-08), également 100 % client.
2. **ChatFeature** (degré 13) — panneau chat live, cible de la plupart des features de modération, du jeu BPM, du choix de pseudo et désormais des commandes locales `!save`/`!saved`/`!help`.
3. **api/chat.js** (degré 12) — chat live + modération + renommage (admin et auditeur) + jeu BPM (BpmGuesserFeature) + annonce Flappy + détection d'erreur Upstash.
4. **api/telegram.js** (degré 13) — bot admin, toutes les commandes (reply, supporters, renommage modérateur, bandeau épinglé + auto-pin pause, /ask Claude, suppression bibliothèque, **/move** de migration entre bacs), résilience handleCallback, kill-switch Redis.
5. **AzuraCast** (degré 12) — cœur de l'infra streaming ET de la programmation (l'horloge est exécutée par ses playlists Shuffled + poids).
6. **ProgrammeGrid / Horloge à bacs pondérés** (degré 11) — grille 8 bacs, remplace les 4 créneaux à ordre figé.
7. **tools/classify_bins.py** — source de vérité unique de la classification (seuils auto-calibrés par percentiles).

## Note — 2026-07-21 : incident de quota Upstash et suppression du Top 5

Le plan gratuit Upstash (500k commandes/mois) a été épuisé plusieurs fois : le polling front (chat, Top 5, supporters) représentait ~99% des commandes (lectures), contre ~1% pour les écritures admin. Symptômes en prod : chat/Top 5/supporters clignotant vers un état vide (une erreur Upstash était traitée silencieusement comme une liste vide) et boutons de suppression Telegram sans effet visible. Résolution en plusieurs étapes : espacement du polling, détection explicite des erreurs Upstash, coupure temporaire complète (`REDIS_PAUSED`) le temps de la réflexion, **suppression définitive du Top 5/vote** (`api/reactions.js`, plus gros consommateur), puis passage d'Upstash en Pay As You Go — `REDIS_PAUSED` repassé à `false`. Voir le nœud `RedisQuotaIncident` pour le détail.

## Note — 2026-07-21 (suite) : jeu "devine le BPM" et incident de prod associé

Le BPM n'existe pas dans les métadonnées exposées par l'API AzuraCast (`custom_fields` vide, vérifié en direct). `tools/export_bpm_table.py` lit les tags ID3 réels (mutagen) pour associer le BPM déjà calculé par Essentia à l'artiste+titre exact qu'AzuraCast affiche → `api/bpm-table.json` (749/825 morceaux). `api/chat.js` matche le morceau en cours contre cette table dès qu'un message ressemble à un guess numérique, et répond via le pseudo réservé `BPM GUESSER` (vert fluo). Le déploiement a d'abord cassé `/api/chat` en prod (500, chat invisible pour tous) à cause d'un chargement JSON via `fs.readFileSync(import.meta.url)` qui ne s'est pas comporté comme attendu une fois la fonction empaquetée par Vercel — corrigé par un import JSON statique avec assertion (`with { type: 'json' }`), vérifié cette fois par chargement réel du module en local (pas seulement `node --check`).

## Note — 2026-07-21 (suite) : pseudo persistant fusionné depuis une branche externe

Branche `claude/chat-persistent-user-id-7iol95` (créée après le dernier commit de `main`, fusionnée sans conflit) : bouton "Set nickname" au-dessus du chat, pseudo choisi par l'auditeur stocké dans le hash Redis `chat:pseudos` (clientId → pseudo) et en miroir `localStorage`. Coexiste avec `ChatRenameFeature` (modération admin) : priorité finale = badge supporter > renommage forcé par l'admin > pseudo choisi par l'auditeur > `Listener-XXXX` par défaut. Voir le nœud `ChatNicknameFeature`.

## Note — 2026-07-24 : commande /move (migration de morceau entre bacs)

Fusionnée dans `main` depuis la branche `claude/telegram-move-music-playlists-11xd5s` (déjà mergée à l'arrivée sur cette session, récupérée par un simple `git pull`). `/move` récupère le morceau en cours de lecture (now-playing) et affiche les 8 bacs de `ProgrammeGrid` sous forme de boutons Telegram ; un clic migre le fichier et affiche le chemin source/destination pour le sync manuel FileZilla — cohérent avec le choix déjà établi d'upload SFTP manuel volontaire (pas d'automatisation du transfert serveur). Simplifiée le même jour d'un flux en deux étapes (`/move_track <recherche>`) vers un flux en une commande partant directement du morceau courant. Voir le nœud `MoveTrackFeature`.

## Note — 2026-07-24 (suite) : « My tracks » et popup What's new

Demande récurrente des auditeurs : garder une trace des morceaux aimés. La contrainte décisive a été le **coût Upstash** (cf. l'incident du 2026-07-21 ci-dessus) : un stockage serveur indexé par `clientId` ne survivrait pas mieux à un vidage du cache — puisque le `clientId` **est** dans `localStorage` — tout en coûtant des commandes Redis à chaque like et à chaque lecture. D'où un choix **100 % local**, même patron que `VibeStreakFeature` : chip `♡ Save`, panneau `My tracks` groupé par jour, et surtout un **export texte (Copy / .txt)** qui devient la vraie fonction de récupération puisqu'il n'y a pas de sync multi-appareils. Les commandes chat `!save`/`!saved`/`!help` sont interceptées **avant** le `fetch` : elles ne sont jamais postées, donc zéro écriture Redis et zéro notification Telegram — vérifié en local (aucun POST au journal réseau, alors qu'un message normal en produit toujours un). Voir `MyTracksFeature` et `WhatsNewModal`.

## Note — 2026-07-28 : le bac du matin se remplissait au niveau de mastering

Découverte à l'écoute, et la plus structurante de la session. L'axe d'énergie est
`0.5*rms + 0.3*bpm + 0.2*party`, **or le RMS mesure le niveau de mastering autant que
l'énergie musicale**. Une règle en percentile d'énergie remplit donc son bac avec les titres
*mixés bas*, pas avec les titres calmes : **62 des 118 titres de `1_chill` étaient à ≥120 BPM**
(un garage house à 126 BPM diffusé à 7h du matin). Deux garde-fous indépendants du RMS ont été
ajoutés dans `classify_bins.py` — veto de tempo pour house/genres inconnus (avec une bande
120-145 pour les fausses étiquettes « ambient »), et sélection du bac matin par percentile de
`mood.aggressive` pour jungle/DnB, où le BPM est inutilisable (demi-tempo : 86 pour 172).
L'ancienne règle retenait la jungle old-school mixée bas et laissait le vrai liquid DnB en
ponctuation nocturne, alors que c'est la matière « matin/travail » recherchée. 120 fichiers
reclassés. Voir `EnergyRmsLimitation`.

Corollaire trouvé le même jour sur le jeu BPM : la même erreur de demi-tempo faisait répondre
« faux » à un auditeur annonçant le vrai tempo d'un morceau de DnB. Voir `BpmGuesserFeature`.

## Note — 2026-07-28 (suite) : 82 titres retrouvés et audience réelle

`LibraryRecovery` — 82 morceaux dormaient sur le serveur dans les anciens dossiers depuis
juillet, jamais migrés et référencés par aucune playlist, donc **jamais diffusés**. Rapatriés
puis arbitrés par le détecteur de doublons du pipeline, qui n'en a écarté aucun. Bibliothèque
913 → 995 entrées. `migrate_grid.py` a été rendu ré-exécutable au passage : il renommait en
`Titre_2.mp3` les ~700 fichiers ne changeant pas de bac.

`AudienceStatsFeature` — la commande `/audience` mesure enfin l'audience réelle : **0,26
auditeur de moyenne sur 24h, 0,46 sur 30 jours, pic à 6**. Ce n'est pas un défaut de mesure,
c'est l'état de la station. La géographie mensuelle demandée est impossible : l'instance est en
`analytics = 'no_ip'`, donc aucun enregistrement par auditeur n'est conservé et les rapports
`by-country` / `charts` sont bloqués ou vides. Seuls les auditeurs connectés à l'instant sont
localisables.

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

## Note — 2026-08-08 : émission mensuelle « Mixtapes »

Premier rendez-vous éditorial du projet : une mixtape mixée diffusée à date fixe à l'antenne, puis réécoutable à la demande et suivable en RSS. C'est une réponse au constat du 2026-07-28 (0,46 auditeur sur 30 jours) — la technique est saine, c'est la diffusion et l'accroche qui manquent, et un flux live n'est pas partageable alors qu'un épisode l'est.

**Deux stockages, imposés par l'API.** `playlist_media_id` est en **lecture seule** côté AzuraCast (`must be one of "never"`) : un épisode ne peut pas *référencer* un média déjà dans la bibliothèque station. La voie qui aurait évité toute duplication (`source: playlist` + `playlist_auto_publish`, alimentée par une playlist d'archive qui ne fait que grandir) a été testée et ne génère **aucun** épisode sur cette instance, playlist désactivée comme activée — et supprimer la playlist source **supprime le podcast avec elle**. `source` et `playlist_id` sont par ailleurs immuables après création. Chaque mixtape existe donc en deux exemplaires (~100 Mo, ~1,2 Go/an). Voir `PodcastMediaDuplication`.

**Deux éléments `<audio>`, imposés par le player.** `#audio` est auto-réparant (listeners `pause`/`error`/`visibilitychange` + watchdog `setInterval` qui relancent le flux). Le réutiliser ferait écraser la mixtape par le direct en pleine lecture. `#podcastAudio` est donc un élément séparé, et lancer une mixtape appelle `stopStream()` — qui pose `userStopped = true` et neutralise le watchdog. Vérifié en conditions réelles : direct coupé au lancement, toujours coupé 6 s plus tard. Voir `PodcastAudioElement`.

**Côté auditeur, zéro coût serveur.** Le panneau lit les endpoints *publics* d'AzuraCast (`/public/podcasts`, `/public/podcast/{id}/episodes`) : aucun fichier `api/`, zéro commande Redis, zéro invocation de fonction Vercel — le même arbitrage que `MyTracksFeature`. Le panneau se masque de lui-même tant qu'aucun épisode n'est publié.
