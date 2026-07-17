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

  // Reponse native Telegram ("Repondre") a une notification de message du
  // chat live : postee comme reponse admin, citation du message d'origine.
  // Prioritaire sur les commandes ci-dessous (une reponse n'a pas a commencer
  // par "/"). Si le message repondu n'est pas dans le mapping (notification
  // trop vieille, ou reponse a autre chose qu'un message de chat), on retombe
  // sur le traitement normal.
  if (message.reply_to_message && text) {
    const orig = await getTgMap(message.reply_to_message.message_id);
    if (orig) {
      const id = await postAdminReply(text, orig);
      return confirmWithDelete(token, chatId, '↩️ Réponse envoyée dans le chat live.', id);
    }
  }

  // Reponse via le bouton "↩️ Repondre" : l'admin a clique le bouton, on lui a
  // demande d'ecrire sa reponse ; son prochain message texte simple (hors
  // commande) est consomme ici comme reponse admin dans le chat live.
  if (text && !text.startsWith('/')) {
    const pending = await takePendingReply(fromId);
    if (pending) {
      const id = await postAdminReply(text, pending);
      return confirmWithDelete(token, chatId, '↩️ Réponse envoyée dans le chat live.', id);
    }
  }

  if (text === '/skip') {
    const r = await skipSong();
    if (r.ok) await postAdminMessage('⏭ An admin skipped the current track.');
    return sendMessage(token, chatId, r.ok ? '⏭ Morceau suivant lance.' : `Echec du skip (${r.status}).`);
  }

  if (text.startsWith('/msg')) {
    const body = text.slice(4).trim();
    if (!body) return sendMessage(token, chatId, 'Usage : /msg <texte>');
    const id = await postAdminMessage(body);
    return confirmWithDelete(token, chatId, '✅ Message envoyé dans le chat live.', id);
  }

  if (text === '/jingle') {
    const r = await triggerJingle();
    return sendMessage(token, chatId, r.message);
  }

  if (text.startsWith('/ban')) {
    const id = text.slice(4).trim();
    if (!id) return sendMessage(token, chatId, 'Usage : /ban <clientId> (copie-le depuis une notification de chat)');
    const ok = await setBanned(id, true);
    return sendMessage(token, chatId, ok ? `🔨 Banni : ${id}` : '❌ Echec (store non configure ?).');
  }

  if (text.startsWith('/unban')) {
    const id = text.slice(6).trim();
    if (!id) return sendMessage(token, chatId, 'Usage : /unban <clientId>');
    const ok = await setBanned(id, false);
    return sendMessage(token, chatId, ok ? `✅ Debanni : ${id}` : '❌ Echec (store non configure ?).');
  }

  if (text === '/pause_chat') {
    const ok = await setPaused(true);
    return sendMessage(token, chatId, ok ? '⏸ Chat en pause — plus personne ne peut poster.' : '❌ Echec (store non configure ?).');
  }

  if (text === '/resume_chat') {
    const ok = await setPaused(false);
    return sendMessage(token, chatId, ok ? '▶️ Chat réactivé.' : '❌ Echec (store non configure ?).');
  }

  if (text === '/np') {
    return sendMessage(token, chatId, await nowPlayingText());
  }

  if (text === '/stats') {
    return sendMessage(token, chatId, await statsText());
  }

  if (text.startsWith('/pin')) {
    const body = text.slice(4).trim();
    if (!body) return sendMessage(token, chatId, 'Usage : /pin <texte> (annonce épinglée en haut du chat)');
    const ok = await setPinned(body);
    return sendMessage(token, chatId, ok ? '📌 Annonce épinglée dans le chat.' : '❌ Echec (store non configure ?).');
  }

  if (text === '/unpin') {
    const ok = await setPinned(null);
    return sendMessage(token, chatId, ok ? '✅ Annonce dépinglée.' : '❌ Echec (store non configure ?).');
  }

  if (text === '/recent') {
    const msgs = await getRecentMessages(10);
    if (!msgs.length) return sendMessage(token, chatId, 'Aucun message à afficher.');
    // Liste numerotee + un bouton "🗑 N" par message (auditeurs ET bot/auto),
    // ce qui permet de supprimer les annonces automatiques et les messages
    // admin, qui n'ont pas de notification individuelle. Apres une suppression,
    // les boutons de ce message disparaissent (comportement partage avec les
    // notifications) : relancer /recent rafraichit la liste sans le supprime.
    const lines = msgs.map((m, i) => `${i + 1}. ${m.nick}: ${m.text}`);
    const buttons = msgs.map((m, i) => ({ text: '🗑 ' + (i + 1), callback_data: 'del:' + m.id }));
    const rows = [];
    for (let i = 0; i < buttons.length; i += 3) rows.push(buttons.slice(i, i + 3));
    return sendMessage(token, chatId, 'Derniers messages du chat :\n' + lines.join('\n'), {
      reply_markup: { inline_keyboard: rows },
    });
  }

  return sendMessage(token, chatId,
    'Commandes disponibles :\n' +
    '/skip — passer au morceau suivant\n' +
    '/msg <texte> — envoyer un message admin dans le chat live\n' +
    '/jingle — declencher un jingle (best effort)\n' +
    '/ban <clientId> / /unban <clientId> — bloquer/debloquer un auditeur\n' +
    '/pause_chat / /resume_chat — couper/reactiver le chat\n' +
    '/np — morceau en cours + auditeurs\n' +
    '/stats — auditeurs, messages et votes du jour\n' +
    '/pin <texte> / /unpin — epingler/retirer une annonce en haut du chat\n' +
    '/recent — lister les 10 derniers messages avec un bouton pour les supprimer\n' +
    'Astuce : clique le bouton "↩️ Repondre" sous une notification de message pour y repondre, sous 📻 KALBASSFM.');
}

