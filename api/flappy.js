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

// Plafond par IP, le clientId etant choisi par le navigateur (cf. api/chat.js).
async function ipFlood(kv, req, prefix, max, windowSec) {
  const raw = (req.headers['x-forwarded-for'] || '').toString().split(',')[0].trim();
  const ip = raw.replace(/[^0-9a-f.:]/gi, '');
  if (!ip) return false;
  const key = `${prefix}:ip:${ip}`;
  const n = await kv('incr', key);
  if (n.result === 1) await kv('expire', key, String(windowSec));
  return (n.result || 0) > max;
}

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
      // Plafond a 10 (ce que le player demande) et UN seul hmget pour les
      // pseudos : avant, ?top=50 declenchait 51 commandes Redis par appel,
      // sans limite, a la portee de n'importe quel curl.
      const n = Math.min(parseInt(req.query.top, 10) || 10, 10);
      const zj = await kv('zrange', 'flappy:leaderboard', '0', String(n - 1), 'REV', 'WITHSCORES');
      if (zj.result === undefined) throw new Error('kv-error');
      const raw = zj.result || [];
      const ids = [], scores = [];
      for (let i = 0; i < raw.length; i += 2) { ids.push(raw[i]); scores.push(parseInt(raw[i + 1], 10) || 0); }
      const nicks = ids.length ? ((await kv('hmget', 'flappy:meta', ...ids)).result || []) : [];
      const top = ids.map((_, i) => ({ nick: nicks[i] || 'Listener', score: scores[i] }));
      return res.status(200).json({ enabled: true, top });
    } catch {
      return res.status(200).json({ enabled: false, top: [] });
    }
  }

  // ---- POST : soumettre un score (garde seulement le meilleur par clientId) ----
  const body = req.body || {};
  const clientId = (body.clientId || '').toString().slice(0, 64).replace(/[^a-zA-Z0-9_-]/g, '') || null;
  // Memes pseudos reserves que le chat : le classement est public lui aussi.
  let nick = (body.nick || 'Listener').toString().trim().slice(0, 30) || 'Listener';
  if (/kalbassfm|^admin$|^bpm\s*guesser$/i.test(nick)) nick = 'Listener';
  const score = Math.max(0, Math.min(MAX_SCORE, parseInt(body.score, 10) || 0));

  if (!clientId || score <= 0) return res.status(200).json({ enabled: true, ok: false });

  try {
    if (await ipFlood(kv, req, 'flappy', 30, 60)) return res.status(200).json({ enabled: true, ok: false, rateLimited: true });
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
