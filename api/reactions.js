/* Compteur de 🔥 partagé par morceau.
   Utilise Vercel KV / Upstash Redis via son API REST (variables d'env
   KV_REST_API_URL + KV_REST_API_TOKEN, créées automatiquement quand on
   connecte un store KV au projet dans le dashboard Vercel).
   Sans store configuré, renvoie { enabled:false } et le front bascule
   en mode local — jamais d'erreur visible. */
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(204).end();

  const base = process.env.KV_REST_API_URL;
  const token = process.env.KV_REST_API_TOKEN;
  if (!base || !token) return res.status(200).json({ enabled: false, count: 0 });

  const raw = (req.query.id || (req.body && req.body.id) || '').toString();
  const id = raw.slice(0, 120).replace(/[^a-zA-Z0-9_-]/g, '_') || 'unknown';
  const key = `react:${id}`;
  const headers = { Authorization: `Bearer ${token}` };

  try {
    const path = req.method === 'POST' ? `incr/${key}` : `get/${key}`;
    const r = await fetch(`${base}/${path}`, { headers });
    const j = await r.json();
    const count = parseInt(j.result ?? 0, 10) || 0;
    return res.status(200).json({ enabled: true, count });
  } catch {
    return res.status(200).json({ enabled: false, count: 0 });
  }
}
