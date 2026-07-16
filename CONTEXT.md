# Context — KALBASSFM — FM Caraïbes (3_Radiofm)

> Dernière mise à jour : 2026-07-17

## État actuel (2026-07-17)

- ✅ **Store Upstash Redis confirmé connecté et fonctionnel** — vote 🔥 en direct testé via navigateur preview sur le vrai domaine de prod (`kalbassfm-player.vercel.app`) : incrément persistant, POST 200, comportement confirmé
- ✅ **Vote 🔥 changé en votes libres et illimités** — décision explicite de l'utilisateur, revient sur la limite "1 vote/morceau/auditeur" initiale : plus de `SADD voters:<id>` côté serveur, chaque clic incrémente. Le panneau Top 5 poll désormais toutes les 4s (au lieu de 30s) + re-poll immédiat après chaque vote pour un effet "jauge qui monte en direct"
- ✅ **Panneau Top 5 ouvert par défaut** (`<details open>`)
- ✅ **Chat live anonyme ajouté** — nouvelle fonction serverless `api/chat.js` (même squelette que `api/reactions.js` : Upstash Redis REST, repli gracieux `{enabled:false}`). Pseudo auto-généré (`Auditeur-XXXX`, `localStorage kfm_client_id`), pas de login. Liste Redis `chat:messages` (LPUSH/LTRIM à 100), rate-limit serveur 1 message/3s/auditeur via clé Redis à expiration (`SET ... EX 3 NX`), poll toutes les 3s. **Liens bloqués (anti-autopromo)** : regex de détection (`http(s)://`, `www.`, domaines type `truc.com`) appliquée côté client (retour immédiat, pas de cooldown consommé) ET côté serveur (le vrai point d'application, avant même le rate-limit). Échappement systématique via `textContent` (jamais `innerHTML`) pour empêcher toute injection HTML dans les messages
- ✅ **Bandeau ticker jaune défilant supprimé** — CSS (`.ticker`/`.ticker-inner`/`@keyframes ticker`) et JS (`TICKER_MSG`) nettoyés ; le panneau Chat live occupe désormais son emplacement, ouvert par défaut (`<details open>`)
- ✅ **Popup de contact ajouté** — "Owned by Lupari" dans le footer n'ouvre plus directement un `mailto:`, mais un modal (`#contactModal`, fermeture par clic sur le fond ou Échap) proposant email ou Instagram (`@luparimusic`)
- ✅ **15 jingles intégrés nativement dans AzuraCast** (Media → Playlists, type "Une fois tous les x titres" 10-15, Mode Jingle activé pour masquer les métadonnées) — guidé pas à pas via captures d'écran de l'utilisateur, aucune modification de code nécessaire (hors du pipeline Python, cf. décisions)
- ⏳ **Vérification live du chat en conditions réelles (deux navigateurs différents) pas encore faite dans cette session** — code vérifié en preview locale (repli gracieux, blocage de lien, cooldown) mais pas testé avec le vrai store Redis en prod

## État antérieur (2026-07-16)

- ✅ **Système de vote 🔥 par morceau opérationnel de bout en bout, store Redis connecté** — `api/reactions.js` réécrit : vote libre et illimité (plus de limite 1/morceau/auditeur, retirée à la demande explicite de l'utilisateur), classement Top 5 (sorted set Redis `ZINCRBY`/`ZRANGE`), panneau `#topPanel`/`#topList` dans `index.html` avec jauges proportionnelles, poll toutes les 4s + re-poll immédiat après chaque vote. **Upstash for Redis connecté au projet Vercel le 2026-07-16** (via Vercel Storage → Marketplace → Upstash for Redis, région Washington D.C., plan Free, Production+Preview) — les variables `KV_REST_API_URL`/`KV_REST_API_TOKEN` sont en place. Redeploy déclenché ; vérification live en direct (vote → Top 5 qui se peuple) pas encore confirmée dans cette session
- ✅ **Diversification de la rotation enrichie** — `tools/build_rotation.py` : mini-mouvements sinusoïdaux d'énergie superposés à la rampe linéaire par créneau (respirations façon set DJ), quota minoritaire garantissant qu'une famille rare apparaît au moins une fois par quart de créneau, deux nouvelles familles de style de premier rang **Reggae/Dub** et **Jungle/DnB** (au même titre que House/Techno/Garage/Disco-Funk), garde-fou `enforce_family_limit` désormais bidirectionnel (recherche avant ET arrière) avec jusqu'à 5 passes
- ✅ **Bug de mélange de formats de chemin WSL/Windows corrigé définitivement** — `analyze_essentia.py` (`normalize_path()`) et `triage_new_tracks.py` (`wsl_to_windows()`) normalisent systématiquement ; a mis fin à un incident de ~5h30 de ré-analyse redondante causé par des comparaisons `done_paths` qui échouaient entre chemins équivalents mais formatés différemment
- ✅ **`tools/normalize_and_dedup_metadata.py` créé** — script de réparation sûr de `metadata.json` (ne supprime jamais une entrée irrécupérable sans avoir tenté de la réparer d'abord), tire la leçon de l'incident de perte de données causé par `tools/dedup_metadata.py` (260 entrées perdues, désormais superseded)
- ✅ **`clean_mp3_library.py` fusionné** (hors repo, `C:\Users\ph.dufourcq\Music\00_AZURACAST\scripts\`) — fusion de `clean_local_tracks.py` + `clean_mp3_library.py` en un seul script complet (nettoyage tags, détection covers de sites pirates, lookup iTunes, préservation du préfixe `NNN_`), à la demande explicite de l'utilisateur
- ✅ **15 jingles audio générés (voix off) et intégrés nativement dans AzuraCast** — dossier `Jingles/` (hors repo, non versionné), uploadés dans Media → Files, playlist dédiée créée avec Mode Jingle activé (masque les métadonnées) et type "Une fois tous les x titres" (10-15) — volontairement **hors du pipeline Python** (`build_rotation.py`/`export_rotation.py`) pour rester stable indépendamment des régénérations de rotation
- ✅ **`.gitignore` créé** — exclut `.claude/`, `.planning/`, `Jingles/`, `tools/__pycache__/`, `tools/triage_report.html`
- ⏳ **SACEM toujours pas fait**
- ⏳ **TuneIn Partner ID/Partner Key toujours en attente** de TuneIn support (station soumise, ID s358721/référence 358721)

## État antérieur (2026-07-10, conservé pour l'historique)

- ✅ **Pipeline d'ingestion `triage_new_tracks.py` complet et utilisé en prod** — nettoyage tags/cover, détection de doublons (artiste+titre normalisés en tokens, seuil de similarité 75%, comparé contre `New_prog` uniquement — PAS toute la bibliothèque Music, cf. décisions), analyse Essentia, classification par créneau, régénération auto de l'ordre. Doublons/échecs déplacés dans `_incoming/_duplicates` et `_incoming/_failed`
- ✅ **Interface de suivi en direct** — `tools/triage_report.html` (généré/écrasé à chaque morceau traité, auto-refresh 2s, s'ouvre automatiquement dans le navigateur au lancement) : progression, répartition par créneau avec barres, tableaux doublons/échecs
- ✅ **Lanceur `.bat`** — `C:\Users\ph.dufourcq\Music\00_AZURACAST\scripts\triage.bat` (double-clic → active le venv WSL et lance `triage_new_tracks.py`)
- ✅ **Bibliothèque `New_prog` passée de 220 à 349 morceaux** — l'utilisateur a lancé le pipeline plusieurs fois en conditions réelles. Répartition finale (après réparation, voir ci-dessous) : 1_morning 74, 2_afternoon 108, 3_evening 76, 4_night 88 (+ 3 doublons physiques laissés de côté, non renommés)
- 🔧 **Bug critique corrigé : régénération auto de `New_prog` échouait silencieusement depuis le début** — l'appel `subprocess` dans `triage_new_tracks.py` vers `cmd.exe` avait un bug de quoting (chemin avec espaces mal échappé) ; `check=False` masquait l'échec. Conséquence découverte lors de ce `/save` : 129 morceaux sur 349 n'avaient jamais été renumérotés (`NNN_`) malgré plusieurs runs de `triage_new_tracks.py`. Corrigé en passant par une liste d'arguments (pas de `shell=True` fait main) + `encoding="cp1252"` (la sortie console Windows n'est pas UTF-8)
- 🔧 **Bug corrigé : `export_rotation.py` ne resynchronisait jamais `metadata.json` après renommage** — dès le tout premier cycle de rotation, les chemins stockés dans `metadata.json` devenaient obsolètes, cassant les cycles suivants en cascade (fichiers "MANQUANT"). `export_rotation.py` met maintenant à jour `metadata.json` à la fin de chaque run
- ⚠️ **~55 doublons physiques découverts dans `New_prog`** (même morceau présent en double, parfois dans deux créneaux différents, ex. `Cinthie - U Gotta Believe` en `2_afternoon` ET `3_evening`) — antérieurs à la détection de doublons de `triage_new_tracks.py` (probablement des lots ingérés avant son ajout). Pas supprimés automatiquement (action destructive volontairement laissée à l'utilisateur) — voir TODO
- ✅ **Couverture 24h largement atteinte** — total 35h24 sur 24h visées (6h/créneau) ; les créneaux morning/night autrefois sous-alimentés sont désormais couverts. Seul déséquilibre restant : `afternoon` nettement plus gros que les autres (pas bloquant)
- ✅ **Visuels + textes de lancement Instagram créés** — post carré 1080×1080 et story 1080×1920 (identité visuelle noir/jaune/mascotte calebasse avec casque, cohérente avec `og-image.png` existant), sur le bureau (`kalbassfm_launch_post_square.png/.svg`, `kalbassfm_launch_story.png/.svg`). Légende finale orientée storytelling perso ("années de digging, moins sollicité pour jouer, partage gratuit de la bibliothèque") plutôt que communiqué de lancement générique
- ✅ **Campagne sponsorisée Instagram lancée par l'utilisateur** — ciblage Martinique/Guadeloupe/Saint-Martin, 18-35 ans, intérêts musique électronique/house/techno, budget 5€/jour sur 7 jours (~35€ total). Résultats pas encore analysés
- ✅ **Pipeline d'analyse musicale Essentia opérationnel (WSL2 + Ubuntu)** — `tools/analyze_essentia.py` extrait BPM, énergie (RMS/dynamic complexity), danceability, mood (happy/sad/aggressive/relaxed/party) et top-3 genres (modèles TensorFlow discogs-effnet) pour casser la redondance de style façon FIP/Radio Meuh. `tools/metadata.json` = source de vérité unique (plus de copie manuelle WSL↔repo)
- ✅ **Rotation automatique par énergie + anti-répétition genre/artiste** — `tools/build_rotation.py` calcule un ordre de lecture par créneau (courbes d'énergie cible par slot dans `ENERGY_CURVES`, fenêtre glissante anti-répétition sur le sous-genre Discogs et l'artiste). `tools/export_rotation.py` applique l'ordre en renommant les fichiers en place (préfixe `NNN_`)
- ✅ **`New_prog` = bibliothèque de référence** — les anciens dossiers `1_morning/2_afternoon/3_evening/4_night` (racine `00_AZURACAST`) ont été supprimés par l'utilisateur ; `New_prog\<créneau>\` les remplace. Upload SFTP vers AzuraCast fait manuellement par l'utilisateur
- ✅ **Radio en ligne et diffusant 24/7** — AzuraCast station KALBASSFM, AutoDJ actif
- ✅ **Domaine + SSL actifs** — `kalbassfm.duckdns.org` (DuckDNS gratuit, pas d'achat de domaine payant finalement) + certificat Let's Encrypt auto-renouvelé
- ✅ **Player web public fonctionnel** — https://kalbassfm-player.vercel.app/ — flux HTTPS, now-playing, pochettes, égaliseur réactif au son réel (Web Audio API, désactivé sur mobile pour survivre à l'écran verrouillé)
- ✅ **PWA installable** — manifest, service worker, icônes avec le vrai logo Kalbass (mascotte calebasse), bandeau d'installation mobile (instructions spécifiques iOS) + raccourci permanent dans le header
- ✅ **Fonctionnalités live** — compteur d'auditeurs, historique des titres, recherche YouTube du morceau en cours, partage, réactions 🔥 (compteur local, backend KV pas encore connecté), minuteur de sommeil, grille de programme réelle (Disco/Funk 6h-12h, Deep House 12h-19h, Tech House 19h-23h, Techno 23h-6h, heure Martinique UTC-4)
- ✅ **Pipeline musique Rekordbox → radio opérationnel** — scripts locaux (`tools/`) pour importer les exports Rekordbox, résoudre les ambiguïtés, nettoyer tags/covers (sites pirates détectés et supprimés, vraies pochettes via iTunes Search API)
- ✅ **RaiDrive monté** — lecteur réseau `Z:` sur le SFTP AzuraCast (port 2022), gestion des dossiers playlists comme des dossiers locaux
- ⏳ **SACEM non encore fait** — toujours à faire pour la diffusion légale
- ⏳ **Réactions 🔥 en local uniquement** — nécessite un store Upstash/KV connecté sur Vercel pour un compteur partagé entre auditeurs

## Décisions prises

| Décision | Rationale |
|----------|-----------|
| **Stockage musique : volume Docker AzuraCast (pas Backblaze B2)** | Plus simple, inclus, pas de coût additionnel — le plan B2 initial n'a finalement pas été utilisé |
| **Domaine : DuckDNS gratuit (pas d'achat)** | Suffisant pour SSL Let's Encrypt + usage actuel ; achat d'un vrai domaine reste possible plus tard (bascule rapide) |
| **Upload musique : SFTP intégré AzuraCast (port 2022)** | Piège découvert : le dossier media vit dans un volume Docker nommé, invisible depuis SSH classique sur l'hôte |
| **Playlists assignées par dossier, pas par fichier** | Tout nouveau fichier déposé dans un dossier rejoint automatiquement sa playlist — base du pipeline Rekordbox → radio |
| **Playlist "Copier X" sans horaire par créneau** | Filet de sécurité si une playlist planifiée se retrouve vide (a réellement servi lors d'un incident TechHouse) |
| **Nettoyage tags/covers via script Python (dry-run puis --apply)** | Pattern validé et repris systématiquement (VPS + PC local) : toujours prévisualiser avant d'appliquer |
| **Egaliseur désactivé sur mobile (Web Audio API)** | L'OS suspend l'AudioContext à l'écran verrouillé, coupant le son — le natif `<audio>` + Media Session survit, pas l'AudioContext |
| **Import Rekordbox : matching par tokens titre+artiste, pas par chemin** | Les exports .txt Rekordbox ne contiennent pas le chemin fichier — recherche floue dans la bibliothèque locale avec seuils ambigu/clair |
| **Analyse musicale : Essentia via WSL2, pas nativement Windows** | Pas de wheels pip Windows pour Essentia (Linux/macOS uniquement) — venv `~/essentia-env` dans Ubuntu/WSL2, modèles TensorFlow dans `~/kalbassfm-analysis/models` (~150-200 Mo) |
| **Sous-genre Discogs pour la diversité, pas la catégorie top-level** | Bibliothèque 100% électronique → catégorie top-level ("Electronic") quasi constante et inutile pour l'anti-répétition ; le sous-genre après "---" (Deep House, Techno, UK Garage...) est le niveau discriminant |
| **`New_prog` remplace les dossiers créneaux d'origine** | Décision utilisateur (suppression volontaire des anciens dossiers) — tous les scripts (`build_rotation.py`, `export_rotation.py`, `triage_new_tracks.py`) pointent désormais sur `New_prog\<créneau>\` comme unique source |
| **`export_rotation.py` renomme en place (2 phases) plutôt que de copier** | Depuis que `New_prog` est à la fois source et destination, un renommage direct (temp puis final, pour éviter les collisions) remplace l'ancienne copie inter-dossiers |
| **Upload SFTP fait manuellement par l'utilisateur, pas automatisé** | Choix explicite pour garder le contrôle sur la mise en prod ; le pipeline s'arrête à la préparation locale dans `New_prog` |
| **Détection de doublons : tokens artiste+titre normalisés (seuil 75%), pas nom de fichier exact** | Les noms de fichiers varient trop selon la source de téléchargement (suffixes site, casse, ponctuation) pour un matching exact ; le seuil à 75% reste un point fragile (faux positifs/négatifs possibles), pas encore testé sur cas limites |
| **Index de doublons scanne `New_prog` uniquement, pas tout `C:\Users\ph.dufourcq\Music`** | Testé puis explicitement annulé par l'utilisateur — la bibliothèque Music complète (2944 fichiers) contient des dossiers hors-scope radio (`Mariage`, `iTunes`, outils) ; `_incoming` reste aussi l'unique source des "nouveaux morceaux à traiter" |
| **Rapport HTML régénéré à chaque fichier (pas de serveur local)** | `triage_report.html` avec `<meta http-equiv="refresh">` suffit pour un suivi live en ouvrant simplement le fichier dans le navigateur, évite la complexité d'un serveur HTTP local |
| **Conversion SVG→PNG via Edge headless (`--screenshot`)** | `cairosvg` non installé sur la machine ; Edge headless déjà présent nativement sur Windows 11, évite une dépendance supplémentaire |
| **Vote 🔥 libre et illimité (pas de limite 1/auditeur)** | Décision explicite de l'utilisateur (2026-07-16), revient sur le choix initial "1 vote/morceau/auditeur" du plan — priorité donnée à l'effet "jauge qui monte en direct" plutôt qu'à l'équité stricte du classement |
| **Jingles gérés nativement dans AzuraCast (Media → Playlists), pas dans le pipeline Python** | Le pipeline (`build_rotation.py`/`export_rotation.py`) réécrit intégralement les playlists de créneaux à chaque export ; des jingles insérés "en dur" seraient perdus/décalés à chaque régénération. La fonctionnalité native "Une fois tous les x titres" + Mode Jingle est stable indépendamment de ça |
| **Upstash for Redis (Marketplace) au lieu de l'ancien "Vercel KV" natif** | Vercel a migré son offre de storage clé-valeur vers des providers Marketplace ; Upstash for Redis expose la même API REST (`KV_REST_API_URL`/`KV_REST_API_TOKEN`) que le code attendait déjà, donc compatible sans changement de code |
| **Reggae/Dub et Jungle/DnB en familles de style de premier rang (pas des sous-genres génériques)** | Demande explicite : ces styles doivent être traités "au même titre que" House/Techno pour la contrainte anti-monotonie (max 2 consécutifs, quota minoritaire), pas relégués en famille résiduelle |
| **Chat live : polling 3s + Redis, pas de WebSocket/SSE/service tiers (Pusher, Ably...)** | Vercel Functions sont sans état et de courte durée, pas adaptées aux connexions persistantes ; un chat "quasi temps réel" par polling est largement suffisant pour un chat d'accompagnement radio et réutilise 100% l'infra déjà en place |
| **Chat live : pseudo auto-généré non modifiable, pas de champ à remplir** | Décision explicite de l'utilisateur (choix "recommandé" en plan mode) — zéro friction, cohérent avec le pattern `clientId` déjà utilisé pour le vote |
| **Chat live : modération basique uniquement (rate-limit + longueur), pas de filtre de mots interdits au lancement** | Décision explicite de l'utilisateur — à ajouter plus tard si besoin, sans changer l'architecture |
| **Liens bloqués dans le chat (anti-autopromo), validation dupliquée client + serveur** | Le client donne un retour instantané sans round-trip réseau ; le serveur est le seul point d'application réel (un client malveillant peut contourner le JS du navigateur) |
| **Bandeau ticker supprimé et remplacé par le chat (pas juste ajouté ailleurs)** | Demande explicite de l'utilisateur — le chat prend la place la plus visible du player plutôt que d'être relégué en panneau repliable au même niveau que Historique/Top 5 |

## En cours / TODOs

- [ ] **Nettoyer les ~55 doublons physiques dans `New_prog`** — même fichier (taille identique) présent 2-3 fois, parfois dans des créneaux différents (ex. `Cinthie - U Gotta Believe`, `Retromigration - Half Fried` en 3 exemplaires). Repérables via les noms sans le préfixe `NNN_` ; supprimer manuellement après vérification (action destructive, pas automatisée)
- [ ] **Analyser les résultats de la campagne Instagram sponsorisée** — lancée le 2026-07-10, 5€/jour sur 7 jours (fin prévue ~2026-07-17), ciblage Martinique/Guadeloupe/Saint-Martin 18-35 ans. Revenir avec les stats (CTR, coût/clic, portée) une fois disponibles
- [ ] **Calibrer le seuil de détection de doublons (75%) sur des cas limites réels** — pas encore testé sur des paires ambiguës (ex. deux remixes différents du même morceau, qui ne doivent PAS matcher)
- [ ] **Régénérer les visuels Instagram avec l'accroche "années de digging" si souhaité** — actuellement les PNG/SVG sur le bureau disent encore "C'EST LE LANCEMENT !" ; l'utilisateur a dit "oui" à l'ajustement du ton mais n'a pas confirmé vouloir régénérer les fichiers images eux-mêmes
- [ ] **Remplacer/retélécharger `Alex Cortex - Discola.mp3`** — fichier MP3 corrompu (échoue à l'analyse Essentia ET à la lecture mutagen, "can't sync to MPEG frame")
- [ ] **Tags ID3 artiste manquants sur une partie de la bibliothèque** — colonne "artiste" des CSV de rotation souvent "?" ; lancer `clean_local_tracks.py --apply` sur `New_prog\*` (chemins à mettre à jour dans le script, il pointe encore sur les anciens dossiers) pour que l'anti-répétition d'artiste et la détection de doublons soient pleinement fiables
- [ ] **Rééquilibrer `afternoon`** — nettement plus gros que les autres créneaux (11h vs 7-9h), pas bloquant mais un morceau y revient moins souvent
- [ ] **Système de vote pour changer de style/playlist (planifié, pas codé)** — plan complet écrit dans `C:\Users\ph.dufourcq\.claude\plans\wild-cooking-book.md` : playlists candidates par genre, vote côté public (20 votes → bascule vers la playlist gagnante pendant 2h puis retour à la grille normale), anti-abus 1 vote/navigateur. Nécessite avant codage : créer les playlists genre + clé API AzuraCast (dashboard → My API Keys) + nouvelle fonction `api/vote.js` calquée sur `api/reactions.js` + panneau front dans `index.html`. Rien n'est implémenté à ce stade.
- [ ] **Graphe graphify construit manuellement (pas de CLI `graphify` installé)** — `graphify-out/` créé via lecture directe du repo (pas de commande `graphify update`/`graphify god-nodes` disponible dans l'environnement). À relancer via `/graphify` après changements significatifs ; si le CLI est installé un jour, préférer `graphify update .` à une reconstruction manuelle.
- [ ] **SACEM** — formulaire webradio à remplir (frais mentionnés dans les posts de lancement, pas encore fait)
- [x] **Connecter un store Upstash/KV à Vercel** — fait le 2026-07-16, confirmé fonctionnel le 2026-07-17 (vote testé en direct sur le domaine de prod, incrément persistant)
- [x] **Vérifier en direct le fonctionnement du vote une fois le redeploy Vercel terminé** — fait le 2026-07-17 sur `kalbassfm-player.vercel.app`
- [ ] **Vérifier en direct le chat live avec deux navigateurs différents en conditions réelles** — code vérifié en preview locale (repli gracieux, blocage de lien, cooldown) mais pas testé avec le vrai store Redis en prod dans cette session ; à faire : envoyer un message depuis un navigateur, confirmer qu'il apparaît dans un autre au poll suivant (≤3s)
- [ ] **Mettre à jour `tools/build_rotation.py` + `export_rotation.py` avec les nouveaux morceaux Reggae/Dub et Jungle/DnB une fois `triage.bat` lancé** — l'utilisateur était encore en train de télécharger ces morceaux au moment de la dernière session, le triage n'a pas encore tourné dessus
- [ ] **Traiter les morceaux ambigus/introuvables restants** — `AI GO RYTHM - FUNK edit/edit 2`, `Retromigration - Halt & Stop`, `m - jungle remaster...` (scores faibles, jamais tranchés)
- [ ] **Synchro hebdomadaire PC → radio** — script WinSCP + tâche planifiée Windows évoqué mais pas mis en place
- [ ] **Jingles ElevenLabs** — propositions de textes faites, ni la génération audio ni l'intégration playlist "Jingles" faites
- [ ] **Domaine payant** (optionnel) — si `kalbassfm.com` ou similaire est acheté un jour, bascule di rapide depuis DuckDNS

## Problèmes connus

| Problème | Sévérité | Notes |
|----------|----------|-------|
| Un fichier MP3 corrompu détecté | LOW | `Alex Cortex - Discola.mp3` — erreur "can't sync to MPEG frame", à re-télécharger si besoin |
| Rerun du script d'import Rekordbox après renommage local | LOW | Les fichiers renommés par `clean_local_tracks.py` ne correspondent plus au nom source → le script d'import peut re-proposer une copie ("A COPIER" au lieu de "DEJA PRESENT") ; sans danger mais source de confusion si réexécuté |
| Rate limit API iTunes Search | LOW | ~20 req/min non authentifié — le script de nettoyage throttle à 3.2s/requête, donc lent sur de gros lots (~200 morceaux = 3-4 min) |
| Description de la station AzuraCast | LOW | Contient une double virgule ("Électronique, , Disco") — cosmétique, jamais corrigé |

## Fichiers clés

| Fichier | Rôle | Statut |
|---------|------|--------|
| `index.html` | Player web complet (flux, égaliseur, PWA, features live) | ✅ Live sur Vercel |
| `manifest.webmanifest`, `sw.js` | Config PWA + service worker | ✅ Actifs |
| `icon-192.png`, `icon-512.png`, `og-image.png` | Icônes PWA (logo Kalbass) + image de partage réseaux sociaux | ✅ |
| `api/reactions.js` | Fonction serverless Vercel : vote libre illimité 🔥 + classement Top 5 (sorted set Redis) | ✅ Déployée, store Upstash Redis connecté et testé en direct (2026-07-16/17) |
| `api/chat.js` | Fonction serverless Vercel : chat live anonyme (liste Redis, rate-limit serveur, blocage de liens anti-autopromo) | ✅ Déployée, pas encore testée en direct avec deux clients réels |
| `tools/normalize_and_dedup_metadata.py` | Réparation sûre de `metadata.json` (normalise/dédoublonne/répare sans jamais supprimer une entrée irrécupérable) | ✅ Local, WSL2 |
| `tools/dedup_metadata.py` | Ancien script de dédoublonnage (supprimait sans réparer) — conservé pour l'historique, ne plus utiliser | ⚠️ Superseded |
| `.gitignore` | Exclut `.claude/`, `.planning/`, `Jingles/`, `tools/__pycache__/`, `tools/triage_report.html` du repo | ✅ Créé le 2026-07-16 |
| `tools/import-rekordbox.ps1` | Script local (PC) : matche les exports Rekordbox .txt aux fichiers audio, copie vers dossiers playlists | ✅ Local uniquement, non versionné dans le repo public |
| `tools/clean_local_tracks.py` | Script local : nettoie tags/noms de fichiers, détecte et remplace les covers de sites pirates via iTunes API | ✅ Local uniquement, chemins encore sur les anciens dossiers créneaux (à mettre à jour vers `New_prog`) |
| `/root/clean_music.py`, `/root/clean_covers.py` (sur le VPS) | Équivalents du nettoyage côté serveur AzuraCast | ✅ Sur le VPS, hors repo |
| `tools/analyze_essentia.py` | Analyse Essentia (BPM/énergie/genre/mood/danceability) sur toute la bibliothèque, écrit `tools/metadata.json` | ✅ WSL2 uniquement |
| `tools/build_rotation.py` | Calcule l'ordre de lecture par créneau (courbe d'énergie + anti-répétition genre/artiste), écrit `tools/playlists/*.{csv,m3u}` | ✅ Windows, pointe sur `New_prog` |
| `tools/export_rotation.py` | Applique l'ordre calculé : renomme les fichiers en place dans `New_prog` (préfixe `NNN_`, 2 phases anti-collision) | ✅ Windows |
| `tools/triage_new_tracks.py` | Pipeline d'ingestion complet : `_incoming` → nettoyage → dédoublonnage (vs `New_prog`) → analyse Essentia → classification créneau → `New_prog` → régénération auto + rapport HTML live | ✅ WSL2, utilisé en prod (220→349 morceaux sur 2 lots) |
| `tools/triage_report.html` (généré, pas versionné) | Rapport de suivi live auto-refresh, ouvert automatiquement au lancement | ✅ |
| `C:\Users\ph.dufourcq\Music\00_AZURACAST\scripts\triage.bat` (hors repo) | Lanceur double-clic du pipeline d'ingestion | ✅ |
| `~/kalbassfm-analysis/models/` (WSL, hors repo) | Modèles TensorFlow Essentia (discogs-effnet embeddings + têtes genre/danceability/mood) | ✅ ~150-200 Mo, téléchargés une fois |
| `~/Desktop/kalbassfm_launch_post_square.{png,svg}`, `~/Desktop/kalbassfm_launch_story.{png,svg}` (hors repo) | Visuels de lancement Instagram (post carré 1080×1080, story 1080×1920), identité noir/jaune/mascotte calebasse | ✅ |

## Infrastructure

**Hébergement :**
- **Streaming** : VPS `167.233.226.128` (Ubuntu, Docker) — AzuraCast + Icecast + Liquidsoap, domaine `kalbassfm.duckdns.org` en HTTPS
- **Player** : Vercel — kalbassfm-player.vercel.app, déploiement auto sur push GitHub (`abg5f/kalbassfm-player`)
- **Musique** : volume Docker nommé AzuraCast (pas de stockage cloud externe)
- **Réseau perso** : RaiDrive monte le SFTP AzuraCast en lecteur `Z:` sur le PC Windows

**Session notable** : une partie du travail PWA/mobile (fullscreen standalone, fix écran verrouillé) a été faite en parallèle par une autre session Claude (lancée depuis l'app mobile Claude), fusionnée sans conflit dans cette session.

## Graphe de connaissances
> Mis à jour le 2026-07-17 (construction manuelle, pas de CLI `graphify` disponible)

God nodes (concepts centraux) : `index.html` (hub front — now-playing/vote/Top5/chat live/popup contact/égaliseur/PWA), `AzuraCast` (cœur infra streaming, inclut la playlist Jingles native), `VercelKV`/Upstash Redis (un seul store alimentant trois fonctions serverless : vote, Top 5, chat live), `api/reactions.js` (vote libre + Top 5), `api/chat.js` (chat live anonyme + anti-autopromo, nouveau le 2026-07-17), `VotingSystemPlan` (feature distincte de vote de playlist par genre, toujours planifiée/non codée), `tools/build_rotation.py` (diversité de rotation : familles de style, mini-mouvements, quota minoritaire).
Communautés détectées : 7 (Player/Frontend, Infra/Streaming, Serverless-API vote+chat connectés, Outillage/Pipeline musique Rekordbox, Pipeline Essentia/Rotation musicale, Planning/Business, Contexte de session).
Pour explorer : `graphify query "<question>"` / `graphify explain "<concept>"`

---

_Mis à jour via `/save`. Lire ce fichier en début de session pour reprendre le contexte._
