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

// Reactive le 2026-07-21 : Upstash passe en Pay As You Go + Top 5 retire
// (gros consommateur), donc quota nettement moins a risque.
const REDIS_PAUSED = false;

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

// Tolere les chevrons colles a la lettre depuis les messages d'usage
// ("/rename <clientId> <pseudo>") — un admin qui copie l'exemple sans
// remplacer les placeholders enregistrerait sinon sous une cle "<...>" qui
// ne correspond a aucun clientId reel, en echec silencieux (aucune erreur,
// juste aucun effet visible).
function stripAngles(s) {
  return s.replace(/^<(.*)>$/, '$1');
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
    const id = stripAngles(text.slice(4).trim());
    if (!id) return sendMessage(token, chatId, 'Usage : /ban <clientId> (copie-le depuis une notification de chat)');
    const ok = await setBanned(id, true);
    return sendMessage(token, chatId, ok ? `🔨 Banni : ${id}` : '❌ Echec (store non configure ?).');
  }

  if (text.startsWith('/unban')) {
    const id = stripAngles(text.slice(6).trim());
    if (!id) return sendMessage(token, chatId, 'Usage : /unban <clientId>');
    const ok = await setBanned(id, false);
    return sendMessage(token, chatId, ok ? `✅ Debanni : ${id}` : '❌ Echec (store non configure ?).');
  }

  if (text.startsWith('/mark_supporter')) {
    const body = text.slice('/mark_supporter'.length).trim();
    const spaceIdx = body.indexOf(' ');
    const id = stripAngles(spaceIdx === -1 ? body : body.slice(0, spaceIdx));
    const name = stripAngles(spaceIdx === -1 ? '' : body.slice(spaceIdx + 1).trim());
    if (!id || !name) return sendMessage(token, chatId, 'Usage : /mark_supporter <clientId> <nom> (copie le clientId depuis une notification de chat)');
    const ok = await setChatSupporter(id, name);
    return sendMessage(token, chatId, ok ? `☕ ${id} apparaîtra désormais comme "${name}" dans le chat.` : '❌ Echec (store non configure ?).');
  }

  if (text.startsWith('/unmark_supporter')) {
    const id = stripAngles(text.slice('/unmark_supporter'.length).trim());
    if (!id) return sendMessage(token, chatId, 'Usage : /unmark_supporter <clientId>');
    const ok = await setChatSupporter(id, null);
    return sendMessage(token, chatId, ok ? `✅ Badge supporter retiré : ${id}` : '❌ Echec (store non configure ?).');
  }

  if (text.startsWith('/rename')) {
    const body = text.slice('/rename'.length).trim();
    const spaceIdx = body.indexOf(' ');
    const id = stripAngles(spaceIdx === -1 ? body : body.slice(0, spaceIdx));
    const name = stripAngles(spaceIdx === -1 ? '' : body.slice(spaceIdx + 1).trim());
    if (!id || !name) return sendMessage(token, chatId, 'Usage : /rename <clientId> <nouveau pseudo> (copie le clientId depuis une notification de chat)');
    const ok = await setChatNickname(id, name);
    if (ok) await renameHistory(id, name);
    return sendMessage(token, chatId, ok ? `✏️ ${id} apparaîtra désormais comme "${name}" dans le chat (historique compris).` : '❌ Echec (store non configure ?).');
  }

  if (text.startsWith('/unrename')) {
    const id = stripAngles(text.slice('/unrename'.length).trim());
    if (!id) return sendMessage(token, chatId, 'Usage : /unrename <clientId>');
    const ok = await setChatNickname(id, null);
    return sendMessage(token, chatId, ok ? `✅ Pseudo réinitialisé : ${id}` : '❌ Echec (store non configure ?).');
  }

  if (text.startsWith('/rename_nick')) {
    const body = text.slice('/rename_nick'.length).trim();
    const spaceIdx = body.indexOf(' ');
    const oldNick = stripAngles(spaceIdx === -1 ? body : body.slice(0, spaceIdx));
    const name = stripAngles(spaceIdx === -1 ? '' : body.slice(spaceIdx + 1).trim());
    if (!oldNick || !name) return sendMessage(token, chatId, 'Usage : /rename_nick <ancien pseudo exact> <nouveau pseudo> — rattrape les messages postés avant que /rename ne connaisse le clientId (ex: "Listener-2216"). Ne renomme pas les messages à venir : utilise /rename pour ça.');
    const n = await renameHistoryByNick(oldNick, name);
    return sendMessage(token, chatId, n > 0 ? `✏️ ${n} message(s) renommé(s) de "${oldNick}" vers "${name}".` : `Aucun message trouvé avec le pseudo exact "${oldNick}".`);
  }

  if (text === '/pause_chat') {
    const ok = await pauseChatWithBanner();
    return sendMessage(token, chatId, ok ? '⏸ Chat en pause — plus personne ne peut poster, bandeau épinglé pour prévenir les auditeurs.' : '❌ Echec (store non configure ?).');
  }

  if (text === '/resume_chat') {
    const ok = await resumeChatRestorePin();
    return sendMessage(token, chatId, ok ? '▶️ Chat réactivé.' : '❌ Echec (store non configure ?).');
  }

  if (text === '/np') {
    return sendMessage(token, chatId, await nowPlayingText());
  }

  if (text === '/stats') {
    return sendMessage(token, chatId, await statsText());
  }

  // Plus lourd que /stats (fenetre de 30 jours d'historique) : commande
  // separee pour que /stats reste une reponse instantanee.
  if (text === '/audience') {
    return sendMessage(token, chatId, await audienceText());
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

  // Filet de securite pour api/submit-mix.js : chaque candidature arrive deja
  // en notification, mais une notification se perd dans le fil — l'archive
  // Redis permet de retrouver les 10 dernieres avec leur mail et leur lien.
  if (text === '/submissions') {
    const list = await getRecentSubmissions(10);
    if (!list.length) return sendMessage(token, chatId, 'Aucune candidature mix à afficher.');
    // Texte brut, sans parse_mode : convention du bot (voir audienceText).
    // disable_web_page_preview evite qu'un lien SoundCloud/Drive deploie une
    // carte de previsualisation plus grande que la liste elle-meme.
    const lines = list.map((s, i) => {
      const socials = [
        s.instagram ? 'instagram.com/' + s.instagram : '',
        s.soundcloud ? 'soundcloud.com/' + s.soundcloud : '',
      ].filter(Boolean).join('  ');
      return `${i + 1}. ${s.dj || '?'} — ${s.style || '?'}\n`
        + `   ${s.email || '?'}\n`
        + `   ${s.url || '?'}`
        + (socials ? `\n   ${socials}` : '');
    });
    // Un bouton "📣 N" par candidature : une fois la mixtape planifiee, un tap
    // publie l'annonce dans le chat live avec les liens sociaux du DJ.
    const buttons = list.map((s, i) => ({ text: '📣 ' + (i + 1), callback_data: 'annmix:' + s.id }));
    const rows = [];
    for (let i = 0; i < buttons.length; i += 3) rows.push(buttons.slice(i, i + 3));
    return sendMessage(token, chatId,
      '🎛 Dernières candidatures mix :\n' + lines.join('\n')
      + '\n\n📣 = annoncer dans le chat live (à faire une fois la programmation calée).', {
        disable_web_page_preview: true,
        reply_markup: { inline_keyboard: rows },
      });
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

  if (text === '/move') {
    const d = await nowPlaying();
    if (!d) return sendMessage(token, chatId, '❌ Impossible de joindre AzuraCast.');
    const song = (d.now_playing && d.now_playing.song) || {};
    if (!song.title) return sendMessage(token, chatId, '❌ Aucun morceau identifiable en cours.');
    // Même logique que /delete_current_track : cherche d'abord par titre seul,
    // puis par artiste seul, puis les deux combinés en dernier recours.
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
    // Tente une correspondance exacte pour éviter les erreurs
    const exact = r.list.filter((f) =>
      (f.title || '').toLowerCase() === song.title.toLowerCase() &&
      (!song.artist || (f.artist || '').toLowerCase() === song.artist.toLowerCase()));
    const candidate = exact.length ? exact[0] : r.list[0];
    const playlists = await getPlaylists();
    if (!playlists.ok || !playlists.list.length) {
      return sendMessage(token, chatId, '❌ Impossible de récupérer les playlists.');
    }
    // Extraire le dossier source
    const currentPath = candidate.path || '';
    const pathMatch = currentPath.match(/Progv2\/([^\/]+)\//);
    const currentPlaylist = pathMatch ? pathMatch[1] : '?';
    const label = `${song.artist || '?'} — ${song.title}`;
    const lines = playlists.list.map((p) => p.name);
    const buttons = playlists.list.map((p) => ({ text: p.name.slice(0, 12), callback_data: 'movecur:' + candidate.id + ':' + p.id }));
    const rows = [];
    for (let i = 0; i < buttons.length; i += 2) rows.push(buttons.slice(i, i + 2));
    return sendMessage(token, chatId,
      `▶️ En cours : ${label}\n📁 Actuellement : ${currentPlaylist}\n\nVers quelle playlist ?\n\n` + lines.join('\n'), {
        reply_markup: { inline_keyboard: rows },
      });
  }

  return sendMessage(token, chatId,
    'Commandes disponibles :\n\n' +
    '🎵 Diffusion\n' +
    '/np — morceau en cours + auditeurs\n' +
    '/skip — passer au morceau suivant\n' +
    '/jingle — declencher un jingle (best effort)\n' +
    '/move — deplacer le morceau en cours vers une autre playlist\n' +
    '/delete_track <recherche> — supprimer une piste de la bibliothèque AzuraCast\n' +
    '/delete_current_track — supprimer le morceau en cours et passer au suivant\n\n' +
    '💬 Chat live\n' +
    '/msg <texte> — envoyer un message admin dans le chat live\n' +
    '/pin <texte> / /unpin — epingler/retirer une annonce en haut du chat\n' +
    '/recent — lister les 10 derniers messages avec un bouton pour les supprimer\n' +
    '/pause_chat / /resume_chat — couper/reactiver le chat (bandeau epingle automatiquement pendant la pause)\n\n' +
    '👤 Auditeurs & supporters\n' +
    '/ban <clientId> / /unban <clientId> — bloquer/debloquer un auditeur\n' +
    '/mark_supporter <clientId> <nom> / /unmark_supporter <clientId> — badge ☕ dans le chat\n' +
    '/rename <clientId> <pseudo> / /unrename <clientId> — imposer un pseudo (moderation)\n' +
    '/rename_nick <ancien pseudo exact> <nouveau pseudo> — rattrape l\'historique quand /rename ne trouve pas de clientId\n' +
    '/add_supporter <nom> | <message> — ajouter manuellement un supporter à la liste\n' +
    '/recent_supporters — lister les 10 derniers supporters avec un bouton pour les supprimer\n\n' +
    '🎛 Candidatures DJ\n' +
    '/submissions — lister les 10 dernières candidatures mix (nom, style, mail, lien du set, réseaux)\n' +
    '   bouton 📣 sous la liste — annoncer le DJ dans le chat live avec ses liens Insta/SoundCloud\n\n' +
    '🤖 Assistant\n' +
    '/ask <question> — demander de l\'aide à Claude (messages à pin, idées pour animer le chat, etc.)\n\n' +
    '📊 Stats\n' +
    '/stats — auditeurs et messages du jour\n' +
    '/audience — moyennes 24 h / 30 j, pics, meilleur jour et localisation des auditeurs\n\n' +
    'Astuce : clique le bouton "↩️ Repondre" sous une notification de message pour y repondre, sous Admin.');
}

async function handleCallback(token, cb) {
  const fromId = cb.from && cb.from.id;
  const authorized = String(fromId) === String(process.env.TELEGRAM_CHAT_ID || '');
  if (!authorized) return;

  const data = cb.data || '';
  // Toute la logique ci-dessous est enveloppee dans un try/catch : sans lui,
  // une erreur Redis (quota Upstash depasse, panne...) qui leve avant
  // d'atteindre answerCallback laisse le tap Telegram sans aucune reaction
  // visible (bouton ni retire, ni toast) — l'admin croit avoir rate son tap
  // et reessaie en boucle pour rien. On garantit ici qu'un tap produit
  // toujours un retour, meme en cas d'echec.
  try {
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
      `✍️ Écris ta réponse à « ${orig.nick} » — je la posterai dans le chat live sous Admin.`,
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
    await answerCallback(token, cb.id, skip.ok ? '🗑 Supprimé, morceau suivant lancé' : '🗑 Supprimé (skip échoué)');
    await sendMessage(token, cb.message.chat.id,
      `✅ Piste supprimée d'AzuraCast : ${label}\n` +
      (skip.ok ? '⏭ Morceau suivant lancé.' : `⚠️ Le skip a échoué (${skip.status}) — lance-le manuellement avec /skip.`));
    await editMessageMarkup(token, cb.message.chat.id, cb.message.message_id);
  } else if (data.startsWith('annmix:')) {
    const sub = await getSubmissionById(data.slice(7));
    if (!sub) return answerCallback(token, cb.id, 'Candidature introuvable (trop ancienne).');
    const id = await postAdminMessage(mixAnnouncement(sub));
    await answerCallback(token, cb.id, id ? 'Annonce publiée ✅' : '❌ Échec (store non configuré ?)');
    // Les boutons de la liste sont volontairement CONSERVES ici, contrairement
    // aux suppressions : annoncer n'est pas destructif, et il arrive de vouloir
    // re-annoncer (nouvelle diffusion du meme mix, message noye dans le fil).
    return confirmWithDelete(token, cb.message.chat.id, '📣 Annonce publiée dans le chat live.', id);
  } else if (data.startsWith('delsup:')) {
    const id = data.slice(7);
    await markDeletedSupporter(id);
    await answerCallback(token, cb.id, 'Supprimé ✅');
    await editMessageMarkup(token, cb.message.chat.id, cb.message.message_id);
  } else if (data.startsWith('movecur:')) {
    const parts = data.slice(8).split(':');
    const trackId = parts[0];
    const playlistId = parts[1];
    if (!trackId || !playlistId) {
      await answerCallback(token, cb.id, '❌ Paramètres invalides.');
      return;
    }
    const info = await getTrack(trackId);
    const label = info.ok && info.data ? `${info.data.artist || '?'} — ${info.data.title || info.data.text || trackId}` : trackId;
    const playlists = await getPlaylists();
    const targetPlaylist = playlists.ok ? playlists.list.find(p => String(p.id) === String(playlistId)) : null;
    const r = await moveTrackToPlaylist(trackId, playlistId);
    if (!r.ok) {
      await answerCallback(token, cb.id, `❌ Échec (${r.status})`);
      await sendMessage(token, cb.message.chat.id,
        `❌ Impossible de déplacer « ${label} » (${r.status}).`);
      return;
    }
    await answerCallback(token, cb.id, '✅ Déplacé');
    // Extraire les informations de chemin pour le résumé local
    const currentPath = info.ok && info.data ? (info.data.path || '') : '';
    const pathMatch = currentPath.match(/Progv2\/([^\/]+)\/(.+)$/);
    const sourceBac = pathMatch ? pathMatch[1] : '?';
    const filename = pathMatch ? pathMatch[2] : '?';
    const targetBac = targetPlaylist ? targetPlaylist.name : 'Destination';
    const summary = currentPath
      ? `📋 Résumé pour synchronisation locale :\n\n` +
        `Fichier : ${filename}\n` +
        `De : Progv2\\${sourceBac}\\\n` +
        `Vers : Progv2\\${targetBac}\\\n\n` +
        `(Copier/déplacer le fichier sur votre PC avec FileZilla)`
      : '';
    await sendMessage(token, cb.message.chat.id,
      `✅ Morceau déplacé : ${label}\n${summary}`);
    await editMessageMarkup(token, cb.message.chat.id, cb.message.message_id);
  } else {
    await answerCallback(token, cb.id, '');
  }
  } catch {
    await answerCallback(token, cb.id, '❌ Échec (Redis indisponible — quota Upstash dépassé ?)').catch(() => {});
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

// Recupere la liste des playlists de la station
async function getPlaylists() {
  const apiKey = process.env.AZURACAST_API_KEY;
  if (!apiKey) return { ok: false, status: 'no-api-key' };
  try {
    const r = await fetch(`${AZURACAST_BASE}/api/station/${STATION}/playlists`, {
      headers: { 'X-API-Key': apiKey },
    });
    if (!r.ok) return { ok: false, status: r.status };
    const body = await r.json();
    const list = Array.isArray(body) ? body : (body.playlists || body.rows || []);
    return { ok: true, list };
  } catch {
    return { ok: false, status: 'network-error' };
  }
}

// Reaffecte une piste a une (seule) playlist. Il n'existe pas d'endpoint
// AzuraCast dedie "media -> playlist" (un POST vers .../playlist/{id}/media/{id}
// renvoie 405, verifie en prod le 2026-07-24) : l'appartenance aux playlists
// est un champ ecrivable de la ressource file elle-meme (Api_StationMedia.playlists,
// tableau d'IDs), donc on passe par le meme endpoint que getTrack/deleteTrack
// (PUT au lieu de GET/DELETE) avec { playlists: [playlistId] }.
async function moveTrackToPlaylist(trackId, playlistId) {
  const apiKey = process.env.AZURACAST_API_KEY;
  if (!apiKey) return { ok: false, status: 'no-api-key' };
  try {
    const r = await fetch(
      `${AZURACAST_BASE}/api/station/${STATION}/file/${encodeURIComponent(trackId)}`,
      {
        method: 'PUT',
        headers: { 'X-API-Key': apiKey, 'Content-Type': 'application/json' },
        body: JSON.stringify({ playlists: [Number(playlistId)] }),
      }
    );
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

// Formulation unique des auditeurs pour /np, /stats et /audience.
// On annonce des PERSONNES (listeners.unique), pas des connexions
// (listeners.total) : l'ecart entre les deux vient surtout des reconnexions
// mobiles — quand un telephone bascule du Wi-Fi a la 4G, l'ancienne connexion
// reste ouverte une a deux minutes cote serveur et est comptee en double.
// L'ancien "4 (3 uniques)" laissait croire a 4 auditeurs ; le chiffre honnete
// est 3. Le nombre de connexions n'est rappele que s'il differe.
function listenersText(listeners) {
  const nl = listeners || {};
  const uniq = nl.unique ?? null;
  const total = nl.total ?? nl.current ?? null;
  if (uniq === null) return '?';
  return `${uniq} auditeur${uniq > 1 ? 's' : ''}`
    + (total !== null && total !== uniq ? ` (${total} connexions ouvertes)` : '');
}

async function nowPlayingText() {
  const d = await nowPlaying();
  if (!d) return '❌ Impossible de joindre AzuraCast.';
  const song = (d.now_playing && d.now_playing.song) || {};
  const label = song.title ? `${song.artist || ''} — ${song.title}`.trim() : '(inconnu)';
  return `▶️ En cours : ${label}\n🎧 ${listenersText(d.listeners)}`;
}

async function statsText() {
  const kv = kvClient();
  const day = new Date(Date.now() - 4 * 3600 * 1000).toISOString().slice(0, 10);
  const [d, msgJ] = await Promise.all([
    nowPlaying(),
    kv ? kv('get', `stats:msg:${day}`) : Promise.resolve({ result: null }),
  ]);
  const msgs = (msgJ && msgJ.result) || 0;
  return `📊 Stats du ${day} (UTC-4)\n` +
    `🎧 Maintenant : ${listenersText(d && d.listeners)}\n` +
    `💬 Messages du chat aujourd'hui : ${msgs}`;
}

/* ---- Audience : moyennes jour/mois + localisation (/audience) ----

   Tout vient d'AzuraCast, rien n'est accumule cote Redis : l'instance garde
   deja l'historique complet depuis le premier jour, et un echantillonnage
   maison n'aurait aucune anteriorite tout en ajoutant des ecritures Upstash
   (cf. l'incident de quota du 2026-07-21).

   Deux endpoints, tous deux au schema documente dans /static/openapi.yml de
   l'instance (verifie avant ecriture — meme lecon que le 405 de /move) :
   - GET /station/{id}/history?start=&end=  -> Api_DetailedSongHistory[],
     un enregistrement par morceau joue avec listeners_start/listeners_end,
     played_at (timestamp UNIX) et duration (secondes).
   - GET /station/{id}/listeners            -> Api_Listener[], avec location
     (country / city / description) pour les auditeurs CONNECTES MAINTENANT.
     AzuraCast n'expose pas d'historique de localisation : les lieux sont donc
     forcement un instantane, pas une moyenne.

   La moyenne est PONDEREE PAR LA DUREE : chaque morceau represente une tranche
   de temps pendant laquelle l'audience valait ~(start+end)/2. Une moyenne
   simple par morceau surponderait les titres courts. */
const AUDIENCE_CACHE_KEY = 'stats:audience';
const AUDIENCE_CACHE_TTL = 900; // 15 min : la fenetre 30 j bouge lentement

async function fetchHistory(startTs, endTs) {
  const apiKey = process.env.AZURACAST_API_KEY;
  if (!apiKey) return null;
  const qs = `start=${new Date(startTs).toISOString()}&end=${new Date(endTs).toISOString()}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const r = await fetch(`${AZURACAST_BASE}/api/station/${STATION}/history?${qs}`, {
      headers: { 'X-API-Key': apiKey, 'User-Agent': BROWSER_UA },
      signal: controller.signal,
    });
    if (!r.ok) return null;
    const d = await r.json();
    return Array.isArray(d) ? d : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchListeners() {
  const apiKey = process.env.AZURACAST_API_KEY;
  if (!apiKey) return null;
  try {
    const r = await fetch(`${AZURACAST_BASE}/api/station/${STATION}/listeners`, {
      headers: { 'X-API-Key': apiKey, 'User-Agent': BROWSER_UA },
    });
    if (!r.ok) return null;
    const d = await r.json();
    return Array.isArray(d) ? d : null;
  } catch { return null; }
}

// Moyenne ponderee par la duree sur un sous-ensemble d'entrees d'historique.
// Retourne null si la fenetre ne contient aucune seconde de diffusion (evite
// d'afficher "0.0" pour une absence de donnees, qui n'a pas le meme sens).
function weightedAverage(entries) {
  let seconds = 0;
  let sum = 0;
  for (const e of entries) {
    const dur = Number(e.duration) || 0;
    if (dur <= 0) continue;
    const mid = ((Number(e.listeners_start) || 0) + (Number(e.listeners_end) || 0)) / 2;
    sum += mid * dur;
    seconds += dur;
  }
  return seconds ? { avg: sum / seconds, hours: seconds / 3600 } : null;
}

function peakOf(entries) {
  let peak = 0;
  for (const e of entries) {
    peak = Math.max(peak, Number(e.listeners_start) || 0, Number(e.listeners_end) || 0);
  }
  return peak;
}

// Jour "radio" en heure Martinique (UTC-4 fixe, pas de DST) — meme convention
// que les annonces automatiques et le compteur stats:msg de api/chat.js.
function mqDay(tsMs) {
  return new Date(tsMs - 4 * 3600 * 1000).toISOString().slice(0, 10);
}

async function audienceStats() {
  const now = Date.now();
  const month = await fetchHistory(now - 30 * 86400 * 1000, now);
  if (!month) return null;

  const day = month.filter((e) => (Number(e.played_at) || 0) * 1000 >= now - 86400 * 1000);

  // Meilleure journee du mois : moyenne ponderee jour par jour, pas somme
  // d'auditeurs — sinon une journee avec plus d'heures de diffusion gagnerait
  // mecaniquement.
  const byDay = new Map();
  for (const e of month) {
    const d = mqDay((Number(e.played_at) || 0) * 1000);
    if (!byDay.has(d)) byDay.set(d, []);
    byDay.get(d).push(e);
  }
  let best = null;
  for (const [d, entries] of byDay) {
    const w = weightedAverage(entries);
    if (w && w.hours >= 6 && (!best || w.avg > best.avg)) best = { day: d, avg: w.avg };
  }

  return {
    daily: weightedAverage(day),
    monthly: weightedAverage(month),
    dailyPeak: peakOf(day),
    monthlyPeak: peakOf(month),
    tracksDay: day.length,
    daysCovered: byDay.size,
    best,
  };
}

// Regroupe les auditeurs connectes par pays, avec les villes distinctes.
function groupLocations(listeners) {
  const byCountry = new Map();
  for (const l of listeners) {
    const loc = l.location || {};
    const country = loc.country || 'Inconnu';
    if (!byCountry.has(country)) byCountry.set(country, { n: 0, cities: new Set() });
    const row = byCountry.get(country);
    row.n += 1;
    if (loc.city) row.cities.add(loc.city);
  }
  return [...byCountry.entries()].sort((a, b) => b[1].n - a[1].n);
}

function fmtAvg(w) {
  return w ? w.avg.toFixed(1) : '—';
}

async function audienceText() {
  const kv = kvClient();
  // Cache court : la fenetre 30 jours represente des milliers d'entrees, inutile
  // de la recalculer a chaque appel. Les auditeurs connectes, eux, sont toujours
  // relus en direct (c'est un instantane, il perdrait tout son sens en cache).
  let stats = null;
  if (kv) {
    try {
      const c = await kv('get', AUDIENCE_CACHE_KEY);
      if (c && c.result) stats = JSON.parse(c.result);
    } catch {}
  }
  if (!stats) {
    stats = await audienceStats();
    if (stats && kv) {
      try {
        await kv('set', AUDIENCE_CACHE_KEY, JSON.stringify(stats), 'EX', String(AUDIENCE_CACHE_TTL));
      } catch {}
    }
  }

  const [np, listeners] = await Promise.all([nowPlaying(), fetchListeners()]);
  const nowText = listenersText(np && np.listeners);

  // Texte brut, sans parse_mode : c'est la convention de tout le bot (aucun
  // autre message n'utilise HTML/Markdown), donc rien a echapper.
  let out = `📊 Audience\n\n🎧 Maintenant : ${nowText}\n`;

  if (!stats) {
    out += '\n⚠️ Historique indisponible (cle API AzuraCast absente ou API injoignable).';
  } else {
    out += `\n📅 Moyenne 24 h : ${fmtAvg(stats.daily)} auditeurs\n` +
           `   pic ${stats.dailyPeak} · ${stats.tracksDay} morceaux joues\n` +
           `\n📆 Moyenne 30 j : ${fmtAvg(stats.monthly)} auditeurs\n` +
           `   pic ${stats.monthlyPeak} · ${stats.daysCovered} jours de donnees\n`;
    if (stats.best) {
      out += `   meilleur jour : ${stats.best.day} (${stats.best.avg.toFixed(1)})\n`;
    }
  }

  out += '\n🌍 Localisation (auditeurs connectes maintenant)\n';
  if (!listeners) {
    out += '   ⚠️ Indisponible (cle API AzuraCast absente ou API injoignable).';
  } else if (!listeners.length) {
    out += '   Personne connecte a l\'instant.';
  } else {
    for (const [country, row] of groupLocations(listeners).slice(0, 10)) {
      const cities = [...row.cities].slice(0, 3).join(', ');
      out += `   ${country} : ${row.n}${cities ? ` — ${cities}` : ''}\n`;
    }
    const totalTime = listeners.reduce((s, l) => s + (Number(l.connected_time) || 0), 0);
    out += `   ecoute moyenne en cours : ${Math.round(totalTime / listeners.length / 60)} min`;
  }

  return out;
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
  if (REDIS_PAUSED) return null;
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
  const msg = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8), nick: 'Admin', text: text.slice(0, 200), ts: Date.now(), admin: true };
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
    nick: 'Admin',
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

// Candidatures DJ archivees par api/submit-mix.js. Pas de liste "deleted"
// comme pour les messages ou les supporters : rien n'est expose publiquement
// ici, donc rien a moderer — la liste est bornee par le LTRIM a 49.
async function getRecentSubmissions(n) {
  const kv = kvClient();
  if (!kv) return [];
  const lj = await kv('lrange', 'mix:submissions', '0', String(n - 1));
  return (lj.result || [])
    .map((s) => { try { return JSON.parse(s); } catch { return null; } })
    .filter(Boolean);
}

async function getSubmissionById(id) {
  // 49 entrees au maximum (LTRIM dans api/submit-mix.js) : un scan complet
  // coute une seule commande Redis, la ou un index par id en couterait une de
  // plus a chaque soumission pour le meme resultat.
  const all = await getRecentSubmissions(50);
  return all.find((s) => s && s.id === id) || null;
}

/* Annonce publiee dans le chat live quand une mixtape est calee.

   Les pseudos sociaux viennent de socialHandle() dans api/submit-mix.js : ils
   ne peuvent contenir ni schema ni domaine, donc l'URL reconstruite ici pointe
   forcement vers Instagram ou SoundCloud, jamais ailleurs.

   postAdminMessage tronque a 200 caracteres. On calcule donc le budget en
   partant des liens plutot que l'inverse : couper un lien en deux le rendrait
   inutilisable, alors qu'un nom de DJ tres long s'abrege sans dommage. */
function mixAnnouncement(s) {
  const links = [
    s.instagram ? 'instagram.com/' + s.instagram : '',
    s.soundcloud ? 'soundcloud.com/' + s.soundcloud : '',
  ].filter(Boolean);
  const tail = links.length ? ' Follow: ' + links.join(' · ') : '';
  const head = `🎧 Next mixtape on KALBASSFM: ${s.dj || 'a guest DJ'} — ${s.style || 'DJ set'}.`;
  const budget = 200 - tail.length;
  return (head.length > budget ? head.slice(0, Math.max(0, budget - 1)).trimEnd() + '…' : head) + tail;
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

// Lien clientId -> pseudo impose par l'admin (moderation d'un pseudo
// offensant/inapproprie), sans badge supporter. Priorite plus faible que
// chat:supporters cote api/chat.js (un supporter marque garde son nom+badge).
async function setChatNickname(clientId, name) {
  const kv = kvClient();
  if (!kv || !clientId) return false;
  if (name) await kv('hset', 'chat:nicknames', clientId, name.slice(0, 30));
  else await kv('hdel', 'chat:nicknames', clientId);
  return true;
}

// Reecrit le pseudo dans les messages deja postes par ce clientId (pas
// seulement les messages a venir). Necessite que chaque message stocke son
// clientId (ajoute cote api/chat.js, jamais renvoye au GET public — voir le
// commentaire associe la-bas). LSET met a jour en place, sans reordonner la
// liste. Best effort silencieux : n'affecte jamais le resultat de /rename.
//
// chat:messages recoit des LPUSH concurrents (n'importe quel auditeur qui
// poste pendant qu'on boucle ici decale tous les index suivants) : on
// reverifie via LINDEX que l'entree n'a pas bouge juste avant d'ecrire, pour
// ne jamais corrompre le message d'un autre auditeur. Une entree decalee est
// simplement sautee (sans risque de la relancer : /rename_nick/rename sont
// idempotents) plutot que de risquer un LSET au mauvais index.
async function renameHistory(clientId, name) {
  const kv = kvClient();
  if (!kv || !clientId) return;
  try {
    const lj = await kv('lrange', 'chat:messages', '0', '-1');
    const raw = lj.result || [];
    for (let i = 0; i < raw.length; i++) {
      let msg;
      try { msg = JSON.parse(raw[i]); } catch { continue; }
      if (msg.clientId === clientId) {
        const cur = await kv('lindex', 'chat:messages', String(i));
        if (cur.result !== raw[i]) continue;
        msg.nick = name;
        await kv('lset', 'chat:messages', String(i), JSON.stringify(msg));
      }
    }
  } catch {}
}

// Rattrapage pour l'historique poste AVANT l'ajout du clientId dans chaque
// message (voir renameHistory ci-dessus) : matche sur le pseudo affiche tel
// quel plutot que sur le clientId. A manier avec discernement — le pseudo
// auto-genere ("Listener-XXXX", derive du clientId modulo 9000) n'est pas
// garanti unique entre auditeurs differents, contrairement au clientId.
// Exclut les messages admin (nick "Admin") par securite. Meme garde-fou
// LINDEX que renameHistory contre les LPUSH concurrents — voir ce commentaire.
// Idempotent : si le compte renvoye est inferieur au nombre attendu (des
// entrees ont decale pendant la boucle), relancer la meme commande rattrape
// le reste sans risque.
async function renameHistoryByNick(oldNick, name) {
  const kv = kvClient();
  if (!kv) return 0;
  let count = 0;
  try {
    const lj = await kv('lrange', 'chat:messages', '0', '-1');
    const raw = lj.result || [];
    for (let i = 0; i < raw.length; i++) {
      let msg;
      try { msg = JSON.parse(raw[i]); } catch { continue; }
      if (msg.nick === oldNick && !msg.admin) {
        const cur = await kv('lindex', 'chat:messages', String(i));
        if (cur.result !== raw[i]) continue;
        msg.nick = name;
        await kv('lset', 'chat:messages', String(i), JSON.stringify(msg));
        count++;
      }
    }
  } catch {}
  return count;
}

// Bandeau epingle automatiquement pendant une pause, pour que les auditeurs
// comprennent pourquoi l'envoi est bloque plutot que de croire a un bug.
const PAUSE_BANNER = '⏸ Chat temporarily paused — back soon!';

// Sauvegarde l'annonce eventuellement deja epinglee (/pin) avant de la
// remplacer par le bandeau de pause, pour pouvoir la restaurer a la reprise
// au lieu de la perdre.
async function pauseChatWithBanner() {
  const kv = kvClient();
  if (!kv) return false;
  const prev = await kv('get', 'chat:pinned');
  if (prev.result) await kv('set', 'chat:pinned:backup', prev.result);
  else await kv('del', 'chat:pinned:backup');
  await kv('set', 'chat:paused', '1');
  await kv('set', 'chat:pinned', PAUSE_BANNER);
  return true;
}

async function resumeChatRestorePin() {
  const kv = kvClient();
  if (!kv) return false;
  await kv('del', 'chat:paused');
  const backup = await kv('get', 'chat:pinned:backup');
  if (backup.result) {
    await kv('set', 'chat:pinned', backup.result);
    await kv('del', 'chat:pinned:backup');
  } else {
    // Ne retire le bandeau que s'il s'agit bien du bandeau de pause — l'admin
    // a pu poser un /pin different pendant la pause, on ne veut pas l'ecraser.
    const cur = await kv('get', 'chat:pinned');
    if (cur.result === PAUSE_BANNER) await kv('del', 'chat:pinned');
  }
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
