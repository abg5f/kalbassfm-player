/* Webhook du bot Telegram admin : skip morceau, message admin dans le chat live,
   suppression de message (bouton inline "Supprimer" envoye par api/chat.js).
   Un seul admin autorise (TELEGRAM_CHAT_ID). Sans TELEGRAM_BOT_TOKEN/SECRET
   configures, le webhook n'est de toute facon jamais appele par Telegram.

   Variables d'env requises :
   - TELEGRAM_BOT_TOKEN     : token BotFather
   - TELEGRAM_WEBHOOK_SECRET: verifie contre X-Telegram-Bot-Api-Secret-Token
   - TELEGRAM_CHAT_ID       : seul chat_id autorise a utiliser le bot
   - AZURACAST_API_KEY      : auth API AzuraCast (My API Keys) pour /skip
   - KV_REST_API_URL / KV_REST_API_TOKEN : memes que api/chat.js
*/
const AZURACAST_BASE = 'https://kalbassfm.duckdns.org';
const STATION = 'kalbassfm';

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'POST') return res.status(200).json({ ok: true });

  const secret = process.env.TELEGRAM_WEBHOOK_SECRET;
  if (!secret || req.headers['x-telegram-bot-api-secret-token'] !== secret) {
    return res.status(401).json({ ok: false });
  }

  const token = process.env.TELEGRAM_BOT_TOKEN;
  if (!token) return res.status(200).json({ ok: true });

  const update = req.body || {};

  try {
    if (update.callback_query) await handleCallback(token, update.callback_query);
    else if (update.message) await handleMessage(token, update.message);
  } catch {}

  return res.status(200).json({ ok: true });
}

async function handleMessage(token, message) {
  const chatId = message.chat && message.chat.id;
  const fromId = message.from && message.from.id;
  const text = (message.text || '').trim();
  const authorized = String(fromId) === String(process.env.TELEGRAM_CHAT_ID || '');

  if (!process.env.TELEGRAM_CHAT_ID) {
    return sendMessage(token, chatId, `Ton chat ID : ${fromId}\nAjoute-le comme TELEGRAM_CHAT_ID sur Vercel puis redeploie.`);
  }
  if (!authorized) return; // ignore silencieusement les expediteurs non autorises

  if (text === '/skip') {
    const r = await skipSong();
    if (r.ok) await postAdminMessage('⏭ Un admin a passé le morceau en cours.');
    return sendMessage(token, chatId, r.ok ? '⏭ Morceau suivant lance.' : `Echec du skip (${r.status}).`);
  }

  if (text.startsWith('/msg')) {
    const body = text.slice(4).trim();
    if (!body) return sendMessage(token, chatId, 'Usage : /msg <texte>');
    const ok = await postAdminMessage(body);
    return sendMessage(token, chatId, ok ? '✅ Message envoye dans le chat live.' : '❌ Echec de l\'envoi (store non configure ?).');
  }

  return sendMessage(token, chatId,
    'Commandes disponibles :\n/skip — passer au morceau suivant\n/msg <texte> — envoyer un message admin dans le chat live');
}

async function handleCallback(token, cb) {
  const fromId = cb.from && cb.from.id;
  const authorized = String(fromId) === String(process.env.TELEGRAM_CHAT_ID || '');
  if (!authorized) return;

  const data = cb.data || '';
  if (data.startsWith('del:')) {
    const id = data.slice(4);
    await markDeleted(id);
    await answerCallback(token, cb.id, 'Supprimé ✅');
    await editMessageMarkup(token, cb.message.chat.id, cb.message.message_id);
  } else {
    await answerCallback(token, cb.id, '');
  }
}

/* ---- AzuraCast ---- */
async function skipSong() {
  const apiKey = process.env.AZURACAST_API_KEY;
  if (!apiKey) return { ok: false, status: 'no-api-key' };
  const r = await fetch(`${AZURACAST_BASE}/api/station/${STATION}/backend/skip`, {
    method: 'POST',
    headers: { 'X-API-Key': apiKey },
  });
  return { ok: r.ok, status: r.status };
}

/* ---- Redis (memes cles que api/chat.js) ---- */
function kvClient() {
  const base = process.env.KV_REST_API_URL;
  const kvToken = process.env.KV_REST_API_TOKEN;
  if (!base || !kvToken) return null;
  const headers = { Authorization: `Bearer ${kvToken}` };
  return (...segments) => fetch(`${base}/${segments.map(encodeURIComponent).join('/')}`, { headers }).then((r) => r.json());
}

async function postAdminMessage(text) {
  const kv = kvClient();
  if (!kv) return false;
  const msg = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8), nick: '📻 KALBASSFM', text: text.slice(0, 200), ts: Date.now() };
  await kv('lpush', 'chat:messages', JSON.stringify(msg));
  await kv('ltrim', 'chat:messages', '0', '99');
  return true;
}

async function markDeleted(id) {
  const kv = kvClient();
  if (!kv || !id) return;
  await kv('hset', 'chat:deleted', id, '1');
}

/* ---- Telegram ---- */
async function sendMessage(token, chatId, text) {
  if (!chatId) return;
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text }),
  }).catch(() => {});
}

async function answerCallback(token, callbackId, text) {
  await fetch(`https://api.telegram.org/bot${token}/answerCallbackQuery`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ callback_query_id: callbackId, text }),
  }).catch(() => {});
}

async function editMessageMarkup(token, chatId, messageId) {
  await fetch(`https://api.telegram.org/bot${token}/editMessageReplyMarkup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, message_id: messageId, reply_markup: { inline_keyboard: [] } }),
  }).catch(() => {});
}
