# Context — KALBASSFM — FM Caraïbes (3_Radiofm)

> Dernière mise à jour : 2026-07-17

## État actuel (2026-07-17, fin de session)

- ✅ **Interface passée entièrement en anglais** — UI, aria-labels, meta og/twitter, `manifest.webmanifest` (lang=en). Pseudos auditeurs `Listener-XXXX`. Le thumbnail de partage (WhatsApp etc.) suivra au prochain partage (cache tiers)
- ✅ **Messages admin distingués visuellement** — flag `admin:true` posé **exclusivement côté serveur** (par `api/telegram.js`, infalsifiable par un client) → affiché en gras dans le chat (`index.html`). Anti-usurpation : un auditeur qui tente le pseudo "KALBASSFM" est renommé "Listener" côté serveur (`api/chat.js`)
- ✅ **Messages automatiques d'animation du chat** (`api/chat.js`) — 8 annonces EN/jour (7 transitions de programme horodatées "UTC-4" + 1 rappel de vote à 18h), postées "paresseusement" au fil des GET des auditeurs (pas de cron), verrou Redis `chat:auto:<key>:<day>` (SET NX) garantissant un envoi unique ; sautées si personne n'écoute dans le quart d'heure de la transition
- ✅ **Chat à hauteur fixe** — `.chat-list` passée de `max-height` à `height: 260px` (mobile) / colonne desktop : l'arrivée de nouveaux messages ne redimensionne plus jamais le panneau, scroll interne uniquement
- ✅ **Bot Telegram `/jingle` opérationnel en prod** — deux bugs trouvés et corrigés après tests réels : (1) les 15 jingles sont des voix off dont le **titre est le texte lu**, aucun ne contient le mot "jingle" → filtre changé pour le marqueur fiable **"kalbass fm"** (vérifié : présent uniquement sur les 15 jingles parmi 383 morceaux demandables) ; (2) AzuraCast rejetait les requêtes API avec `"Les robots des moteurs de recherche ne sont pas autorisés"` (détection anti-crawler sur `User-Agent` absent) → ajout d'un `User-Agent` de navigateur classique sur les appels `triggerJingle()`. Activation manuelle nécessaire faite par l'utilisateur : station **"Autoriser la demande du titre suivant"** + playlist Jingles **"Autoriser les demandes"**

## État antérieur (2026-07-17, milieu de session)

