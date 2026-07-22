# Context — KALBASSFM — FM Caraïbes (3_Radiofm)

> Dernière mise à jour : 2026-07-21

## État actuel (2026-07-21, fin de session)

- ✅ **Incident de quota Upstash résolu** — le plan gratuit (500k commandes/mois) a été épuisé plusieurs fois de suite : ~99% des commandes étaient des lectures du polling front (chat/Top 5/supporters), pas des écritures admin. Symptômes en prod : chat/Top 5/supporters clignotant vers un état vide (`lj.result` manquant = erreur Upstash, traité à tort comme une liste vide), boutons de suppression Telegram sans effet visible (l'échec Redis interrompait `handleCallback` avant `answerCallback`). Corrigé par étapes : espacement du polling (chat 3s→6s, Top 5 4s→8s, supporters 30s→45s), détection explicite des erreurs Upstash (`result === undefined` → throw), coupure complète temporaire (`REDIS_PAUSED=true` dans `api/chat.js`/`api/reactions.js`/`api/supporters.js`/`api/telegram.js` via `kvClient()`) le temps de la réflexion, puis (depuis une autre session/remote) **suppression définitive du Top 5/vote** (`api/reactions.js` retiré du repo — plus gros consommateur) et **passage d'Upstash en Pay As You Go** → `REDIS_PAUSED` repassé à `false`, Redis réactivé partout
- ✅ **Nouveau mini-jeu Flappy Kalbass** (`api/flappy.js` + popup canvas dans `index.html`, icône oiseau dans le header) — classement global des scores via Redis, décompte 3-2-1 au lancement, vitesse ralentie. Lancement annoncé une seule fois dans le chat live (verrou `SET NX` sans expiration sur `chat:announced:flappy`, `api/chat.js`)
- ✅ **Renommage modérateur du pseudo chat** — `/rename <clientId> <pseudo>` / `/unrename` (hash `chat:nicknames`, même patron server-only que `admin:true`/`supporter:true`) impose un pseudo sans badge supporter, priorité : supporter > rename > pseudo client. Réécrit aussi l'historique déjà posté (`renameHistory`, `LSET` protégé par vérification `LINDEX` contre les `LPUSH` concurrents d'autres auditeurs). `/rename_nick <ancien pseudo exact> <nouveau>` rattrape les messages postés avant que le `clientId` ne soit stocké sur chaque message (limitation initiale, corrigée depuis). `stripAngles()` tolère les chevrons `<...>` collés à la lettre depuis les messages d'usage (bug réel observé : un admin qui copie l'exemple littéralement enregistrait sous une clé `<...>` qui ne matchait jamais rien, échec 100% silencieux)
- ✅ **`/pause_chat` épingle un bandeau d'avertissement** — sauvegarde l'annonce `/pin` existante (`chat:pinned:backup`) et la restaure à `/resume_chat` au lieu de la perdre
- ✅ **Pseudo admin coloré en orange** (`--accent-2`) dans le chat, pour se distinguer visuellement des auditeurs
- ✅ **`handleCallback` (bot Telegram) toujours résilient** — toute la logique est enveloppée dans un try/catch qui répond systématiquement au tap Telegram (message d'échec explicite), même si Redis échoue en cours de route — avant ce fix, un tap pouvait rester sans aucune réaction visible
- ✅ **Top 5 replié par défaut** (avant sa suppression complète), header épuré

## État antérieur (2026-07-20, fin de session)

- ✅ **Badge visuel supporter dans le chat live** — `/mark_supporter <clientId> <nom>`/`/unmark_supporter` (nouveau, `api/telegram.js`) lient un `clientId` à un nom de supporter dans un hash Redis `chat:supporters`, même patron que `/ban`/`chat:banned`. Aucun lien automatique don↔clientId n'existe (checkout entièrement sur BMC, pas de comptes) : le rapprochement est manuel, fait par l'admin quand le supporter se manifeste dans le chat (son `clientId` est déjà visible dans chaque notification Telegram). `api/chat.js` surclasse alors le pseudo + pose `supporter:true` côté serveur uniquement (même principe que `admin:true`, jamais dérivé du pseudo envoyé par le client). Front : nouvelle couleur `--accent-2` (ambre) pour distinguer visuellement les supporters de l'accent jaune déjà très utilisé partout. Testé de bout en bout (vrai round-trip POST→GET contre un faux Redis)
- ✅ **Bot Telegram admin très étendu** (`api/telegram.js`) — nouvelles commandes : réponse native (Reply Telegram ou bouton dédié) postée dans le chat live sous le pseudo admin **avec citation** du message d'origine (mapping `chat:tgmap` dans `api/chat.js`, TTL 3j) ; `/recent` et `/recent_supporters` (suppression rétroactive avec boutons 🗑) ; `/add_supporter` (ajout manuel, ex. don reçu avant le webhook) ; `/reset_top5` (reset instantané via compteur d'epoch) ; `/pin`/`/unpin` (bandeau d'annonce épinglée) ; `/np`/`/stats` ; `/delete_track`/`/delete_current_track` (suppression bibliothèque AzuraCast, recherche progressive titre→artiste→phrase — corrige un vrai bug où AzuraCast ne matche pas une phrase combinée) ; `/ask` (brainstorm via l'API Claude, HTTP brut, `claude-opus-4-8`, nécessite `ANTHROPIC_API_KEY`)
- ✅ **Webhook Buy Me a Coffee opérationnel** (`api/supporters.js`, nouveau) — signature HMAC-SHA256 vérifiée sur le corps brut, remerciement auto dans le chat live + panneau **Supporters ☕** + notif Telegram à chaque don réel. Events de test BMC (`live_mode:false`) étiquetés `🧪 [TEST]` pour ne pas induire les auditeurs en erreur. Testé de bout en bout avec le bouton "Send test event" de BMC
- ✅ **Plafond de vote 🔥 durci** (`api/reactions.js`) — 10 votes max par `clientId` et par morceau (`clientId` désormais **obligatoire**, faille de contournement par ancien front en cache fermée), plus blocage visuel côté front (shake + toast) dès que le quota de l'auditeur est atteint. Reset du classement via compteur d'epoch (`/reset_top5`), réutilisable à volonté sans lister/supprimer de clés Redis
- ✅ **Vibe Streak** — fidélité gamifiée 100% locale (`localStorage`, zéro serveur). Le déclencheur initial (60s d'écoute strictement ininterrompue) ne se déclenchait quasiment jamais en usage mobile réel (micro-coupures : verrouillage d'écran, throttling) → remplacé par un cumul tolérant qui met juste le compteur en pause au lieu de le remettre à zéro
- ✅ **Reconnexion audio durcie** (`index.html`) — sur erreur dure, backoff exponentiel (1s→8s) + cache-bust de l'URL du flux au lieu de rester bloqué sur "error"
- ✅ **Layout desktop réorganisé (3 itérations)** — (1) la colonne latérale scrolle d'abord comme un bloc (`overflow-y:auto`) au lieu de faire jongler les hauteurs des panneaux via flex-grow/shrink, fragile dès que 3+ panneaux sont ouverts (chevauchement observé en prod) ; (2) **Top 5 déplacé sous Historique** dans la colonne principale, **Supporters mis en avant** (ouvert par défaut, juste sous le Chat) ; (3) le scroll de bloc laissait un grand vide sous Chat/Supporters (contenu cumulé plus court que la colonne principale) → remplacé par **Chat qui s'étire en flex** pour combler tout l'espace vertical restant (Supporters garde sa hauteur naturelle, plafonnée à 240px + scroll interne en garde-fou). A nécessité de contourner un piège Chrome : le pseudo-élément `::details-content` (anime l'ouverture des `<details>`) est `display:block` par défaut et casse la chaîne flex même quand `.panel-body` a `flex:1`
- ✅ **Petites features chat** : bandeau d'annonce épinglée (`/pin`), bouton **Request** (dédicace → Telegram), indicateur **Vibe now/next** (ambiance du créneau horaire courant)

