# Context — KALBASSFM — FM Caraïbes (3_Radiofm)

> Dernière mise à jour : 2026-07-10

## État actuel

- ✅ **Pipeline d'analyse musicale Essentia opérationnel (WSL2 + Ubuntu)** — `tools/analyze_essentia.py` extrait BPM, énergie (RMS/dynamic complexity), danceability, mood (happy/sad/aggressive/relaxed/party) et top-3 genres (modèles TensorFlow discogs-effnet) pour casser la redondance de style façon FIP/Radio Meuh. 220 morceaux analysés, résultats dans `tools/metadata.json` (source de vérité unique, plus de copie manuelle WSL↔repo)
- ✅ **Rotation automatique par énergie + anti-répétition genre/artiste** — `tools/build_rotation.py` calcule un ordre de lecture par créneau (courbes d'énergie cible par slot dans `ENERGY_CURVES`, fenêtre glissante anti-répétition sur le sous-genre Discogs et l'artiste). `tools/export_rotation.py` applique l'ordre en renommant les fichiers en place (préfixe `NNN_`)
- ✅ **`New_prog` = nouvelle bibliothèque de référence** — les anciens dossiers `1_morning/2_afternoon/3_evening/4_night` (racine `00_AZURACAST`) ont été supprimés par l'utilisateur ; `New_prog\<créneau>\` les remplace, contient les 220 morceaux triés (27/76/78/39). Upload SFTP vers AzuraCast fait manuellement par l'utilisateur
- ✅ **Ingestion automatisée des nouveaux téléchargements** — `tools/triage_new_tracks.py` : dépôt dans `_incoming`, nettoyage tags/cover (réutilise `clean_local_tracks.py`), analyse Essentia, classification automatique du créneau (énergie la plus proche des courbes cibles), déplacement direct dans `New_prog\<créneau>\`, régénération auto de l'ordre. Testé avec succès sur un fichier réel (imports OK, modèles chargés)
- ⏳ **Couverture 24h incomplète** — total ~21h09/24h en supposant 6h/créneau ; morning (43% de couverture) et night (61%) sous-alimentés, l'utilisateur ajoute des morceaux manuellement
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

## En cours / TODOs

- [ ] **Combler morning/night** — ajout manuel de morceaux en cours par l'utilisateur pour ces créneaux sous-alimentés (43%/61% de couverture des 6h cibles) ; relancer `analyze_essentia.py` (ou `triage_new_tracks.py` via `_incoming`) une fois de nouveaux fichiers ajoutés
- [ ] **Remplacer/retélécharger `Alex Cortex - Discola.mp3`** — fichier MP3 corrompu (échoue à l'analyse Essentia ET à la lecture mutagen, "can't sync to MPEG frame")
- [ ] **Tags ID3 artiste manquants sur une grande partie de la bibliothèque** — la colonne "artiste" des CSV de rotation est presque toujours "?" ; lancer `clean_local_tracks.py --apply` sur `New_prog\*` (chemins à mettre à jour dans le script, il pointe encore sur les anciens dossiers) pour que l'anti-répétition d'artiste soit utile
- [ ] **Tester `triage_new_tracks.py` en conditions réelles avec upload SFTP ensuite** — le script a été validé sur les imports et un run à vide, mais pas encore sur un vrai nouveau téléchargement suivi d'un upload SFTP
- [ ] **Système de vote pour changer de style/playlist (planifié, pas codé)** — plan complet écrit dans `C:\Users\ph.dufourcq\.claude\plans\wild-cooking-book.md` : playlists candidates par genre, vote côté public (20 votes → bascule vers la playlist gagnante pendant 2h puis retour à la grille normale), anti-abus 1 vote/navigateur. Nécessite avant codage : créer les playlists genre + clé API AzuraCast (dashboard → My API Keys) + nouvelle fonction `api/vote.js` calquée sur `api/reactions.js` + panneau front dans `index.html`. Rien n'est implémenté à ce stade.
- [ ] **Graphe graphify construit manuellement (pas de CLI `graphify` installé)** — `graphify-out/` créé via lecture directe du repo (pas de commande `graphify update`/`graphify god-nodes` disponible dans l'environnement). À relancer via `/graphify` après changements significatifs ; si le CLI est installé un jour, préférer `graphify update .` à une reconstruction manuelle.
- [ ] **SACEM** — formulaire webradio à remplir (frais mentionnés dans les posts de lancement, pas encore fait)
- [ ] **Connecter un store Upstash/KV à Vercel** — pour que le compteur de réactions 🔥 soit partagé entre auditeurs (actuellement `enabled:false`, fallback local)
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
| `api/reactions.js` | Fonction serverless Vercel pour compteur 🔥 partagé | ⏳ Déployée mais store KV pas connecté |
| `tools/import-rekordbox.ps1` | Script local (PC) : matche les exports Rekordbox .txt aux fichiers audio, copie vers dossiers playlists | ✅ Local uniquement, non versionné dans le repo public |
| `tools/clean_local_tracks.py` | Script local : nettoie tags/noms de fichiers, détecte et remplace les covers de sites pirates via iTunes API | ✅ Local uniquement, chemins encore sur les anciens dossiers créneaux (à mettre à jour vers `New_prog`) |
| `/root/clean_music.py`, `/root/clean_covers.py` (sur le VPS) | Équivalents du nettoyage côté serveur AzuraCast | ✅ Sur le VPS, hors repo |
| `tools/analyze_essentia.py` | Analyse Essentia (BPM/énergie/genre/mood/danceability) sur toute la bibliothèque, écrit `tools/metadata.json` | ✅ WSL2 uniquement |
| `tools/build_rotation.py` | Calcule l'ordre de lecture par créneau (courbe d'énergie + anti-répétition genre/artiste), écrit `tools/playlists/*.{csv,m3u}` | ✅ Windows, pointe sur `New_prog` |
| `tools/export_rotation.py` | Applique l'ordre calculé : renomme les fichiers en place dans `New_prog` (préfixe `NNN_`, 2 phases anti-collision) | ✅ Windows |
| `tools/triage_new_tracks.py` | Pipeline d'ingestion des nouveaux téléchargements : `_incoming` → nettoyage → analyse Essentia → classification créneau → `New_prog` → régénération auto | ✅ WSL2, testé sur imports + 1 run réel |
| `~/kalbassfm-analysis/models/` (WSL, hors repo) | Modèles TensorFlow Essentia (discogs-effnet embeddings + têtes genre/danceability/mood) | ✅ ~150-200 Mo, téléchargés une fois |

## Infrastructure

**Hébergement :**
- **Streaming** : VPS `167.233.226.128` (Ubuntu, Docker) — AzuraCast + Icecast + Liquidsoap, domaine `kalbassfm.duckdns.org` en HTTPS
- **Player** : Vercel — kalbassfm-player.vercel.app, déploiement auto sur push GitHub (`abg5f/kalbassfm-player`)
- **Musique** : volume Docker nommé AzuraCast (pas de stockage cloud externe)
- **Réseau perso** : RaiDrive monte le SFTP AzuraCast en lecteur `Z:` sur le PC Windows

**Session notable** : une partie du travail PWA/mobile (fullscreen standalone, fix écran verrouillé) a été faite en parallèle par une autre session Claude (lancée depuis l'app mobile Claude), fusionnée sans conflit dans cette session.

## Graphe de connaissances
> Mis à jour le 2026-07-10 (construction manuelle, pas de CLI `graphify` disponible)

God nodes (concepts centraux) : `index.html` (hub front), `AzuraCast` (cœur infra streaming), `New_prog` (nouvelle bibliothèque de référence), `analyze_essentia.py`/`metadata.json` (pipeline d'analyse musicale), `build_rotation.py` (logique de diversité/rotation), `VotingSystemPlan` (feature de vote planifiée).
Communautés détectées : 7 (Player/Frontend, Infra/Streaming, Serverless-API+vote planifié, Outillage/Pipeline musique Rekordbox, Pipeline Essentia/Rotation musicale, Planning/Business, Contexte de session).
Pour explorer : `graphify query "<question>"` / `graphify explain "<concept>"`

---

_Mis à jour via `/save`. Lire ce fichier en début de session pour reprendre le contexte._