async function handleCallback(token, cb) {
  const fromId = cb.from && cb.from.id;
  const authorized = String(fromId) === String(process.env.TELEGRAM_CHAT_ID || '');
  if (!authorized) return;

  const data = cb.data || '';
  if (data.startsWith('rep:')) {
    // On retrouve le message d'origine via le message_id Telegram de la
    // notification elle-meme (le mapping pose par api/chat.js), puis on arme
    // un etat "reponse en attente" : le prochain message texte de l'admin
    // sera poste comme reponse dans le chat live.
    const orig = await getTgMap(cb.message.message_id);
    if (!orig) return answerCallback(token, cb.id, 'Message introuvable (trop ancien).');
    await setPendingReply(fromId, orig);
    await answerCallback(token, cb.id, 'Écris ta réponse maintenant');
    await sendMessage(token, cb.message.chat.id,
      `✍️ Écris ta réponse à « ${orig.nick} » — je la posterai dans le chat live sous 📻 KALBASSFM.`,
      { reply_markup: { force_reply: true } });
  } else if (data.startsWith('del:')) {
    const id = data.slice(4);
    await markDeleted(id);
    await answerCallback(token, cb.id, 'Supprimé ✅');
    await editMessageMarkup(token, cb.message.chat.id, cb.message.message_id);
  } else if (data.startsWith('ban:')) {
    const id = data.slice(4);
    await setBanned(id, true);
    await answerCallback(token, cb.id, 'Banni ✅');
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

// Best effort : AzuraCast n'a pas d'API "jouer immediatement", seule l'API
// Requests existe (queue le morceau, pas instantane, peut refuser un jingle
// rejoue trop recemment). Necessite "Autoriser les demandes" active sur la
// playlist Jingles dans AzuraCast.
// AzuraCast refuse les demandes envoyees sans User-Agent credible (detection
// anti-robots/crawlers cote SubmitAction) — un appel serveur sans navigateur
// derriere doit donc se presenter comme tel.
const BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

async function triggerJingle() {
  const apiKey = process.env.AZURACAST_API_KEY;
  try {
    const listRes = await fetch(`${AZURACAST_BASE}/api/station/${STATION}/requests`, {
      headers: { 'User-Agent': BROWSER_UA, ...(apiKey ? { 'X-API-Key': apiKey } : {}) },
    });
    if (!listRes.ok) return { message: `Echec de la liste des demandes (${listRes.status}).` };
    const list = await listRes.json();
    // Les jingles sont des voix off dont le titre est le texte lu (pas de nom
    // generique "jingle") : "kalbass fm" est le marqueur fiable commun aux 15,
    // absent de tous les autres morceaux demandables (verifie manuellement).
    const jingles = (Array.isArray(list) ? list : []).filter((r) => {
      const song = r.song || {};
      const hay = `${song.title || ''} ${song.artist || ''}`.toLowerCase();
      return hay.includes('kalbass fm');
    });
    if (!jingles.length) {
      return { message: 'Aucun jingle trouvable — vérifie que la playlist Jingles autorise les demandes dans AzuraCast.' };
    }
    const pick = jingles[Math.floor(Math.random() * jingles.length)];
    const subRes = await fetch(`${AZURACAST_BASE}/api/station/${STATION}/request/${encodeURIComponent(pick.request_id)}`, {
      method: 'POST',
      headers: { 'User-Agent': BROWSER_UA, ...(apiKey ? { 'X-API-Key': apiKey } : {}) },
    });
    const sub = await subRes.json().catch(() => ({}));
    return { message: sub.message || (subRes.ok ? '🎙 Jingle demandé.' : `Echec (${subRes.status}).`) };
  } catch {
    return { message: '❌ Erreur réseau vers AzuraCast.' };
  }
}

async function nowPlaying() {
  try {
    const r = await fetch(`${AZURACAST_BASE}/api/nowplaying/${STATION}`, {
      headers: { 'User-Agent': BROWSER_UA },
    });
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; }
}

async function nowPlayingText() {
  const d = await nowPlaying();
  if (!d) return '❌ Impossible de joindre AzuraCast.';
  const song = (d.now_playing && d.now_playing.song) || {};
  const label = song.title ? `${song.artist || ''} — ${song.title}`.trim() : '(inconnu)';
  const lc = (d.listeners && (d.listeners.current ?? d.listeners.total)) ?? 0;
  return `▶️ En cours : ${label}\n🎧 Auditeurs : ${lc}`;
}

async function statsText() {
  const kv = kvClient();
  const day = new Date(Date.now() - 4 * 3600 * 1000).toISOString().slice(0, 10);
  const [d, msgJ, voteJ] = await Promise.all([
    nowPlaying(),
    kv ? kv('get', `stats:msg:${day}`) : Promise.resolve({ result: null }),
    kv ? kv('get', `stats:vote:${day}`) : Promise.resolve({ result: null }),
  ]);
  const lc = (d && d.listeners && (d.listeners.current ?? d.listeners.total)) ?? '?';
  const uniq = (d && d.listeners && d.listeners.unique) ?? '?';
  const msgs = (msgJ && msgJ.result) || 0;
  const votes = (voteJ && voteJ.result) || 0;
  return `📊 Stats du ${day} (UTC-4)\n` +
    `🎧 Auditeurs maintenant : ${lc} (uniques ${uniq})\n` +
    `💬 Messages du chat aujourd'hui : ${msgs}\n` +
    `🔥 Votes aujourd'hui : ${votes}`;
}

/* ---- Redis (memes cles que api/chat.js) ---- */
function kvClient() {
  const base = process.env.KV_REST_API_URL;
  const kvToken = process.env.KV_REST_API_TOKEN;
  if (!base || !kvToken) return null;
  const headers = { Authorization: `Bearer ${kvToken}` };
  return (...segments) => fetch(`${base}/${segments.map(encodeURIComponent).join('/')}`, { headers }).then((r) => r.json());
}

// Retourne l'id du message poste (pour proposer un bouton de suppression), ou
// null si le store n'est pas configure.
async function postAdminMessage(text) {
  const kv = kvClient();
  if (!kv) return null;
  // admin:true est pose UNIQUEMENT ici (cote serveur) — le front l'utilise pour
  // mettre le message en valeur, un client ne peut pas le forger.
  const msg = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8), nick: '📻 KALBASSFM', text: text.slice(0, 200), ts: Date.now(), admin: true };
  await kv('lpush', 'chat:messages', JSON.stringify(msg));
  await kv('ltrim', 'chat:messages', '0', '99');
  return msg.id;
}

