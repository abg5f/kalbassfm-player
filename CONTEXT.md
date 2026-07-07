# Context — KALBASSFM — FM Caraïbes (3_Radiofm)

> Dernière mise à jour : 2026-07-07

## État actuel

- ✅ **Nom de la radio : KALBASSFM** — Radio Electronique de la Caraïbe (Kalbass = instrument antillais)
- ✅ **VPS Hetzner CPX22 live** — 167.233.226.128, EUR 19.49/mo (4 GB RAM, 2 vCPU, 80 GB SSD, Falkenstein)
- ✅ **AzuraCast déployé & configuré** — Station KALBASSFM créée, AutoDJ Liquidsoap actif, Icecast streaming
- ✅ **Player web custom hébergé** — https://kalbassfm-player.vercel.app/ (Brutalist design : noir/blanc/jaune)
- ✅ **Design brutalist finalisé** — Space Grotesk + Space Mono, 3px borders, HLS ready pour scalabilité
- ✅ **Branding ●KALBASSFM** — point rouge + logo calbass (calabash) en SVG brutalist
- ✅ **Bouton donations intégré** — Buy Me A Coffee link (https://buymeacoffee.com/kalbassfm)
- ⏳ **Domaine non encore acheté** — à vérifier (`kalbassfm.fm`, `kalbassfm.com`)
- ⏳ **Stockage musique non configuré** — Backblaze B2 en attente (URLs AzuraCast : 167.233.226.128/radio.mp3)

## Décisions prises

| Décision | Rationale |
|----------|-----------|
| **Nom : KALBASSFM** | Kalbass (instrument antillais) + FM, court, mémorable, lié à la Caraïbe |
| **VPS : Hetzner CPX22** | EUR 19.49/mo vs RareCloud instable. Meilleure stabilité + 4 GB RAM (suffisant AzuraCast solo) |
| **Design : Brutalism** | Noir/blanc/jaune, 3px borders, sans gradients. Space Grotesk (typo technique) |
| **Player : Vercel gratuit** | Static HTML/CSS/JS, auto-deploy depuis GitHub, 0€ (scalable via Cloudflare HLS en futur) |
| **Stockage : Backblaze B2** | EUR 0.30/mo pour 50 GB musique, egress gratuit via Cloudflare, API S3-compatible |
| **Infrastructure séparée** | AzuraCast seul sur Hetzner (stabilité garantie), player custom sur Vercel (léger) |
| **Genres horodatés** | Matin 6h-12h Disco/Funk · Après-midi 12h-17h House · 17h-21h Tech House · 21h-6h Techno/Trance |

## En cours / TODOs

**CRITIQUE (IMMÉDIAT) :**
- [ ] **Créer 4 playlists horodatées** dans AzuraCast (Morning/Afternoon/TechHouse/Night) + assigner tracks
- [ ] **Configurer Backblaze B2** — Storage Location dans AzuraCast → S3 Compatible → B2 credentials
- [ ] **Upload première vague de tracks** — SFTP ou web UI Backblaze, rescan AzuraCast
- [ ] **Acheter domaine** — `kalbassfm.fm`, `kalbassfm.com` sur Namecheap, pointer vers Cloudflare
- [ ] **Remplir formulaire SACEM** — 90€/an pour la diffusion légale

**À VENIR (PHASE 2) :**
- [ ] **Cloudflare HLS + edge caching** — permettre 500+ auditeurs simultanés sans stress serveur
- [ ] **Patreon/sponsorships** — monetization locale (bars/clubs/événements antillais)
- [ ] **Monitoring AzuraCast** — uptime, listener count, bandwidth graphs
- [ ] **Mobile app** — React Native ou PWA pour iOS/Android
- [ ] **Logo professionnel** — affiner le calbass SVG, favicon 16/32/180 sizes

## Problèmes connus

| Problème | Sévérité | Notes |
|----------|----------|-------|
| VPS RareCloud précédent : instabilité RAM | RESOLVED | Migré vers Hetzner CPX22, 4× plus de RAM |
| Artwork vide au démarrage | LOW | Normal — se remplit avec pochette track AzuraCast |
| Domaine pas encore acheté | MEDIUM | Urgent pour profil Buy Me A Coffee + branding |
| Backblaze B2 non configuré | MEDIUM | Nécessaire pour upload tracks (après création playlists) |

## Fichiers clés

| Fichier | Rôle | Statut |
|---------|------|--------|
| `index.html` | Player web custom brutalist (Vercel) | ✅ Live : https://kalbassfm-player.vercel.app |
| `.claude/launch.json` | Config preview server (port 4200) | ✅ Actif |
| `kalbassfm-player` (GitHub) | Repo public du player (auto-deploy Vercel) | ✅ Synced |
| `.planning/PLAN.md` | Plan d'exécution initial | ⏳ À mettre à jour (migration REC → KALBASSFM) |

## Infrastructure

**Hébergement :**
- **Streaming** : Hetzner CPX22 (Falkenstein, EU) — AzuraCast + Icecast + Liquidsoap (167.233.226.128)
- **Player** : Vercel CDN (Global) — kalbassfm-player.vercel.app
- **Musique** : Backblaze B2 (US) — S3-compatible, EUR 0.30/mo (50 GB)
- **Noms** : Cloudflare (DNS + HLS edge cache futur)

**Coût mensuel estimé :**
- VPS Hetzner : EUR 19.49
- Backblaze B2 : EUR 0.30
- Domaine : EUR 1 (~12 EUR/an)
- **TOTAL : EUR 21/mo**

---

_Mis à jour via `/save`. Lire ce fichier en début de session pour reprendre le contexte._
