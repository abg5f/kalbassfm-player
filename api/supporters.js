/* Webhook Buy Me a Coffee : remerciement automatique dans le chat live +
   liste des supporters recents, a chaque don recu.

   Variables d'env requises :
   - BMC_WEBHOOK_SECRET      : secret de signature genere dans BMC Studio > Integrations > Webhooks
   - KV_REST_API_URL / KV_REST_API_TOKEN : memes que api/chat.js (Redis)
   - TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID : optionnel, notif admin (memes que api/chat.js)

   Verification de signature : BMC envoie un header x-signature-sha256 =
   HMAC-SHA256(corps brut, secret). Le corps brut doit etre lu manuellement
   AVANT tout acces a req.body (le parseur JSON de Vercel est un getter
   paresseux qui consomme le flux) — sinon impossible de recalculer le hash
   sur exactement les memes octets que ceux signes par BMC.

   Les noms de champs exacts de l'evenement "donation.created" ne sont pas
   confirmes publiquement (doc complete derriere connexion BMC) : extraction
   tolerante de plusieurs cles plausibles, avec repli generique si rien n'est
   trouve — mieux vaut un message vague qu'aucun message.

   Structure Redis :
   - liste "supporters"    : JSON {id, name, message, ts}, LPUSH + LTRIM a 49
   - liste "chat:messages" : meme schema que api/chat.js (message admin de remerciement)
*/
import crypto from 'node:crypto';

function readRawBody(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', (chunk) => { data += chunk; });
    req.on('end', () => resolve(data));
    req.on('error', reject);
  });
}

function verifySignature(rawBody, signature, secret) {
  if (!signature || !secret) return false;
  const expected = crypto.createHmac('sha256', secret).update(rawBody).digest('hex');
  const a = Buffer.from(expected);
  const b = Buffer.from(String(signature));
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(204).end();

  const base = process.env.KV_REST_API_URL;
  const kvToken = process.env.KV_REST_API_TOKEN;
  if (!base || !kvToken) return res.status(200).json({ enabled: false, supporters: [] });

  const headers = { Authorization: `Bearer ${kvToken}` };
  const kv = (...segments) => fetch(`${base}/${segments.map(encodeURIComponent).join('/')}`, { headers }).then((r) => r.json());

  // ---- GET : derniers supporters (lecture publique, comme api/chat.js) ----
  if (req.method === 'GET') {
    try {
      const lj = await kv('lrange', 'supporters', '0', '19');
      const supporters = (lj.result || [])
        .map((s) => { try { return JSON.parse(s); } catch { return null; } })
        .filter(Boolean);
      return res.status(200).json({ enabled: true, supporters });
    } catch {
      return res.status(200).json({ enabled: false, supporters: [] });
    }
  }

  // ---- POST : webhook Buy Me a Coffee ----
  if (req.method !== 'POST') return res.status(405).json({ ok: false });

  const rawBody = await readRawBody(req);
  const signature = req.headers['x-signature-sha256'];
  if (!verifySignature(rawBody, signature, process.env.BMC_WEBHOOK_SECRET)) {
    return res.status(401).json({ ok: false });
  }

  let payload;
  try { payload = JSON.parse(rawBody); } catch { return res.status(400).json({ ok: false }); }

  // On ignore tout ce qui n'est pas un don, mais on repond 200 quand meme :
  // un 4xx/5xx ferait passer ca pour un echec de livraison cote BMC (webhook
  // desactive automatiquement au bout de 10 echecs consecutifs).
  if (payload.type !== 'donation.created') return res.status(200).json({ ok: true, ignored: true });

  const data = payload.data || {};
  const rawName = data.supporter_name || data.payer_name || data.name || '';
  const rawMessage = data.support_note || data.message || data.note || data.support_message || '';
  const name = String(rawName).slice(0, 60).trim() || 'A listener';
  const message = String(rawMessage).slice(0, 200).trim();

  try {
    const id = (payload.event_id || Date.now()).toString(36) + Math.random().toString(36).slice(2, 8);

    const entry = { id, name, message, ts: Date.now() };
    await kv('lpush', 'supporters', JSON.stringify(entry));
    await kv('ltrim', 'supporters', '0', '49');

    // admin:true est pose UNIQUEMENT cote serveur, meme convention que
    // partout ailleurs (api/telegram.js, api/chat.js) — affiche en gras.
    const thankYou = message ? `☕ Thanks ${name} for the coffee! "${message}"` : `☕ Thanks ${name} for the coffee!`;
    const chatMsg = { id, nick: '📻 KALBASSFM', text: thankYou.slice(0, 200), ts: Date.now(), admin: true };
    await kv('lpush', 'chat:messages', JSON.stringify(chatMsg));
    await kv('ltrim', 'chat:messages', '0', '99');

    await notifyTelegram(name, message);
    return res.status(200).json({ ok: true });
  } catch {
    // 200 malgre l'echec cote nous : un retry BMC ne resoudra pas une panne
    // Redis, autant eviter d'epuiser le quota de tentatives pour rien.
    return res.status(200).json({ ok: false });
  }
}

async function notifyTelegram(name, message) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) return;
  try {
    const text = `☕ New Buy Me a Coffee supporter: ${escapeHtml(name)}` + (message ? `\n"${escapeHtml(message)}"` : '');
    await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, parse_mode: 'HTML', text }),
    });
  } catch {}
}