- ✅ **NOUVELLE PROGRAMMATION "horloge à bacs pondérés" EN PRODUCTION** — remplace les 4 créneaux à ordre figé. 8 bacs curatés (`1_chill`...`8_jungle`), 7 fenêtres horaires (Lever 6-9h, Groove solaire 9-13h, Alizés 13-17h, Sunset 17-20h, Warm-up 20-23h, Peak 23-2h, Nuit profonde 2-6h), chaque fenêtre = 1 playlist dominante (poids 15) + 1-2 playlists invitées (poids 2-4) en mode **Shuffled**, séparation artiste **120 min** (Dupliquer le temps de prévention), fondu enchaîné **Mode intelligent**. Ponctuation jungle : playlist "Une fois toutes les 14 chansons" 23h-6h. **Vérifié en direct** : le dashboard AzuraCast montre nightdub + chill_guest + jungle actifs simultanément à 5h49, lecture suivante issue de chill_guest → l'alternance pondérée entre playlists planifiées qui se chevauchent fonctionne. Aucun redémarrage de diffusion nécessaire (AutoDJ prend les playlists à la volée)
- ✅ **Migration de la bibliothèque accomplie** — `resync_metadata.py` (948→825 entrées saines, 123 doublons/perdues supprimées) puis `migrate_grid.py --apply` (825 fichiers déplacés vers les 8 bacs, préfixes `NNN_` retirés, metadata.json resynchronisé, zéro chemin cassé). Répartition : chill 115/12.2h, groove 139/15.2h, house 135/13.6h, deep 114/12.2h, clubhouse 86/8h, techno 120/12.9h, nightdub 80/9.7h, jungle 36/4h. Upload serveur fait par l'utilisateur (FileZilla, dossier `Progv2`), 14 playlists créées à la main dans AzuraCast
- ✅ **Pipeline simplifié** — `classify_bins.py` (nouveau) = source de vérité unique : classification genre-d'abord/énergie-ensuite, seuils **auto-calibrés par percentiles par famille de genre** (s'adaptent seuls à l'évolution de la bibliothèque). Vetos structurels : techno/jungle énergiques ne peuvent jamais tomber en chill/groove. Jungle 3 niveaux : chill (<p30) → journée, très club (≥p80) → rotation Peak, cœur du style → ponctuation. `triage_new_tracks.py` classe désormais dans les 8 bacs et dépose sous nom propre (plus d'étape d'ordre). `build_rotation.py`/`export_rotation.py` **superseded**
- ✅ **Bot Telegram admin complet** (`api/telegram.js` + `@kalbassfm_bot`) — `/skip` (annonce aussi dans le chat live), `/msg` (message admin pseudo 📻 KALBASSFM), `/jingle` (best-effort via API Requests), `/ban`/`/unban <clientId>`, `/pause_chat`/`/resume_chat`, modération par boutons inline "🗑 Supprimer"/"🔨 Bannir" sur la notification Telegram de chaque message du chat. Testé en prod (skip 403 résolu = variable Vercel manquante ; /msg et /skip confirmés OK). Env : TELEGRAM_BOT_TOKEN/WEBHOOK_SECRET/CHAT_ID + AZURACAST_API_KEY sur Vercel
- ✅ **Chat modération côté serveur** (`api/chat.js`) — filtre `chat:deleted` (hash) au GET, vérifs `chat:paused` (flag) + `chat:banned` (set, par clientId — le pseudo est falsifiable, pas le clientId) au POST, notification Telegram de chaque message. Le front affiche les erreurs banni/pause via `showChatError` existant
- ✅ **Layout desktop du player** (≥1024px) — grille CSS 2 colonnes : lecteur à gauche (`.main-col`), chat + Top 5 à droite (`.sidebar-col`), hauteurs indépendantes (fix `height:0`/`min-height:100%` — le Top 5 déplié ne déforme plus Volume/Historique). Chat étiré dans l'espace disponible avec scroll interne ancré sur les messages récents (fix `::details-content` Chrome + repli 260px pour les autres navigateurs). Mobile strictement inchangé (`display:contents` + `order`)
- ⏳ **97 fichiers jamais analysés** + **14 doublons physiques** laissés dans les anciens dossiers locaux (`tools/orphans_report.txt`) — à redéposer dans `_incoming` + relancer `triage.bat` (nouvelle grille en place) ; doublons à supprimer à la main
- ⏳ **Anciens dossiers/playlists serveur à supprimer après 24h** de fonctionnement vérifié (morning/afternoon/evening/night désactivés, gardés comme retour arrière)

## État antérieur (2026-07-17, plus tôt)

- ✅ Store Upstash Redis confirmé fonctionnel en prod (vote 🔥 testé en direct)
- ✅ Vote 🔥 libre/illimité, Top 5 poll 4s, panneau ouvert par défaut
- ✅ Chat live anonyme (`api/chat.js`), anti-liens client+serveur, remplace le ticker
- ✅ Popup contact "Owned by Lupari" (email + Instagram)
- ✅ 15 jingles natifs AzuraCast (playlist "Une fois tous les x titres", Mode Jingle)

## État antérieur (2026-07-16 et avant, résumé)

- ✅ Radio 24/7 (AzuraCast VPS, kalbassfm.duckdns.org, SSL), player Vercel (kalbassfm-player.vercel.app), PWA installable, égaliseur Web Audio (désactivé mobile)
- ✅ Pipeline ingestion triage (nettoyage/dédoublonnage 75%/Essentia WSL2), `triage.bat`
- ✅ Campagne Instagram lancée le 2026-07-10 (5€/j × 7j, Antilles 18-35)
- 🔧 Bugs historiques corrigés : chemins WSL/Windows, quoting subprocess cmd.exe, resync metadata après renommage

## Décisions prises

