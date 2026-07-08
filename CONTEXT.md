# Context — KALBASSFM — FM Caraïbes (3_Radiofm)

> Dernière mise à jour : 2026-07-08

## État actuel

- ✅ **Radio en ligne et diffusant 24/7** — AzuraCast station KALBASSFM, AutoDJ actif, ~370+ morceaux répartis en 4 créneaux (morning/afternoon/evening/night)
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

## En cours / TODOs

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
| `tools/clean_local_tracks.py` | Script local : nettoie tags/noms de fichiers, détecte et remplace les covers de sites pirates via iTunes API | ✅ Local uniquement |
| `/root/clean_music.py`, `/root/clean_covers.py` (sur le VPS) | Équivalents du nettoyage côté serveur AzuraCast | ✅ Sur le VPS, hors repo |

## Infrastructure

**Hébergement :**
- **Streaming** : VPS `167.233.226.128` (Ubuntu, Docker) — AzuraCast + Icecast + Liquidsoap, domaine `kalbassfm.duckdns.org` en HTTPS
- **Player** : Vercel — kalbassfm-player.vercel.app, déploiement auto sur push GitHub (`abg5f/kalbassfm-player`)
- **Musique** : volume Docker nommé AzuraCast (pas de stockage cloud externe)
- **Réseau perso** : RaiDrive monte le SFTP AzuraCast en lecteur `Z:` sur le PC Windows

**Session notable** : une partie du travail PWA/mobile (fullscreen standalone, fix écran verrouillé) a été faite en parallèle par une autre session Claude (lancée depuis l'app mobile Claude), fusionnée sans conflit dans cette session.

---

_Mis à jour via `/save`. Lire ce fichier en début de session pour reprendre le contexte._
