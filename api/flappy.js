/* Classement global du mini-jeu Flappy Kalbass, partage entre auditeurs.
   Meme backend que api/chat.js (Vercel KV / Upstash Redis via API REST,
   variables d'env KV_REST_API_URL + KV_REST_API_TOKEN). Sans store configure,
   renvoie { enabled:false } et le front bascule sur le high score local
   uniquement — jamais d'erreur visible.

   Structure Redis :
   - sorted set "flappy:leaderboard" : score = meilleur score du clientId, membre = clientId
   - hash "flappy:meta"              : clientId -> pseudo affiche (dernier connu)

   Seul le meilleur score de chaque clientId est garde (lecture du score actuel
   avant ecriture, pas d'ecrasement si le nouveau score est plus bas).
*/
const MAX_SCORE = 100000;
const MAX_LEADERBOARD_SIZE = 500; // borne la croissance, on ne garde que le Top

// Reactive le 2026-07-21 : Upstash passe en Pay As You Go + Top 5 retire
// (gros consommateur), donc quota nettement moins a risque.
const REDIS_PAUSED = false;

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(204).end();

  const base = process.env.KV_REST_API_URL;
  const token = process.env.KV_REST_API_TOKEN;
  if (!base || !token || REDIS_PAUSED) return res.status(200).json({ enabled: false, top: [] });

  const headers = { Authorization: `Bearer ${token}` };
  const kv = (...segments) => fetch(`${base}/${segments.map(encodeURIComponent).join('/')}`, { headers }).then(r => r.json());

  // ---- GET ?top=10 : classement des meilleurs scores ----
  if (req.method === 'GET' && req.query.top) {
    try {
      const n = Math.min(parseInt(req.query.top, 10) || 10, 50);
      const zj = await kv('zrange', 'flappy:leaderboard', '0', String(n - 1), 'REV', 'WITHSCORES');
      if (zj.result === undefined) throw new Error('kv-error');
      const raw = zj.result || [];
      const top = [];
      for (let i = 0; i < raw.length; i += 2) {
        const clientId = raw[i];
        const score = parseInt(raw[i + 1], 10) || 0;
        const nj = await kv('hget', 'flappy:meta', clientId);
        top.push({ nick: nj.result || 'Listener', score });
      }
      return res.status(200).json({ enabled: true, top });
    } catch {
      return res.status(200).json({ enabled: false, top: [] });
    }
  }

  // ---- POST : soumettre un score (garde seulement le meilleur par clientId) ----
  const body = req.body || {};
  const clientId = (body.clientId || '').toString().slice(0, 64).replace(/[^a-zA-Z0-9_-]/g, '') || null;
  const nick = (body.nick || 'Listener').toString().slice(0, 30) || 'Listener';
  const score = Math.max(0, Math.min(MAX_SCORE, parseInt(body.score, 10) || 0));

  if (!clientId || score <= 0) return res.status(200).json({ enabled: true, ok: false });

  try {
    const curJ = await kv('zscore', 'flappy:leaderboard', clientId);
    const currentBest = parseInt(curJ.result ?? 0, 10) || 0;
    if (score > currentBest) {
      await kv('zadd', 'flappy:leaderboard', String(score), clientId);
      await kv('hset', 'flappy:meta', clientId, nick);
      await kv('zremrangebyrank', 'flappy:leaderboard', '0', String(-1 - MAX_LEADERBOARD_SIZE));
    }
    return res.status(200).json({ enabled: true, ok: true, best: Math.max(score, currentBest) });
  } catch {
    return res.status(200).json({ enabled: false, ok: false });
  }
}
