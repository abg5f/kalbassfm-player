# KALBASSFM — Graphe de connaissances

> Généré le 2026-07-09 via `/graphify` (codebase complet : player, serverless, outillage, docs de planification).

## Vue d'ensemble

- **31 nœuds**, **41 relations**, **6 communautés** détectées.
- Le graphe couvre : le player web (`index.html`), la fonction serverless de réactions (`api/reactions.js`), les scripts d'outillage musique (`tools/`), la PWA (`sw.js`, `manifest.webmanifest`), l'infra (AzuraCast/Icecast/Liquidsoap/VPS/Vercel/DuckDNS), les documents `.planning/` (vision produit, roadmap, requirements), et le plan (non codé) du système de vote de playlist.

## Communautés

| Communauté | Membres clés |
|---|---|
| Player / Frontend | index.html, sw.js, manifest.webmanifest, PWA, égaliseur, réactions, programme, now-playing |
| Infra / Streaming | AzuraCast, Icecast, Liquidsoap, VPS, DuckDNS, GitHub, Vercel, Admin API |
| Serverless / API + vote planifié | api/reactions.js, Vercel KV, système de vote (planifié) |
| Outillage / Pipeline musique | pipeline Rekordbox, import-rekordbox.ps1, clean_local_tracks.py, RaiDrive, iTunes Search API |
| Planning / Business | PROJECT.md, ROADMAP.md, PLAN.md, REQUIREMENTS.md, EXECUTION_CHECKLIST.md, STATE.md, SACEM |
| Contexte de session | CONTEXT.md, README.md |

## God nodes (les plus connectés)

1. **index.html** (degré 8) — hub de toutes les features front.
2. **AzuraCast** (degré 8) — cœur de l'infra streaming.
3. **VotingSystemPlan** (degré 6) — feature planifiée, déjà reliée à 5 autres nœuds bien qu'aucun code n'existe encore.
4. **RekordboxPipeline** (degré 5) — processus reliant scripts locaux, RaiDrive et programme.
5. **api/reactions.js** (degré 4) — seule fonction serverless existante, patron pour le futur `api/vote.js`.
6. **ProgrammeGrid** (degré 4) — convergence planning produit / pipeline musique / AzuraCast / vote.
7. **.planning/PROJECT.md** (degré 4) — racine de la vision produit.

## Comment explorer

- `graphify query "<mot-clé>"` — ex. `graphify query "reactions"`, `graphify query "AzuraCast"`
- `graphify path "index.html" "AzuraCastAdminAPI"` — chemin entre deux nœuds
- `graphify explain "VotingSystemPlan"` — résumé + connexions d'un nœud
- `graphify community "serverless-api"` — lister les membres d'une communauté
- `graphify god-nodes` — lister les hubs

## Notes

- Ce graphe est une snapshot manuelle (pas d'outil `graphify` CLI exécuté — construit par lecture directe des fichiers du repo). Relancer `/graphify` après des changements significatifs pour le mettre à jour.
- Le système de vote (`VotingSystemPlan`) n'est qu'un plan à ce stade (`C:\Users\ph.dufourcq\.claude\plans\wild-cooking-book.md`), aucun fichier de code ne l'implémente encore — les arêtes vers lui sont donc prospectives, pas des dépendances réelles de code.