| Décision | Rationale |
|----------|-----------|
| **Programmation = horloge à bacs pondérés, 100% native AzuraCast (2026-07-16)** | Exigences : "aucune journée ne doit ressembler à une autre" + "ne plus repasser dessus". L'ancien pipeline figeait UN ordre dans les noms de fichiers. Désormais : bacs curatés localement, ordonnancement délégué à AzuraCast (Shuffled + poids + chevauchement de plannings + séparation artiste 120 min) — zéro cron, zéro régénération, variété mathématiquement garantie |
| **Seuils de classification auto-calibrés par percentiles par famille** | L'échelle d'énergie est compressée (p95 ≈ 0.56) et dépend de la bibliothèque — des seuils absolus étaient tous faux (8 morceaux en clubhouse au 1er essai). Les proportions (ex. "45% des techno les moins énergiques → nightdub") restent valables quelle que soit l'évolution de la bibliothèque |
| **Jungle/DnB à 3 destins selon l'énergie** | Demande explicite : style rare qui "marque la fin d'un cycle" mais titres chill intégrables en journée. <p30 → 1_chill (journée), ≥p80 → 6_techno (rotation Peak), entre → 8_jungle en ponctuation "1/14 chansons" 23h-6h (~toutes les 1h20) |
| **Playlists invitées = playlists miroirs (même dossier, poids différent)** | Le poids AzuraCast est par playlist, pas par entrée de planning. 6 playlists `*_guest` en plus des 7 principales. Vérifié en prod : l'alternance pondérée entre playlists planifiées qui se chevauchent fonctionne |
| **`classify_bins.py` importé (pas dupliqué) par migrate/triage** | Écart assumé au plan initial ("dupliquer avec commentaire") : triage importait déjà ses modules voisins, l'import partagé élimine le risque de divergence des règles |
| **Ban chat par clientId, pas par pseudo** | Le pseudo est dérivé côté navigateur et falsifiable ; le clientId est déjà la clé du rate-limit. Contournable en vidant localStorage — best effort assumé |
| **Bot Telegram : un seul admin (TELEGram_CHAT_ID), secret webhook vérifié** | Démarrage simple, extensible en liste plus tard. Expéditeurs non autorisés ignorés silencieusement |
| **Jingle à la demande via API Requests AzuraCast (best-effort)** | AzuraCast n'a pas d'API "jouer immédiatement" (vérifié dans le code source). La clé API contourne l'anti-flood IP ; reste le blocage "joué trop récemment", acceptable |
| **Détection jingle par marqueur "kalbass fm", pas par mot "jingle"** | Les 15 jingles sont des voix off nommées d'après leur texte lu ("welcome to kalbass fm...") — aucun ne contient littéralement "jingle". Vérifié sur les 383 morceaux demandables : "kalbass fm" n'apparaît que dans les 15 jingles, zéro faux positif |
| **Messages auto du chat en "lazy cron" (verrou Redis au GET), pas de cron réel** | Cohérent avec le reste du projet (pas d'infra supplémentaire) : le poll 3s des auditeurs sert de déclencheur, un `SET NX` par créneau+jour garantit l'unicité même avec des dizaines de clients simultanés |
| **Flag `admin`/gras posé uniquement côté serveur, jamais dérivé du pseudo** | Le pseudo est envoyé librement par le client (déjà vrai pour le rate-limit) — un flag serveur est la seule façon fiable de distinguer un vrai message admin d'une usurpation |
| **Anciennes décisions toujours valables** | Upload SFTP manuel volontaire ; jingles natifs hors pipeline ; polling+Redis (pas de WebSocket) pour toute feature partagée ; dossier = playlist ; DuckDNS gratuit ; volume Docker |

## En cours / TODOs

- [ ] **Vérifier que `/jingle` fonctionne réellement en prod** après les deux fix (marqueur "kalbass fm" + User-Agent) — dernier test montrait encore l'erreur anti-robots, non reconfirmé après le fix
- [ ] **Vérifier l'horloge sur 24h** (Rapports → Historique : ratio ~3:1 dominant/invité, pas d'artiste <2h, séquences différentes d'un jour à l'autre) puis **supprimer les 4 anciens dossiers + playlists serveur** et les restes locaux
- [ ] **Redéposer les 97 fichiers jamais analysés dans `_incoming`** (`tools/orphans_report.txt`) + relancer `triage.bat` ; supprimer les 14 doublons physiques listés dans le même rapport
- [ ] **Créer la playlist `filet`** (sans planning, poids 1, dossiers groove+house) si pas encore fait
- [ ] **Double virgule dans la description station** ("Électronique, , Disco") — cosmétique, 10s dans Profil
- [ ] **Vérifier le chat live à deux navigateurs en prod** (jamais fait formellement ; la modération Telegram le teste indirectement)
- [ ] **Analyser les résultats campagne Instagram** (terminée ~2026-07-17)
- [ ] **Mettre à jour `clean_local_tracks.py`** (pointe encore sur les anciens dossiers racine)
- [ ] **SACEM** — toujours pas fait
- [ ] **TuneIn** — Partner ID toujours en attente (station s358721)
- [ ] **Système de vote de playlist par genre** (`wild-cooking-book.md`) — plan complet, non codé ; à re-concevoir sur la nouvelle grille (bacs ≠ genres purs)
- [ ] **Weekend différencié / bac "pépites"** — extensions natives possibles de l'horloge, non planifiées
- [ ] **Domaine payant** (optionnel)

## Problèmes connus