async function getTgMap(tgMessageId) {
  const kv = kvClient();
  if (!kv || !tgMessageId) return null;
  const j = await kv('get', `chat:tgmap:${tgMessageId}`);
  if (!j || !j.result) return null;
  try { return JSON.parse(j.result); } catch { return null; }
}

async function postAdminReply(text, orig) {
  const kv = kvClient();
  if (!kv) return null;
  const msg = {
    id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
    nick: '📻 KALBASSFM',
    text: text.slice(0, 200),
    ts: Date.now(),
    admin: true,
    replyTo: { id: orig.id, nick: orig.nick, text: (orig.text || '').slice(0, 120) },
  };
  await kv('lpush', 'chat:messages', JSON.stringify(msg));
  await kv('ltrim', 'chat:messages', '0', '99');
  return msg.id;
}

// Etat "reponse en attente" pose au clic du bouton Repondre, consomme au
// message suivant. TTL court (3 min) : si l'admin ne repond pas tout de suite,
// l'etat expire et un message ulterieur ne part pas par erreur dans le chat.
async function setPendingReply(fromId, orig) {
  const kv = kvClient();
  if (!kv || !fromId) return;
  await kv('set', `chat:pendingreply:${fromId}`, JSON.stringify(orig), 'EX', '180');
}

