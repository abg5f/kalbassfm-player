# KALBASSFM — Graphe de connaissances

> Généré le 2026-07-09, mis à jour le 2026-07-16 puis le 2026-07-17 via `/graphify` (codebase complet : player, serverless, outillage, docs de planification).

## Vue d'ensemble

- **43 nœuds**, **57 relations**, **7 communautés** détectées.
- Le graphe couvre : le player web (`index.html`), les fonctions serverless de vote/Top 5/chat live (`api/reactions.js`, `api/chat.js`, Upstash Redis connecté), les scripts d'outillage musique (`tools/`), le pipeline Essentia/rotation (analyse + diversité de style + réparation de metadata), la playlist Jingles native AzuraCast, la PWA (`sw.js`, `manifest.webmanifest`), l'infra (AzuraCast/Icecast/Liquidsoap/VPS/Vercel/DuckDNS), les documents `.planning/` (vision produit, roadmap, requirements), et le plan (non codé) du système de vote de playlist par genre.

## Communautés

| Communauté | Membres clés |
|---|---|
| Player / Frontend | index.html, sw.js, manifest.webmanifest, PWA, égaliseur, votes, Top 5, chat live, popup contact, programme, now-playing |
| Infra / Streaming | AzuraCast, Icecast, Liquidsoap, VPS, DuckDNS, GitHub, Vercel, Admin API, playlist Jingles |
| Serverless / API (vote + chat temps réel connectés) + vote playlist planifié | api/reactions.js, api/chat.js, Upstash Redis (connecté 2026-07-16), Top 5, chat live, système de vote playlist (planifié) |
| Outillage / Pipeline musique | pipeline Rekordbox, import-rekordbox.ps1, clean_local_tracks.py, RaiDrive, iTunes Search API |
| Pipeline Essentia / Rotation musicale | analyze_essentia.py, build_rotation.py, dedup_metadata.py, normalize_and_dedup_metadata.py |
| Planning / Business | PROJECT.md, ROADMAP.md, PLAN.md, REQUIREMENTS.md, EXECUTION_CHECKLIST.md, STATE.md, SACEM |
| Contexte de session | CONTEXT.md, README.md |

## God nodes (les plus connectés)

1. **index.html** (degré 13) — hub de toutes les features front (now-playing, votes, Top 5, chat live, popup contact, égaliseur, PWA, programme).
2. **AzuraCast** (degré 9) — cœur de l'infra streaming, inclut la playlist Jingles native.
3. **VercelKV / Upstash Redis** (degré 7) — un seul store alimentant désormais trois fonctions serverless (votes, Top 5, chat live).
4. **api/reactions.js** (degré 6) — vote libre + classement Top 5.
5. **api/chat.js** (degré 5) — nouvelle fonction serverless (2026-07-17) : chat live anonyme + blocage de liens anti-autopromo.
6. **VotingSystemPlan** (degré 6) — feature de vote de playlist par genre planifiée, distincte du vote par morceau et du chat déjà codés.
7. **tools/build_rotation.py** (degré 6) — logique de diversité de rotation (familles de style, mini-mouvements, quota minoritaire).
8. **RekordboxPipeline** (degré 5) — processus reliant scripts locaux, RaiDrive et programme.
9. **ChatFeature** (degré 4) — remplace le bandeau ticker (supprimé), nouvelle zone permanente ouverte par défaut.

## Comment explorer

- `graphify query "<mot-clé>"` — ex. `graphify query "chat"`, `graphify query "build_rotation"`
- `graphify path "index.html" "AzuraCastAdminAPI"` — chemin entre deux nœuds
- `graphify explain "ChatFeature"` — résumé + connexions d'un nœud
- `graphify community "serverless-api"` — lister les membres d'une communauté
- `graphify god-nodes` — lister les hubs

## Notes

- Ce graphe est une snapshot manuelle (pas d'outil `graphify` CLI exécuté — construit par lecture directe des fichiers du repo). Relancer `/graphify` après des changements significatifs pour le mettre à jour.
- Le vote par morceau (`ReactionsFeature`/`api/reactions.js`) est **codé et connecté à un vrai store Redis** depuis le 2026-07-16 — les votes sont libres/illimités et le Top 5 se met à jour en direct (poll 4s, panneau ouvert par défaut depuis le 2026-07-16/17). Ne pas confondre avec `VotingSystemPlan`, un plan distinct et toujours non codé (vote de playlist par genre, bascule temporaire de programmation).
- Le **chat live** (`ChatFeature`/`api/chat.js`, 2026-07-17) reprend exactement le même modèle polling+Redis que le vote — confirme que ce modèle est le patron par défaut pour toute future feature "partagée entre auditeurs" sur ce projet, plutôt qu'un vrai temps réel (WebSocket/SSE), jugé superflu pour l'usage. Il remplace physiquement le bandeau ticker défilant (CSS/JS supprimés) et bloque les liens (autopromo/spam) à la fois côté client et côté serveur, le serveur étant le seul point d'application réel.
- La playlist `JinglesFeature` est gérée entièrement côté AzuraCast (UI native), volontairement hors du pipeline Python (`build_rotation.py`/`export_rotation.py`) pour rester stable indépendamment des régénérations de rotation.