## État antérieur (2026-07-17, fin de session)

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
| **Badge supporter lié au clientId, rapprochement manuel par l'admin (2026-07-20)** | Aucun lien automatique don BMC↔session de chat n'est possible (pas de comptes, checkout entièrement sur le site de BMC). Même patron que `/ban` : l'admin pose le lien via `/mark_supporter` quand le supporter se manifeste dans le chat, jamais dérivé du pseudo client — cohérent avec le principe déjà établi pour `admin:true` |
| **Anciennes décisions toujours valables** | Upload SFTP manuel volontaire ; jingles natifs hors pipeline ; polling+Redis (pas de WebSocket) pour toute feature partagée ; dossier = playlist ; DuckDNS gratuit ; volume Docker |
| **Reset Top 5 via compteur d'epoch Redis, pas de suppression de clés (2026-07-20)** | Incrémenter `top5:epoch` "vide" instantanément le leaderboard ET les plafonds de vote par auditeur (les clés sont scopées par epoch) sans lister/supprimer quoi que ce soit — réutilisable à volonté par `/reset_top5` |
| **clientId obligatoire pour voter, requête rejetée sinon (2026-07-20)** | Le plafond de 10 votes n'était appliqué que si `clientId` était présent — un ancien front en cache (avant l'ajout du plafond) pouvait donc voter sans limite. Rejeter les votes sans `clientId` ferme cette faille quelle que soit la version du client qui appelle l'API |
| **Vibe Streak : cumul tolérant plutôt que chronomètre strict (2026-07-20)** | La première version exigeait 60s d'écoute strictement ininterrompues — les micro-coupures mobiles (écran verrouillé, throttling) remettaient tout à zéro avant d'atteindre le seuil, donc le streak ne se déclenchait presque jamais en usage réel. Le cumul met juste le compteur en pause au lieu de le réinitialiser |
| **Top 5 sous Historique, Supporters mis en avant (2026-07-20)** | Top 5/Historique = même thème (lecture/popularité) ; Chat/Supporters = vie communautaire. Les supporters sont des contributeurs financiers réels — les rendre visibles sans scroll était explicitement demandé |
| **Événements de test BMC (`live_mode:false`) étiquetés, jamais traités comme réels (2026-07-20)** | Le bouton "Send test event" de BMC Studio envoie un vrai payload webhook — sans ce garde-fou, cliquer sur "test" aurait posté un faux remerciement dans le chat live sous les yeux des vrais auditeurs |
| **~~Sidebar desktop scrolle comme un bloc~~ → Chat seul flex-grow, Supporters plafonné (2026-07-20, révisé même jour)** | Le scroll de bloc (retenu plus tôt dans la session) laissait un grand vide visuel sous Chat/Supporters quand leur contenu cumulé était plus court que la colonne principale — repéré sur capture d'écran par l'utilisateur. Solution finale : seul `#chatPanel` devient flexible (`flex:1`) pour absorber l'espace restant, `#supportersList` reçoit un plafond dur (`max-height:240px` + scroll interne) en garde-fou puisqu'il n'a pas de limite côté serveur (jusqu'à 20 entrées, `api/supporters.js`) |
| **Contournement `::details-content` (Chrome) pour la sidebar flex (2026-07-20)** | Chrome enveloppe automatiquement le contenu d'un `<details>` ouvert dans un pseudo-élément `::details-content` (pour l'animation d'ouverture), `display:block` par défaut — casse silencieusement toute chaîne `flex:1` en aval même si les enfants directs sont bien configurés. Il faut le cibler explicitement (`#chatPanel[open]::details-content { display:flex; ... }`) à chaque fois qu'un `<details>` doit participer à un layout flex/grid |
| **Top 5/vote supprimé entièrement plutôt qu'optimisé (2026-07-21)** | Après l'incident de quota Upstash, le Top 5 s'est avéré être le plus gros consommateur de commandes Redis (poll 4-8s + jusqu'à 6 commandes par poll : `zrange` + un `hgetall` par morceau) pour une feature "peu utilisée" — retiré plutôt que d'investir dans son optimisation |
| **`REDIS_PAUSED` comme kill-switch de code plutôt que retirer les variables d'env Vercel (2026-07-21)** | Pas d'accès direct au dashboard Vercel depuis Claude Code — un flag booléen en tête de chaque fichier (`api/chat.js`, `api/reactions.js`, `api/supporters.js`, `api/telegram.js` via `kvClient()`) réutilise les garde-fous "store non configuré" déjà présents partout, réversible en une ligne, pas de risque de casser une variable d'env par erreur |
| **Rename par clientId (`/rename`) + rattrapage par pseudo affiché (`/rename_nick`) comme deux commandes distinctes (2026-07-21)** | Les messages postés avant l'ajout du `clientId` sur chaque entrée `chat:messages` ne peuvent pas être retrouvés par `/rename` (clé absente). `/rename_nick` matche sur le pseudo littéralement affiché (`Listener-XXXX`), pas garanti unique entre auditeurs contrairement au clientId — feature de rattrapage explicitement "à manier avec discernement", pas le mécanisme par défaut |
| **`renameHistory`/`renameHistoryByNick` vérifient `LINDEX` avant chaque `LSET` (2026-07-21)** | `chat:messages` reçoit des `LPUSH` concurrents d'autres auditeurs pendant qu'une commande de rename boucle sur un snapshot `LRANGE` figé — sans vérification, un `LSET` par index périmé pouvait écraser le message d'un autre auditeur. Une entrée décalée est sautée plutôt que corrompue ; la commande est idempotente donc la relancer rattrape ce qui a été sauté |
| **Annonce de lancement de feature en verrou `SET NX` sans expiration, distincte des annonces horaires quotidiennes (2026-07-21)** | Le mécanisme existant (`ANNOUNCEMENTS`) est conçu pour se répéter chaque jour à heure fixe — un lancement de feature (Flappy Kalbass) ne doit partir qu'une seule fois, jamais répété : verrou permanent (`chat:announced:flappy`, pas de `EX`) plutôt qu'un verrou quotidien |

