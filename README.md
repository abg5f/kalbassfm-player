# KALBASSFM — Web Player

Player web pour **KALBASSFM**, webradio caribéenne diffusant électro, disco, funk et house 24/7.

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
- Minuteur de sommeil
- Partage du titre en cours
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
| Serverless | `api/` (chat live, supporters, bot Telegram admin, Flappy Kalbass — Vercel KV/Upstash Redis) |

## Infrastructure

```
VPS 167.233.226.128 (Ubuntu / Docker)
  └── AzuraCast
        ├── Icecast (diffusion)
        ├── Liquidsoap (AutoDJ)
        └── ~370+ morceaux, 4 playlists par créneau horaire

Vercel
  └── kalbassfm-player.vercel.app
        └── Player statique + fonctions serverless (chat, supporters, bot admin, Flappy)

Domaine : kalbassfm.duckdns.org (DuckDNS + Let's Encrypt auto-renouvelé)
```

## Outils locaux (`tools/`)

- `triage_new_tracks.py` (+ `triage.bat`) — pipeline d'ingestion : nettoyage tags/covers, dédoublonnage, analyse Essentia, classement dans le bon bac
- `classify_bins.py` — source de vérité de la grille : 8 bacs, classification genre-d'abord/énergie-ensuite, seuils auto-calibrés par percentiles
- `analyze_essentia.py` — analyse BPM/énergie/genre/mood (WSL2, modèles TensorFlow)
- `migrate_grid.py` / `resync_metadata.py` — migrations one-shot (grille 4→8 bacs, réparation metadata)
- `clean_local_tracks.py` — nettoie tags et noms de fichiers, détecte les pochettes de sites pirates et les remplace via iTunes Search API
- `import-rekordbox.ps1` — matche les exports `.txt` Rekordbox aux fichiers audio
- `build_rotation.py` / `export_rotation.py` — ⚠️ superseded (l'ordonnancement est délégué à AzuraCast)

Pipeline : **téléchargements → `_incoming` → `triage.bat` → `New_prog/<bac>` → upload SFTP → AzuraCast (Shuffled + poids + séparation artiste)**

## Roadmap

- [ ] Connecter Upstash KV pour les réactions 🔥 partagées entre auditeurs
- [ ] Synchro hebdomadaire PC → radio (WinSCP + tâche planifiée Windows)
- [ ] Jingles générés avec ElevenLabs
- [ ] Déclaration SACEM webradio
- [ ] Domaine payant (optionnel — bascule rapide depuis DuckDNS)
