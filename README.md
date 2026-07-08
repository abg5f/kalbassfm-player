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
- Grille de programme (heure Martinique UTC-4) :
  - 6h–12h : Disco / Funk
  - 12h–19h : Deep House
  - 19h–23h : Tech House
  - 23h–6h : Techno

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
| Serverless | `api/reactions.js` (compteur 🔥, store KV à connecter) |

## Infrastructure

```
VPS 167.233.226.128 (Ubuntu / Docker)
  └── AzuraCast
        ├── Icecast (diffusion)
        ├── Liquidsoap (AutoDJ)
        └── ~370+ morceaux, 4 playlists par créneau horaire

Vercel
  └── kalbassfm-player.vercel.app
        └── Player statique + fonction serverless reactions

Domaine : kalbassfm.duckdns.org (DuckDNS + Let's Encrypt auto-renouvelé)
```

## Outils locaux (`tools/`)

Scripts non versionnés (usage local uniquement) :

- `import-rekordbox.ps1` — matche les exports `.txt` Rekordbox aux fichiers audio et les copie dans les dossiers playlists
- `clean_local_tracks.py` — nettoie tags et noms de fichiers, détecte les pochettes de sites pirates et les remplace via iTunes Search API

Pipeline : **Rekordbox → export .txt → `import-rekordbox.ps1` → dossiers AzuraCast (via RaiDrive / SFTP Z:)**

## Roadmap

- [ ] Connecter Upstash KV pour les réactions 🔥 partagées entre auditeurs
- [ ] Synchro hebdomadaire PC → radio (WinSCP + tâche planifiée Windows)
- [ ] Jingles générés avec ElevenLabs
- [ ] Déclaration SACEM webradio
- [ ] Domaine payant (optionnel — bascule rapide depuis DuckDNS)
