/* Chat live anonyme entre auditeurs, partage via Vercel Storage / Upstash Redis
   (variables d'env KV_REST_API_URL + KV_REST_API_TOKEN, memes que api/reactions.js).
   Sans store configure, renvoie { enabled:false } et le front bascule en mode
   degrade (panneau masque) — jamais d'erreur visible.

   Pas d'identification : chaque auditeur a un clientId anonyme genere cote
   navigateur (localStorage), utilise pour le pseudo affiche et le rate-limit.

   Structure Redis :
   - liste "chat:messages"       : JSON {id, nick, text, ts} par entree, LPUSH + LTRIM a 99
   - cle "chat:rate:<clientId>"  : pose avec EX 3 NX, bloque l'envoi suivant pendant 3s

   Anti-autopromo : tout message contenant un lien (http(s)://, www., ou un
   domaine du type "motacle.com") est refuse avant meme le rate-limit — pas
   de bannissement, juste un refus systematique des liens dans le chat.
*/
const LINK_RE = /(https?:\/\/|www\.|\b[a-z0-9-]+\.(com|net|org|fr|io|co|link|to|me|tv|info|biz|xyz|gg|app|shop))/i;
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(204).end();

  const base = process.env.KV_REST_API_URL;
  const token = process.env.KV_REST_API_TOKEN;
  if (!base || !token) return res.status(200).json({ enabled: false, messages: [] });

  const headers = { Authorization: `Bearer ${token}` };
  const kv = (...segments) => fetch(`${base}/${segments.map(encodeURIComponent).join('/')}`, { headers }).then(r => r.json());

  // ---- GET : les 50 derniers messages (plus recent en premier) ----
  if (req.method === 'GET') {
    try {
      const [lj, dj] = await Promise.all([
        kv('lrange', 'chat:messages', '0', '49'),
        kv('hgetall', 'chat:deleted'),
      ]);
      const raw = lj.result || [];
      const deletedFields = dj.result || [];
      const deletedIds = new Set();
      for (let i = 0; i < deletedFields.length; i += 2) deletedIds.add(deletedFields[i]);
      const messages = raw
        .map((s) => { try { return JSON.parse(s); } catch { return null; } })
        .filter((m) => m && !deletedIds.has(m.id));
      return res.status(200).json({ enabled: true, messages });
    } catch {
      return res.status(200).json({ enabled: false, messages: [] });
    }
  }

  // ---- POST : envoyer un message (rate-limit serveur 1 / 3s / clientId) ----
  const body = req.body || {};
  const rawClientId = (body.clientId || '').toString();
  const clientId = rawClientId.slice(0, 64).replace(/[^a-zA-Z0-9_-]/g, '') || null;
  const nick = (body.nick || 'Auditeur').toString().slice(0, 30);
  const text = (body.text || '').toString().trim().slice(0, 200);

  if (!clientId || !text) return res.status(200).json({ enabled: true, ok: false });

  try {
    const [pausedJ, bannedJ] = await Promise.all([
      kv('get', 'chat:paused'),
      kv('sismember', 'chat:banned', clientId),
    ]);
    if (pausedJ.result) return res.status(200).json({ enabled: true, ok: false, paused: true });
    if (bannedJ.result) return res.status(200).json({ enabled: true, ok: false, banned: true });
  } catch {
    return res.status(200).json({ enabled: false, ok: false });
  }

  if (LINK_RE.test(text)) return res.status(200).json({ enabled: true, ok: false, blocked: 'link' });

  try {
    const lockJ = await kv('set', `chat:rate:${clientId}`, '1', 'EX', '3', 'NX');
    if (lockJ.result !== 'OK') return res.status(200).json({ enabled: true, ok: false, rateLimited: true });

    const msg = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8), nick, text, ts: Date.now() };
    await kv('lpush', 'chat:messages', JSON.stringify(msg));
    await kv('ltrim', 'chat:messages', '0', '99');
    await notifyTelegram(msg, clientId);
    return res.status(200).json({ enabled: true, ok: true });
  } catch {
    return res.status(200).json({ enabled: false, ok: false });
  }
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
}

// Relaie chaque nouveau message vers l'admin Telegram avec des boutons inline
// "Supprimer" / "Bannir" (par clientId, le meme identifiant que le rate-limit
// ci-dessus — le pseudo affiche est falsifiable par le client, pas le clientId
// utilise ailleurs comme source de verite). No-op silencieux si le bot n'est
// pas configure ou en cas d'erreur reseau : la publication du message dans le
// chat ne doit jamais en dependre.
async function notifyTelegram(msg, clientId) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) return;
  try {
    await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: `${escapeHtml(msg.nick)}: ${escapeHtml(msg.text)}\n<code>${escapeHtml(clientId)}</code>`,
        reply_markup: { inline_keyboard: [[
          { text: '🗑 Supprimer', callback_data: 'del:' + msg.id },
          { text: '🔨 Bannir', callback_data: 'ban:' + clientId },
        ]] },
      }),
    });
  } catch {}
}
