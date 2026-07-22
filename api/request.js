/* Demande de titre / dedicace d'un auditeur, relayee UNIQUEMENT a l'admin
   Telegram (jamais postee directement dans le chat public — l'admin decide).
   L'admin peut y repondre depuis Telegram (bouton "↩️ Repondre" ou reponse
   native) : la reponse apparait alors dans le chat live sous Admin,
   grace au meme mapping chat:tgmap:<message_id> que api/chat.js.

   Sans bot configure (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID), renvoie
   { enabled:false } et le front masque le bouton Request.

   Anti-abus : filtre anti-liens + rate-limit 1 demande / 30 s / clientId. */
const LINK_RE = /(https?:\/\/|www\.|\b[a-z0-9-]+\.(com|net|org|fr|io|co|link|to|me|tv|info|biz|xyz|gg|app|shop))/i;

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(204).end();

  const botToken = process.env.TELEGRAM_BOT_TOKEN;
  const adminChat = process.env.TELEGRAM_CHAT_ID;
  if (!botToken || !adminChat) return res.status(200).json({ enabled: false });
  if (req.method !== 'POST') return res.status(200).json({ enabled: true });

  const base = process.env.KV_REST_API_URL;
  const kvToken = process.env.KV_REST_API_TOKEN;
  const kv = (base && kvToken)
    ? (...s) => fetch(`${base}/${s.map(encodeURIComponent).join('/')}`, { headers: { Authorization: `Bearer ${kvToken}` } }).then((r) => r.json())
    : null;

  const body = req.body || {};
  const clientId = (body.clientId || '').toString().slice(0, 64).replace(/[^a-zA-Z0-9_-]/g, '') || null;
  let nick = (body.nick || 'Listener').toString().slice(0, 30);
  if (/kalbassfm/i.test(nick)) nick = 'Listener';
  const text = (body.text || '').toString().trim().slice(0, 200);

  if (!clientId || !text) return res.status(200).json({ enabled: true, ok: false });
  if (LINK_RE.test(text)) return res.status(200).json({ enabled: true, ok: false, blocked: 'link' });

  if (kv) {
    try {
      const lock = await kv('set', `req:rate:${clientId}`, '1', 'EX', '30', 'NX');
      if (lock.result !== 'OK') return res.status(200).json({ enabled: true, ok: false, rateLimited: true });
    } catch {}
  }

  const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  try {
    const r = await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chat_id: adminChat,
        parse_mode: 'HTML',
        text: `🎵 <b>Request / shout-out</b>\n${escapeHtml(nick)}: ${escapeHtml(text)}\n<code>${escapeHtml(clientId)}</code>`,
        reply_markup: { inline_keyboard: [[
          { text: '↩️ Répondre', callback_data: 'rep:' + id },
          { text: '🔨 Bannir', callback_data: 'ban:' + clientId },
        ]] },
      }),
    });
    const j = await r.json().catch(() => null);
    const tgId = j && j.result && j.result.message_id;
    if (kv && tgId) {
      await kv('set', `chat:tgmap:${tgId}`, JSON.stringify({ id, nick, text }), 'EX', '259200');
    }
    return res.status(200).json({ enabled: true, ok: true });
  } catch {
    return res.status(200).json({ enabled: false, ok: false });
  }
}