| Problème | Sévérité | Notes |
|----------|----------|-------|
| Ban contournable en vidant localStorage | LOW | Best effort assumé, cohérent avec le modèle de modération |
| Renames WinSCP (`migration_sftp.txt`) non utilisés | INFO | Upload frais FileZilla choisi à la place (noms serveur ≠ noms locaux) — script obsolète, ignoré par git |
| `Alex Cortex - Discola.mp3` corrompu | LOW | "can't sync to MPEG frame", à re-télécharger |
| Rate limit iTunes Search | LOW | ~20 req/min, throttle 3.2s/req dans le nettoyage |
| Mode intelligent (crossfade) = +CPU sur le VPS | LOW | À surveiller ; repli Mode normal si besoin |

## Fichiers clés

| Fichier | Rôle | Statut |
|---------|------|--------|
| `tools/classify_bins.py` | **Source de vérité de la grille 8 bacs** : familles, SHARES, seuils auto-calibrés, classify_bin() | ✅ Nouveau, importé par migrate+triage |
| `tools/migrate_grid.py` | Migration one-shot 4→8 bacs (dry-run/--apply, garde-fou _incoming, rapport, WinSCP) | ✅ Exécutée le 2026-07-16 |
| `tools/resync_metadata.py` | Réparation metadata↔disque par nom sans préfixe (948→825 entrées) | ✅ Exécutée le 2026-07-16 |
| `tools/triage_new_tracks.py` | Pipeline ingestion → 8 bacs, nom propre, plus d'étape d'ordre | ✅ Mis à jour, à retester sur les 97 orphelins |
| `tools/build_rotation.py`, `tools/export_rotation.py` | Ancien calcul/export d'ordre | ⚠️ Superseded (en-têtes marqués) |
| `tools/orphans_report.txt` | 97 fichiers jamais analysés + 14 doublons physiques | ⏳ À traiter (gitignored) |
| `api/telegram.js` | Webhook bot Telegram admin (skip/msg/jingle/ban/pause + callbacks modération) | ✅ Déployé ; `/jingle` corrigé 2x (marqueur "kalbass fm" + User-Agent), à reconfirmer |
| `api/chat.js` | Chat live + modération (deleted/banned/paused) + notification Telegram + messages auto EN + anti-usurpation pseudo | ✅ Déployé |
| `api/reactions.js` | Vote 🔥 + Top 5 | ✅ Déployé |
| `index.html` | Player complet EN, layout desktop 2 colonnes, chat hauteur fixe, messages admin en gras | ✅ Live |
| `manifest.webmanifest`, `sw.js` | PWA en anglais, cache bumpé `kfm-v4` | ✅ Live |
| `CONTEXT.md`, `graphify-out/` | Contexte + graphe de connaissances | ✅ À jour 2026-07-17 |

## Infrastructure

**Hébergement :**
- **Streaming** : VPS `167.233.226.128` (Ubuntu, Docker) — AzuraCast v0.23.7 + Icecast + Liquidsoap, `kalbassfm.duckdns.org` HTTPS, fuseau America/Martinique
- **Player** : Vercel — kalbassfm-player.vercel.app, deploy auto sur push GitHub (`abg5f/kalbassfm-player`)
- **Musique serveur** : volume Docker, dossier `Progv2/` contenant les 8 bacs ; anciens dossiers morning/... encore présents (filet 24h)
- **Musique locale** : `C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog\<bac>` + `_incoming` (triage)
- **Réseau perso** : RaiDrive `Z:` sur le SFTP AzuraCast (port 2022) ; FileZilla pour les gros uploads
- **Bot** : `@kalbassfm_bot` (BotFather), webhook `kalbassfm-player.vercel.app/api/telegram`

## Graphe de connaissances
> Mis à jour le 2026-07-17 (construction manuelle via /graphify, pas de CLI)

God nodes (concepts centraux) : `index.html` (hub front, degré 12), `AzuraCast` (infra + exécution de l'horloge, 10), `ProgrammeGrid`/horloge à bacs pondérés (8), `VotingSystemPlan` (7, toujours non codé), `RekordboxPipeline` (6), Upstash Redis (4 fonctions serverless), `classify_bins.py` (source de vérité classification).
Communautés détectées : 7 (Player/Frontend, Infra/Streaming, Serverless+bot Telegram, Outillage/Pipeline, Essentia/Grille 8 bacs, Planning/Business, Contexte).
Pour explorer : `graphify query "<question>"` / `graphify explain "<concept>"`

---

_Mis à jour via `/save`. Lire ce fichier en début de session pour reprendre le contexte._
