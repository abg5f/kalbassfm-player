/* Votes 🔥 par morceau + classement Top 5, partages entre auditeurs.
   Utilise Vercel KV / Upstash Redis via son API REST (variables d'env
   KV_REST_API_URL + KV_REST_API_TOKEN, creees automatiquement quand on
   connecte un store KV au projet dans le dashboard Vercel).
   Sans store configure, renvoie { enabled:false } et le front bascule
   en mode local — jamais d'erreur visible.

   Votes libres : pas de limite par auditeur, chacun peut voter autant de
   fois qu'il veut pour faire monter un morceau dans le classement.

   Structure Redis :
   - sorted set "leaderboard"  : score = nombre de votes, membre = id du morceau
   - hash "meta:<id>"          : title / artist / art du morceau (pour le Top 5)
*/
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(204).end();

  const base = process.env.KV_REST_API_URL;
  const token = process.env.KV_REST_API_TOKEN;
  if (!base || !token) return res.status(200).json({ enabled: false, count: 0, top: [] });

  const headers = { Authorization: `Bearer ${token}` };
  const kv = (...segments) => fetch(`${base}/${segments.map(encodeURIComponent).join('/')}`, { headers }).then(r => r.json());

  // ---- GET ?top=5 : classement des morceaux les plus votes ----
  if (req.method === 'GET' && req.query.top) {
    try {
      const zj = await kv('zrange', 'leaderboard', '0', '4', 'REV', 'WITHSCORES');
      const raw = zj.result || [];
      const top = [];
      for (let i = 0; i < raw.length; i += 2) {
        const id = raw[i];
        const count = parseInt(raw[i + 1], 10) || 0;
        const mj = await kv('hgetall', `meta:${id}`);
        const fields = mj.result || [];
        const meta = {};
        for (let k = 0; k < fields.length; k += 2) meta[fields[k]] = fields[k + 1];
        top.push({ id, count, title: meta.title || '', artist: meta.artist || '', art: meta.art || '' });
      }
      return res.status(200).json({ enabled: true, top });
    } catch {
      return res.status(200).json({ enabled: false, top: [] });
    }
  }

  const rawId = (req.query.id || (req.body && req.body.id) || '').toString();
  const id = rawId.slice(0, 120).replace(/[^a-zA-Z0-9_-]/g, '_') || 'unknown';

  // ---- GET ?id=... : score actuel d'un morceau ----
  if (req.method === 'GET') {
    try {
      const j = await kv('zscore', 'leaderboard', id);
      const count = parseInt(j.result ?? 0, 10) || 0;
      return res.status(200).json({ enabled: true, count });
    } catch {
      return res.status(200).json({ enabled: false, count: 0 });
    }
  }

  // ---- POST : voter pour un morceau (votes libres, sans limite) ----
  const body = req.body || {};
  const title = (body.title || '').toString().slice(0, 200);
  const artist = (body.artist || '').toString().slice(0, 200);
  const art = (body.art || '').toString().slice(0, 500);

  try {
    await kv('zincrby', 'leaderboard', '1', id);
    const fields = [];
    if (title) fields.push('title', title);
    if (artist) fields.push('artist', artist);
    if (art) fields.push('art', art);
    if (fields.length) await kv('hset', `meta:${id}`, ...fields);

    // Compteur quotidien (jour Martinique UTC-4) lu par /stats du bot Telegram.
    const day = new Date(Date.now() - 4 * 3600 * 1000).toISOString().slice(0, 10);
    await kv('incr', `stats:vote:${day}`);
    await kv('expire', `stats:vote:${day}`, '172800');

    const j = await kv('zscore', 'leaderboard', id);
    const count = parseInt(j.result ?? 0, 10) || 0;
    return res.status(200).json({ enabled: true, count });
  } catch {
    return res.status(200).json({ enabled: false, count: 0 });
  }
}
