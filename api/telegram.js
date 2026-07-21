/* Webhook du bot Telegram admin : skip morceau, message admin dans le chat live,
   suppression de message (bouton inline "Supprimer" envoye par api/chat.js).
   Un seul admin autorise (TELEGRAM_CHAT_ID). Sans TELEGRAM_BOT_TOKEN/SECRET
   configures, le webhook n'est de toute facon jamais appele par Telegram.

   Variables d'env requises :
   - TELEGRAM_BOT_TOKEN     : token BotFather
   - TELEGRAM_WEBHOOK_SECRET: verifie contre X-Telegram-Bot-Api-Secret-Token
   - TELEGRAM_CHAT_ID       : seul chat_id autorise a utiliser le bot
   - AZURACAST_API_KEY      : auth API AzuraCast (My API Keys) pour /skip, /jingle, /delete_track
   - KV_REST_API_URL / KV_REST_API_TOKEN : memes que api/chat.js
   - ANTHROPIC_API_KEY      : cle API Claude (console.anthropic.com) pour /ask
*/
const AZURACAST_BASE = 'https://kalbassfm.duckdns.org';
const STATION = 'kalbassfm';

// Marge large : les autres commandes (AzuraCast, Redis) sont deja rapides,
// mais /ask attend une reponse Claude avant de repondre a Telegram — sur le
// plan Vercel Hobby ce champ est plafonne a 10s de toute facon (ignore
// silencieusement au-dela), sur Pro il autorise jusqu'a 30s.
export const config = { maxDuration: 30 };

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

  if (text.startsWith('/mark_supporter')) {
    const body = text.slice('/mark_supporter'.length).trim();
    const spaceIdx = body.indexOf(' ');
    const id = spaceIdx === -1 ? body : body.slice(0, spaceIdx);
    const name = spaceIdx === -1 ? '' : body.slice(spaceIdx + 1).trim();
    if (!id || !name) return sendMessage(token, chatId, 'Usage : /mark_supporter <clientId> <nom> (copie le clientId depuis une notification de chat)');
    const ok = await setChatSupporter(id, name);
    return sendMessage(token, chatId, ok ? `☕ ${id} apparaîtra désormais comme "${name}" dans le chat.` : '❌ Echec (store non configure ?).');
  }

  if (text.startsWith('/unmark_supporter')) {
    const id = text.slice('/unmark_supporter'.length).trim();
    if (!id) return sendMessage(token, chatId, 'Usage : /unmark_supporter <clientId>');
    const ok = await setChatSupporter(id, null);
    return sendMessage(token, chatId, ok ? `✅ Badge supporter retiré : ${id}` : '❌ Echec (store non configure ?).');
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

  if (text.startsWith('/ask')) {
    const q = text.slice('/ask'.length).trim();
    if (!q) return sendMessage(token, chatId, 'Usage : /ask <ta question> — ex: /ask propose-moi un message a pin pour annoncer le mode support');
    const answer = await askClaude(q);
    return sendMessage(token, chatId, answer || '❌ Échec de la requête Claude (clé API manquante ou erreur réseau).');
  }

  if (text.startsWith('/add_supporter')) {
    const body = text.slice('/add_supporter'.length).trim();
    if (!body) return sendMessage(token, chatId, 'Usage : /add_supporter <nom> | <message optionnel> — ajoute manuellement un supporter (ex: don reçu avant la mise en place du webhook BMC).');
    const [namePart, ...rest] = body.split('|');
    const name = namePart.trim().slice(0, 60) || 'A listener';
    const message = rest.join('|').trim().slice(0, 200);
    const ok = await addSupporter(name, message);
    return sendMessage(token, chatId, ok ? `☕ Ajouté à la liste des supporters : ${name}` : '❌ Echec (store non configuré ?).');
  }

  if (text === '/recent_supporters') {
    const list = await getRecentSupporters(10);
    if (!list.length) return sendMessage(token, chatId, 'Aucun supporter à afficher.');
    const lines = list.map((s, i) => `${i + 1}. ${s.name}` + (s.message ? ` — "${s.message}"` : ''));
    const buttons = list.map((s, i) => ({ text: '🗑 ' + (i + 1), callback_data: 'delsup:' + s.id }));
    const rows = [];
    for (let i = 0; i < buttons.length; i += 3) rows.push(buttons.slice(i, i + 3));
    return sendMessage(token, chatId, 'Derniers supporters :\n' + lines.join('\n'), {
      reply_markup: { inline_keyboard: rows },
    });
  }

  if (text === '/reset_top5') {
    const ok = await resetTop5();
    return sendMessage(token, chatId, ok ? '🔥 Top 5 remis à zéro (les votes précédents ne comptent plus).' : '❌ Echec (store non configure ?).');
  }

  if (text.startsWith('/delete_track')) {
    const q = text.slice('/delete_track'.length).trim();
    if (!q) return sendMessage(token, chatId, 'Usage : /delete_track <titre ou artiste> — cherche dans la bibliotheque AzuraCast.');
    const r = await searchTracks(q);
    if (!r.ok) return sendMessage(token, chatId, `Echec de la recherche (${r.status}).`);
    if (!r.list.length) return sendMessage(token, chatId, `Aucune piste trouvée pour « ${q} ».`);
    const top = r.list.slice(0, 8);
    const lines = top.map((f, i) => `${i + 1}. ${f.artist || '?'} — ${f.title || f.text || f.path || '(sans titre)'}`);
    const buttons = top.map((f, i) => ({ text: '🗑 ' + (i + 1), callback_data: 'delfile:' + f.id }));
    const rows = [];
    for (let i = 0; i < buttons.length; i += 3) rows.push(buttons.slice(i, i + 3));
    return sendMessage(token, chatId,
      `Résultats pour « ${q} » — clique 🗑 pour supprimer définitivement (fichier + entrée bibliothèque) :\n` + lines.join('\n'), {
        reply_markup: { inline_keyboard: rows },
      });
  }

  if (text === '/delete_current_track') {
    const d = await nowPlaying();
    if (!d) return sendMessage(token, chatId, '❌ Impossible de joindre AzuraCast.');
    const song = (d.now_playing && d.now_playing.song) || {};
    if (!song.title) return sendMessage(token, chatId, '❌ Aucun morceau identifiable en cours.');
    // La recherche AzuraCast (searchPhrase) matche la phrase complete contre
    // UN champ a la fois (titre OU artiste) — "Artiste Titre" colle en un seul
    // terme ne matchera jamais si les deux sont stockes separement en base.
    // On essaie donc le titre seul d'abord (le plus distinctif), puis
    // l'artiste seul, puis la phrase combinee en dernier recours.
    let r = await searchTracks(song.title);
    if (!r.ok) return sendMessage(token, chatId, `Echec de la recherche dans la bibliothèque (${r.status}).`);
    if (!r.list.length && song.artist) r = await searchTracks(song.artist);
    if (!r.ok) return sendMessage(token, chatId, `Echec de la recherche dans la bibliothèque (${r.status}).`);
    if (!r.list.length) r = await searchTracks(`${song.artist || ''} ${song.title}`.trim());
    if (!r.ok) return sendMessage(token, chatId, `Echec de la recherche dans la bibliothèque (${r.status}).`);
    if (!r.list.length) {
      return sendMessage(token, chatId,
        `Aucune piste de bibliothèque ne correspond à « ${song.artist || '?'} — ${song.title} » ` +
        `(morceau en direct, requête externe, ou jingle ?).`);
    }
    // On tente une correspondance exacte titre(+artiste) pour eviter de
    // presenter par erreur un homonyme de la bibliotheque ; a defaut, on
    // laisse l'admin choisir parmi les resultats de la recherche.
    const exact = r.list.filter((f) =>
      (f.title || '').toLowerCase() === song.title.toLowerCase() &&
      (!song.artist || (f.artist || '').toLowerCase() === song.artist.toLowerCase()));
    const candidates = (exact.length ? exact : r.list).slice(0, 5);
    const lines = candidates.map((f, i) => `${i + 1}. ${f.artist || '?'} — ${f.title || f.text || f.path || '(sans titre)'}`);
    const buttons = candidates.map((f, i) => ({ text: '🗑⏭ ' + (i + 1), callback_data: 'delcur:' + f.id }));
    const rows = [];
    for (let i = 0; i < buttons.length; i += 3) rows.push(buttons.slice(i, i + 3));
    return sendMessage(token, chatId,
      `▶️ En cours : ${song.artist || '?'} — ${song.title}\n` +
      (exact.length === 1
        ? 'Trouvée dans la bibliothèque — clique 🗑⏭ pour supprimer et passer au morceau suivant :'
        : `${candidates.length} correspondance(s) possible(s) — choisis la bonne :`) +
      '\n' + lines.join('\n'),
      { reply_markup: { inline_keyboard: rows } });
  }

  return sendMessage(token, chatId,
    'Commandes disponibles :\n\n' +
    '🎵 Diffusion\n' +
    '/np — morceau en cours + auditeurs\n' +
    '/skip — passer au morceau suivant\n' +
    '/jingle — declencher un jingle (best effort)\n' +
    '/delete_track <recherche> — supprimer une piste de la bibliothèque AzuraCast\n' +
    '/delete_current_track — supprimer le morceau en cours et passer au suivant\n\n' +
    '💬 Chat live\n' +
    '/msg <texte> — envoyer un message admin dans le chat live\n' +
    '/pin <texte> / /unpin — epingler/retirer une annonce en haut du chat\n' +
    '/recent — lister les 10 derniers messages avec un bouton pour les supprimer\n' +
    '/pause_chat / /resume_chat — couper/reactiver le chat\n\n' +
    '👤 Auditeurs & supporters\n' +
    '/ban <clientId> / /unban <clientId> — bloquer/debloquer un auditeur\n' +
    '/mark_supporter <clientId> <nom> / /unmark_supporter <clientId> — badge ☕ dans le chat\n' +
    '/add_supporter <nom> | <message> — ajouter manuellement un supporter à la liste\n' +
    '/recent_supporters — lister les 10 derniers supporters avec un bouton pour les supprimer\n\n' +
    '🤖 Assistant\n' +
    '/ask <question> — demander de l\'aide à Claude (messages à pin, idées pour animer le chat, etc.)\n\n' +
    '📊 Stats & votes\n' +
    '/stats — auditeurs, messages et votes du jour\n' +
    '/reset_top5 — remettre à zéro le classement des votes 🔥\n\n' +
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
  } else if (data.startsWith('delfile:')) {
    const id = data.slice(8);
    // Recupere le libelle avant suppression (apres, le fichier n'existe plus).
    const info = await getTrack(id);
    const label = info.ok && info.data ? `${info.data.artist || '?'} — ${info.data.title || info.data.text || id}` : id;
    const r = await deleteTrack(id);
    // Toast immediat (disparait vite) + message persistant dans le chat admin,
    // pour avoir une trace claire de validation/echec meme si le toast est rate.
    await answerCallback(token, cb.id, r.ok ? '🗑 Supprimé' : `❌ Échec (${r.status})`);
    await sendMessage(token, cb.message.chat.id,
      r.ok
        ? `✅ Piste supprimée d'AzuraCast : ${label}`
        : `❌ Échec de la suppression de « ${label} » (${r.status}).${r.status === 403 ? ' La cle API manque peut-etre du droit "Manage Station Media".' : ''}`);
    if (r.ok) await editMessageMarkup(token, cb.message.chat.id, cb.message.message_id);
  } else if (data.startsWith('delcur:')) {
    const id = data.slice(7);
    const info = await getTrack(id);
    const label = info.ok && info.data ? `${info.data.artist || '?'} — ${info.data.title || info.data.text || id}` : id;
    const r = await deleteTrack(id);
    if (!r.ok) {
      await answerCallback(token, cb.id, `❌ Échec (${r.status})`);
      await sendMessage(token, cb.message.chat.id,
        `❌ Échec de la suppression de « ${label} » (${r.status}).${r.status === 403 ? ' La cle API manque peut-etre du droit "Manage Station Media".' : ''}`);
      return editMessageMarkup(token, cb.message.chat.id, cb.message.message_id);
    }
    const skip = await skipSong();
    if (skip.ok) await postAdminMessage('⏭ An admin skipped the current track.');
    await answerCallback(token, cb.id, skip.ok ? '🗑 Supprimé, morceau suivant lancé' : '🗑 Supprimé (skip échoué)');
    await sendMessage(token, cb.message.chat.id,
      `✅ Piste supprimée d'AzuraCast : ${label}\n` +
      (skip.ok ? '⏭ Morceau suivant lancé.' : `⚠️ Le skip a échoué (${skip.status}) — lance-le manuellement avec /skip.`));
    await editMessageMarkup(token, cb.message.chat.id, cb.message.message_id);
  } else if (data.startsWith('delsup:')) {
    const id = data.slice(7);
    await markDeletedSupporter(id);
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

// Recherche par titre/artiste dans la bibliotheque media de la station (pas
// la file d'attente ni les demandes). L'API publique renvoie soit un tableau
// simple, soit {rows:[...]} selon la version d'AzuraCast : on gere les deux.
async function searchTracks(query) {
  const apiKey = process.env.AZURACAST_API_KEY;
  if (!apiKey) return { ok: false, status: 'no-api-key' };
  try {
    const url = `${AZURACAST_BASE}/api/station/${STATION}/files?searchPhrase=${encodeURIComponent(query)}`;
    const r = await fetch(url, { headers: { 'X-API-Key': apiKey } });
    if (!r.ok) return { ok: false, status: r.status };
    const body = await r.json();
    const list = Array.isArray(body) ? body : (body.rows || body.data || []);
    return { ok: true, list };
  } catch {
    return { ok: false, status: 'network-error' };
  }
}

// Recupere titre/artiste d'un fichier avant de le supprimer, pour que le
// message de confirmation nomme la piste plutot que son seul id numerique.
async function getTrack(id) {
  const apiKey = process.env.AZURACAST_API_KEY;
  if (!apiKey) return { ok: false, status: 'no-api-key' };
  try {
    const r = await fetch(`${AZURACAST_BASE}/api/station/${STATION}/file/${encodeURIComponent(id)}`, {
      headers: { 'X-API-Key': apiKey },
    });
    if (!r.ok) return { ok: false, status: r.status };
    return { ok: true, data: await r.json() };
  } catch {
    return { ok: false, status: 'network-error' };
  }
}

// Suppression definitive : retire le fichier ET son entree de la bibliotheque
// (ne se contente pas de le sortir de la playlist). Irreversible cote AzuraCast.
async function deleteTrack(id) {
  const apiKey = process.env.AZURACAST_API_KEY;
  if (!apiKey) return { ok: false, status: 'no-api-key' };
  try {
    const r = await fetch(`${AZURACAST_BASE}/api/station/${STATION}/file/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: { 'X-API-Key': apiKey },
    });
    return { ok: r.ok, status: r.status };
  } catch {
    return { ok: false, status: 'network-error' };
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

/* ---- Claude (brainstorm admin : /ask) ---- */
const CLAUDE_SYSTEM_PROMPT =
  "You help run KALBASSFM, a 100% electronic webradio from the Caribbean. " +
  "The admin messages you from Telegram for quick brainstorming — drafting a chat " +
  "pin announcement, ideas to animate the live chat, small engagement ideas, or " +
  "general help. When asked to draft a pin message, give exactly 3 short numbered " +
  "options, each under 200 characters (they get pasted directly after \"/pin \"), " +
  "in English, matching a light Caribbean/electronic-music tone. For anything else, " +
  "give a few concise, actionable suggestions. Keep replies short and scannable — " +
  "this is read on a phone inside Telegram, not a long essay.";

// HTTP brut (pas de dependance @anthropic-ai/sdk, coherent avec le reste du
// projet). Pas de "thinking" : reponses courtes/creatives, pas de raisonnement
// complexe requis, et ca garde la latence basse dans le contexte d'un webhook.
async function askClaude(prompt) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return null;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 25000);
  try {
    const r = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-opus-4-8',
        max_tokens: 1024,
        system: CLAUDE_SYSTEM_PROMPT,
        messages: [{ role: 'user', content: prompt.slice(0, 2000) }],
      }),
      signal: controller.signal,
    });
    if (!r.ok) return null;
    const data = await r.json();
    const text = (data.content || [])
      .filter((b) => b.type === 'text')
      .map((b) => b.text)
      .join('\n')
      .trim();
    // Marge de securite sous la limite Telegram (4096 caracteres/message).
    return text ? text.slice(0, 3800) : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
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

// Meme convention que getRecentMessages/markDeleted, mais sur la liste
// "supporters" (api/supporters.js) — suppression logique (hash "supporters:deleted"),
// lue et filtree cote GET de api/supporters.js.
async function getRecentSupporters(n) {
  const kv = kvClient();
  if (!kv) return [];
  const [lj, dj] = await Promise.all([
    kv('lrange', 'supporters', '0', String(n - 1)),
    kv('hgetall', 'supporters:deleted'),
  ]);
  const raw = lj.result || [];
  const deletedFields = dj.result || [];
  const deleted = new Set();
  for (let i = 0; i < deletedFields.length; i += 2) deleted.add(deletedFields[i]);
  return raw
    .map((s) => { try { return JSON.parse(s); } catch { return null; } })
    .filter((s) => s && !deleted.has(s.id));
}

// Ajout manuel (ex: don recu avant la mise en place du webhook BMC, ou
// webhook temporairement en panne) — meme schema que api/supporters.js.
async function addSupporter(name, message) {
  const kv = kvClient();
  if (!kv) return false;
  const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  const entry = { id, name, message, ts: Date.now() };
  await kv('lpush', 'supporters', JSON.stringify(entry));
  await kv('ltrim', 'supporters', '0', '49');
  return true;
}

async function markDeletedSupporter(id) {
  const kv = kvClient();
  if (!kv || !id) return;
  await kv('hset', 'supporters:deleted', id, '1');
}

async function setBanned(clientId, banned) {
  const kv = kvClient();
  if (!kv || !clientId) return false;
  await kv(banned ? 'sadd' : 'srem', 'chat:banned', clientId);
  return true;
}

// Lien clientId -> nom de supporter, pose UNIQUEMENT par l'admin (/mark_supporter).
// Lu par api/chat.js a chaque POST pour surclasser le pseudo (badge ☕) —
// jamais derive de ce que le client envoie, meme principe que le flag admin.
async function setChatSupporter(clientId, name) {
  const kv = kvClient();
  if (!kv || !clientId) return false;
  if (name) await kv('hset', 'chat:supporters', clientId, name.slice(0, 30));
  else await kv('hdel', 'chat:supporters', clientId);
  return true;
}

async function setPaused(paused) {
  const kv = kvClient();
  if (!kv) return false;
  if (paused) await kv('set', 'chat:paused', '1');
  else await kv('del', 'chat:paused');
  return true;
}

// Incremente l'epoch lu par api/reactions.js : le classement (leaderboard:<epoch>)
// et les plafonds de vote par auditeur (votes:<epoch>:<id>) redemarrent a zero
// sans avoir a lister/supprimer des cles individuellement.
async function resetTop5() {
  const kv = kvClient();
  if (!kv) return false;
  await kv('incr', 'top5:epoch');
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
