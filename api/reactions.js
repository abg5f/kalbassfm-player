/* Votes 🔥 par morceau + classement Top 5, partages entre auditeurs.
   Utilise Vercel KV / Upstash Redis via son API REST (variables d'env
   KV_REST_API_URL + KV_REST_API_TOKEN, creees automatiquement quand on
   connecte un store KV au projet dans le dashboard Vercel).
   Sans store configure, renvoie { enabled:false } et le front bascule
   en mode local — jamais d'erreur visible.

   Vote plafonne a 10 par auditeur et par morceau (clientId anonyme, meme
   identifiant que le chat) — evite les chiffres qui grimpent a l'infini en
   spammant le bouton, tout en gardant le vote libre en dessous du plafond.

   "epoch" (compteur "top5:epoch") permet un reset instantane et repetable du
   Top 5 (commande /reset_top5 du bot Telegram) : le leaderboard et les
   plafonds par auditeur sont scopes par epoch, donc changer d'epoch les vide
   tous les deux sans avoir a lister/supprimer des cles individuellement.

   Structure Redis :
   - cle "top5:epoch"                    : entier, incremente a chaque reset
   - sorted set "leaderboard:<epoch>"    : score = votes, membre = id du morceau
   - hash "votes:<epoch>:<id>"           : votes par clientId pour ce morceau (plafond 10)
   - hash "meta:<id>"                    : title / artist / art (independant de l'epoch)
*/
const MAX_VOTES_PER_USER = 10;

async function getEpoch(kv) {
  const j = await kv('get', 'top5:epoch');
  return parseInt(j.result, 10) || 0;
}

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
      const epoch = await getEpoch(kv);
      const zj = await kv('zrange', `leaderboard:${epoch}`, '0', '4', 'REV', 'WITHSCORES');
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
      const epoch = await getEpoch(kv);
      const j = await kv('zscore', `leaderboard:${epoch}`, id);
      const count = parseInt(j.result ?? 0, 10) || 0;
      return res.status(200).json({ enabled: true, count });
    } catch {
      return res.status(200).json({ enabled: false, count: 0 });
    }
  }

  // ---- POST : voter pour un morceau (plafond 10 / auditeur / morceau) ----
  const body = req.body || {};
  const title = (body.title || '').toString().slice(0, 200);
  const artist = (body.artist || '').toString().slice(0, 200);
  const art = (body.art || '').toString().slice(0, 500);
  const clientId = (body.clientId || '').toString().slice(0, 64).replace(/[^a-zA-Z0-9_-]/g, '') || null;

  try {
    const epoch = await getEpoch(kv);

    // clientId obligatoire pour voter : sans lui, impossible d'appliquer le
    // plafond par auditeur (contournable sinon en omettant simplement le
    // champ — un vieux front en cache qui ne l'envoie pas encore, par
    // exemple). On renvoie le score reel actuel pour ne pas faire redescendre
    // l'affichage a 0 chez ce client.
    if (!clientId) {
      const j = await kv('zscore', `leaderboard:${epoch}`, id);
      const count = parseInt(j.result ?? 0, 10) || 0;
      return res.status(200).json({ enabled: true, count, ok: false });
    }

    const votesKey = `votes:${epoch}:${id}`;
    const uj = await kv('hincrby', votesKey, clientId, '1');
    const userCount = parseInt(uj.result, 10) || 0;
    if (userCount > MAX_VOTES_PER_USER) {
      await kv('hincrby', votesKey, clientId, '-1'); // annule le vote en trop
      const j = await kv('zscore', `leaderboard:${epoch}`, id);
      const count = parseInt(j.result ?? 0, 10) || 0;
      return res.status(200).json({ enabled: true, count, capped: true });
    }
    await kv('expire', votesKey, '2592000'); // 30 jours, borne la croissance

    await kv('zincrby', `leaderboard:${epoch}`, '1', id);
    const fields = [];
    if (title) fields.push('title', title);
    if (artist) fields.push('artist', artist);
    if (art) fields.push('art', art);
    if (fields.length) await kv('hset', `meta:${id}`, ...fields);

    // Compteur quotidien (jour Martinique UTC-4) lu par /stats du bot Telegram.
    const day = new Date(Date.now() - 4 * 3600 * 1000).toISOString().slice(0, 10);
    await kv('incr', `stats:vote:${day}`);
    await kv('expire', `stats:vote:${day}`, '172800');

    const j = await kv('zscore', `leaderboard:${epoch}`, id);
    const count = parseInt(j.result ?? 0, 10) || 0;
    return res.status(200).json({ enabled: true, count });
  } catch {
    return res.status(200).json({ enabled: false, count: 0 });
  }
}