async function takePendingReply(fromId) {
  const kv = kvClient();
  if (!kv || !fromId) return null;
  const j = await kv('get', `chat:pendingreply:${fromId}`);
  if (!j || !j.result) return null;
  await kv('del', `chat:pendingreply:${fromId}`); // usage unique
  try { return JSON.parse(j.result); } catch { return null; }
}

// Derniers messages encore visibles (deja-supprimes filtres), pour /recent.
async function getRecentMessages(n) {
  const kv = kvClient();
  if (!kv) return [];
  const [lj, dj] = await Promise.all([
    kv('lrange', 'chat:messages', '0', String(n - 1)),
    kv('hgetall', 'chat:deleted'),
  ]);
  const raw = lj.result || [];
  const deletedFields = dj.result || [];
  const deleted = new Set();
  for (let i = 0; i < deletedFields.length; i += 2) deleted.add(deletedFields[i]);
  return raw
    .map((s) => { try { return JSON.parse(s); } catch { return null; } })
    .filter((m) => m && !deleted.has(m.id));
}

async function markDeleted(id) {
  const kv = kvClient();
  if (!kv || !id) return;
  await kv('hset', 'chat:deleted', id, '1');
}

async function setBanned(clientId, banned) {
  const kv = kvClient();
  if (!kv || !clientId) return false;
  await kv(banned ? 'sadd' : 'srem', 'chat:banned', clientId);
  return true;
}

async function setPaused(paused) {
  const kv = kvClient();
  if (!kv) return false;
  if (paused) await kv('set', 'chat:paused', '1');
  else await kv('del', 'chat:paused');
  return true;
}

async function setPinned(text) {
  const kv = kvClient();
  if (!kv) return false;
  if (text) await kv('set', 'chat:pinned', text.slice(0, 200));
  else await kv('del', 'chat:pinned');
  return true;
}

/* ---- Telegram ---- */
// Confirmation d'un message admin poste, avec un bouton "🗑 Supprimer" quand
// l'envoi a reussi (id non nul) pour pouvoir retirer immediatement ce qu'on
// vient de poster (reponse, /msg).
function confirmWithDelete(token, chatId, okLabel, id) {
  if (!id) return sendMessage(token, chatId, '❌ Échec de l\'envoi (store non configuré ?).');
  return sendMessage(token, chatId, okLabel, {
    reply_markup: { inline_keyboard: [[{ text: '🗑 Supprimer', callback_data: 'del:' + id }]] },
  });
}

async function sendMessage(token, chatId, text, extra) {
  if (!chatId) return;
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, ...(extra || {}) }),
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