## En cours / TODOs

- [ ] **Configurer le webhook Buy Me a Coffee** si pas déjà fait après cette session : BMC Studio → Integrations → Webhooks → URL `https://kalbassfm-player.vercel.app/api/supporters`, événement "Support created" uniquement, copier le secret dans `BMC_WEBHOOK_SECRET` sur Vercel
- [ ] **Ajouter `ANTHROPIC_API_KEY` sur Vercel** pour que `/ask` fonctionne (clé à créer sur console.anthropic.com)
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
- [ ] **Retirer « ID (#04) »** (`Progv2/4_deep/29. ID - ID (#04).mp3`) — probable extrait de DJ set trance mal étiqueté (tags "ID"/"ID", pochette reprenant visuellement un épisode ASOT), pas un vrai morceau. `/delete_current_track` désormais disponible pour ça une fois le morceau relancé
- [ ] **Faire entrer « Arachnida » (Veuskemini) dans le pipeline** — jamais passé par `classify_bins.py`/`triage_new_tracks.py` (probablement uploadé directement sur le serveur), donc mal classé (son genre — expérimental/IDM — ne correspond pas au créneau où il tournait). Le localiser sur le serveur, le rapatrier dans `_incoming`, relancer `triage.bat`
- [ ] **Repérer d'autres morceaux uploadés hors pipeline** — le cas Arachnida suggère qu'il en existe potentiellement d'autres en plus des 97 déjà connus dans `orphans_report.txt`. Un script de rapprochement serveur↔local (comparer la liste AzuraCast à `metadata.json`) permettrait de tous les repérer d'un coup
- [ ] **Surveiller la facture Upstash Pay As You Go** les premières semaines pour valider que le volume de commandes reste raisonnable après suppression du Top 5 (2026-07-21)
- [ ] **Vérifier qu'aucun don Buy Me a Coffee n'a été perdu** pendant la fenêtre `REDIS_PAUSED` (2026-07-21) — le webhook répondait 200 à BMC (pour ne pas se faire désactiver) mais n'enregistrait rien côté Redis

## Problèmes connus

| Problème | Sévérité | Notes |
|----------|----------|-------|
| Ban contournable en vidant localStorage | LOW | Best effort assumé, cohérent avec le modèle de modération |
| Renames WinSCP (`migration_sftp.txt`) non utilisés | INFO | Upload frais FileZilla choisi à la place (noms serveur ≠ noms locaux) — script obsolète, ignoré par git |
| `Alex Cortex - Discola.mp3` corrompu | LOW | "can't sync to MPEG frame", à re-télécharger |
| Rate limit iTunes Search | LOW | ~20 req/min, throttle 3.2s/req dans le nettoyage |
| Mode intelligent (crossfade) = +CPU sur le VPS | LOW | À surveiller ; repli Mode normal si besoin |
| `/rename_nick` matche par pseudo affiché, pas garanti unique | LOW | `Listener-XXXX` dérivé du clientId modulo 9000 — collision possible entre deux auditeurs différents ; usage manuel ponctuel assumé, pas le mécanisme par défaut (`/rename` par clientId l'est) |

## Fichiers clés

| Fichier | Rôle | Statut |
|---------|------|--------|
| `tools/classify_bins.py` | **Source de vérité de la grille 8 bacs** : familles, SHARES, seuils auto-calibrés, classify_bin() | ✅ Nouveau, importé par migrate+triage |
| `tools/migrate_grid.py` | Migration one-shot 4→8 bacs (dry-run/--apply, garde-fou _incoming, rapport, WinSCP) | ✅ Exécutée le 2026-07-16 |
| `tools/resync_metadata.py` | Réparation metadata↔disque par nom sans préfixe (948→825 entrées) | ✅ Exécutée le 2026-07-16 |
| `tools/triage_new_tracks.py` | Pipeline ingestion → 8 bacs, nom propre, plus d'étape d'ordre | ✅ Mis à jour, à retester sur les 97 orphelins |
| `tools/build_rotation.py`, `tools/export_rotation.py` | Ancien calcul/export d'ordre | ⚠️ Superseded (en-têtes marqués) |
| `tools/orphans_report.txt` | 97 fichiers jamais analysés + 14 doublons physiques | ⏳ À traiter (gitignored) |
| `api/telegram.js` | Bot Telegram admin — hub de toutes les commandes (skip/msg/jingle/ban/pause, reply avec citation, supporters, badge supporter, reset Top 5, bandeau épinglé, np/stats, suppression bibliothèque, /ask Claude) | ✅ Déployé, très étendu le 2026-07-20 |
| `api/chat.js` | Chat live + modération + mapping `chat:tgmap` (reply) + `chat:pinned` (bandeau) + lookup `chat:supporters` (badge) + messages auto EN + anti-usurpation pseudo | ✅ Déployé |
| `api/reactions.js` | Vote 🔥 plafonné 10/auditeur/morceau (clientId obligatoire) + Top 5 + reset par epoch | ✅ Déployé, durci le 2026-07-20 |
| `api/supporters.js` | **Nouveau** — webhook Buy Me a Coffee (HMAC), remerciement chat + panneau Supporters + notif Telegram | ✅ Déployé, testé de bout en bout |
| `index.html` | Player complet EN, layout desktop réorganisé (Top 5 sous Historique, Supporters en avant), Vibe Streak, bandeau épinglé, Request, reconnexion durcie | ✅ Live |
| `manifest.webmanifest`, `sw.js` | PWA en anglais, cache bumpé `kfm-v14` | ✅ Live |
| `CONTEXT.md`, `graphify-out/` | Contexte + graphe de connaissances | ✅ À jour 2026-07-20 |

## Infrastructure

**Hébergement :**
- **Streaming** : VPS `167.233.226.128` (Ubuntu, Docker) — AzuraCast v0.23.7 + Icecast + Liquidsoap, `kalbassfm.duckdns.org` HTTPS, fuseau America/Martinique
- **Player** : Vercel — kalbassfm-player.vercel.app, deploy auto sur push GitHub (`abg5f/kalbassfm-player`)
- **Musique serveur** : volume Docker, dossier `Progv2/` contenant les 8 bacs ; anciens dossiers morning/... encore présents (filet 24h)
- **Musique locale** : `C:\Users\ph.dufourcq\Music\00_AZURACAST\New_prog\<bac>` + `_incoming` (triage)
- **Réseau perso** : RaiDrive `Z:` sur le SFTP AzuraCast (port 2022) ; FileZilla pour les gros uploads
- **Bot** : `@kalbassfm_bot` (BotFather), webhook `kalbassfm-player.vercel.app/api/telegram`

## Graphe de connaissances
> Mis à jour le 2026-07-20 (construction manuelle via /graphify, pas de CLI)

God nodes (concepts centraux) : `index.html` (hub front, degré 16), `AzuraCast` (infra + exécution de l'horloge, 10), `api/telegram.js` (hub des commandes admin, degré 9, dépasse ProgrammeGrid/VotingSystemPlan), `ProgrammeGrid`/horloge à bacs pondérés (8), `VotingSystemPlan` (8, toujours non codé), Upstash Redis (5 fonctions serverless), `classify_bins.py` (source de vérité classification).
Communautés détectées : 8 (Player/Frontend, Infra/Streaming, Serverless+bot Telegram, Intégrations externes [dons+IA, nouveau], Outillage/Pipeline, Essentia/Grille 8 bacs, Planning/Business, Contexte).
Pour explorer : `graphify query "<question>"` / `graphify explain "<concept>"`

---

_Mis à jour via `/save`. Lire ce fichier en début de session pour reprendre le contexte._
