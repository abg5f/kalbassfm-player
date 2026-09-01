/* Chat live anonyme entre auditeurs, partage via Vercel Storage / Upstash Redis
   (variables d'env KV_REST_API_URL + KV_REST_API_TOKEN, memes que api/supporters.js
   et api/flappy.js). Sans store configure, renvoie { enabled:false } et le front bascule en mode
   degrade (panneau masque) — jamais d'erreur visible.

   Pas d'identification : chaque auditeur a un clientId anonyme genere cote
   navigateur (localStorage), utilise pour le pseudo affiche et le rate-limit.

   Structure Redis :
   - liste "chat:messages"       : JSON {id, nick, text, ts} par entree, LPUSH + LTRIM a 99
   - cle "chat:rate:<clientId>"  : pose avec EX 3 NX, bloque l'envoi suivant pendant 3s
   - hash "chat:pseudos"         : clientId -> pseudo choisi par l'auditeur via
                                   "Set nickname" (POST {clientId, setNick}).
                                   Pas de compte : attache au seul clientId
                                   local, donc perdu si le cache/localStorage
                                   est efface ou sur un autre appareil (retombe
                                   alors sur le pseudo Listener-XXXX par defaut).

   Anti-autopromo : tout message contenant un lien (http(s)://, www., ou un
   domaine du type "motacle.com") est refuse avant meme le rate-limit — pas
   de bannissement, juste un refus systematique des liens dans le chat.
*/
const LINK_RE = /(https?:\/\/|www\.|\b[a-z0-9-]+\.(com|net|org|fr|io|co|link|to|me|tv|info|biz|xyz|gg|app|shop))/i;

/* ---- Jeu "devine le BPM" ----
   Un message compose uniquement d'un nombre plausible (60-200) est traite
   comme une tentative de deviner le BPM du morceau en cours -- il reste
   affiche normalement dans le chat (rien de special cote front), mais
   declenche en plus une reponse automatique du bot juste apres. bpm-table.json
   (genere par tools/export_bpm_table.py a partir des tags ID3 reels + du BPM
   Essentia de tools/metadata.json) associe artiste+titre exacts -> BPM ; ce
   sont les memes tags qu'AzuraCast affiche, donc le matching est direct. Le
   BPM n'existe nulle part dans l'API AzuraCast elle-meme (verifie : le champ
   custom_fields est vide) -- cette table est la seule source de verite.

   Import JSON statique + assertion de type : la premiere version utilisait
   fs.readFileSync(import.meta.url), qui plantait la fonction entiere en prod
   (500 sur /api/chat, chat invisible pour tous les auditeurs) -- evite donc
   totalement import.meta.url ici. L'assertion `with { type: 'json' }` est
   necessaire pour le loader ESM natif de Node (verifie en local) ; les
   bundlers (esbuild, utilise par Vercel) la respectent aussi sans probleme. */
import bpmTable from './bpm-table.json' with { type: 'json' };

const AZURACAST_BASE = 'https://kalbassfm.duckdns.org';
const STATION = 'kalbassfm';
// AzuraCast rejette parfois les requetes API sans User-Agent credible
// (detection anti-crawler, deja rencontre sur /requests dans api/telegram.js).
const BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

function normalizeKey(s) {
  return (s || '').toLowerCase().trim().replace(/\s+/g, ' ');
}

// Index construit une fois au chargement du module, reutilise tant que
// l'instance serverless reste chaude (pas de cout par requete).
const BPM_INDEX = new Map();
for (const t of bpmTable) {
  BPM_INDEX.set(normalizeKey(t.artist) + '|' + normalizeKey(t.title), t.bpm);
}

function parseBpmGuess(text) {
  const m = /^(\d{2,3})$/.exec(text);
  if (!m) return null;
  const n = parseInt(m[1], 10);
  return (n >= 60 && n <= 200) ? n : null;
}

// Retourne null si le morceau en cours n'est pas dans bpm-table.json (jamais
// analyse par le pipeline Essentia) ou en cas d'erreur reseau -- le jeu reste
// alors silencieux plutot que de repondre "je ne sais pas" a chaque tentative.
async function getCurrentTrackBpm() {
  try {
    const r = await fetch(`${AZURACAST_BASE}/api/nowplaying/${STATION}`, {
      headers: { 'User-Agent': BROWSER_UA },
    });
    if (!r.ok) return null;
    const d = await r.json();
    const song = (d.now_playing && d.now_playing.song) || {};
    if (!song.title) return null;
    const bpm = BPM_INDEX.get(normalizeKey(song.artist) + '|' + normalizeKey(song.title));
    if (bpm === undefined) return null;
    return { bpm, artist: song.artist, title: song.title };
  } catch {
    return null;
  }
}

// Reactive le 2026-07-21 : Upstash passe en Pay As You Go + Top 5 retire
// (gros consommateur), donc quota nettement moins a risque.
const REDIS_PAUSED = false;

/* Messages automatiques d'animation du chat — RETIRES le 2026-07-28.

   Il y avait deux mecanismes, tous deux supprimes :

   1. ANNOUNCEMENTS : 7 annonces quotidiennes de transition de programme
      ("1PM UTC-4 — Trade Winds: eclectic house all afternoon"), postees
      paresseusement au fil des GET avec un verrou Redis par annonce et par
      jour. Retirees a la demande : elles polluaient le fil, qui recoit peu de
      messages d'auditeurs — deux annonces automatiques suffisaient a noyer une
      vraie conversation. Un indicateur "Vibe now" sous le titre en cours a
      brievement affiche le bac reellement joue (2026-08-31, champ `playlist`
      de nowplaying) avant d'etre retire a son tour (2026-09-01, juge peu
      utile) : aucune info de programmation n'est plus resurfacee dans le
      player aujourd'hui.

   2. maybeAnnounceOnce : annonce unique de lancement d'une feature (Flappy),
      protegee par un verrou SET NX permanent. Le verrou etant pose depuis
      longtemps, la fonction ne pouvait plus rien poster — mais elle executait
      quand meme UNE COMMANDE REDIS A CHAQUE GET du chat, soit une ecriture
      inutile toutes les 6 secondes et par auditeur. Retiree aussi : c'est
      exactement le type de gaspillage qui a epuise le quota Upstash le
      2026-07-21.

   Consequence : un GET du chat ne fait plus que ses 3 lectures utiles
   (lrange + hgetall + get), sans ecriture. */

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(204).end();

  const base = process.env.KV_REST_API_URL;
  const token = process.env.KV_REST_API_TOKEN;
  if (!base || !token || REDIS_PAUSED) return res.status(200).json({ enabled: false, messages: [] });

  const headers = { Authorization: `Bearer ${token}` };
  const kv = (...segments) => fetch(`${base}/${segments.map(encodeURIComponent).join('/')}`, { headers }).then(r => r.json());

  // ---- GET : les 50 derniers messages (plus recent en premier) ----
  if (req.method === 'GET') {
    try {
      const [lj, dj, pj] = await Promise.all([
        kv('lrange', 'chat:messages', '0', '49'),
        kv('hgetall', 'chat:deleted'),
        kv('get', 'chat:pinned'),
      ]);
      // lj.result absent (pas juste vide) = erreur Upstash (ex: quota mensuel
      // depasse) plutot qu'une vraie liste vide — sans cette distinction,
      // l'appel "reussit" silencieusement avec messages:[] et le front efface
      // le chat au lieu de garder le dernier contenu affiche.
      if (lj.result === undefined) throw new Error('kv-error');
      const raw = lj.result || [];
      const deletedFields = dj.result || [];
      const deletedIds = new Set();
      for (let i = 0; i < deletedFields.length; i += 2) deletedIds.add(deletedFields[i]);
      // clientId n'est stocke dans le message que pour permettre a /rename
      // (api/telegram.js) de reecrire l'historique — jamais expose aux
      // auditeurs, meme principe que chat:banned/chat:nicknames.
      const messages = raw
        .map((s) => { try { return JSON.parse(s); } catch { return null; } })
        .filter((m) => m && !deletedIds.has(m.id))
        .map(({ clientId, ...m }) => m);
      return res.status(200).json({ enabled: true, messages, pinned: pj.result || null });
    } catch {
      return res.status(200).json({ enabled: false, messages: [] });
    }
  }

  // ---- POST : envoyer un message (rate-limit serveur 1 / 3s / clientId) ----
  const body = req.body || {};
  const rawClientId = (body.clientId || '').toString();
  const clientId = rawClientId.slice(0, 64).replace(/[^a-zA-Z0-9_-]/g, '') || null;

  // ---- POST (action) : choisir son pseudo, stocke dans chat:pseudos
  // (clientId -> pseudo) pour rester attache a cet appareil/navigateur tant
  // que kfm_client_id vit en local -- pas de compte, pas de sync cross-device.
  // Meme regle anti-usurpation que le pseudo envoye avec un message.
  if (typeof body.setNick === 'string') {
    if (!clientId) return res.status(200).json({ enabled: true, ok: false });
    const desired = body.setNick.toString().trim().slice(0, 30);
    if (!desired || /kalbassfm|^admin$|^bpm\s*guesser$/i.test(desired)) {
      return res.status(200).json({ enabled: true, ok: false });
    }
    try {
      await kv('hset', 'chat:pseudos', clientId, desired);
      return res.status(200).json({ enabled: true, ok: true, nick: desired });
    } catch {
      return res.status(200).json({ enabled: false, ok: false });
    }
  }

  // Anti-usurpation : les pseudos reserves aux bots (admin Telegram et
  // BPM GUESSER, flag admin:true pose cote serveur dans les deux cas) ne
  // peuvent pas etre pris par un auditeur.
  let nick = (body.nick || 'Listener').toString().slice(0, 30);
  if (/kalbassfm|^admin$|^bpm\s*guesser$/i.test(nick)) nick = 'Listener';
  const text = (body.text || '').toString().trim().slice(0, 200);

  if (!clientId || !text) return res.status(200).json({ enabled: true, ok: false });

  let supporterName = null;
  let renamedNick = null;
  let userPseudo = null;
  try {
    const [pausedJ, bannedJ, supporterJ, nicknameJ, pseudoJ] = await Promise.all([
      kv('get', 'chat:paused'),
      kv('sismember', 'chat:banned', clientId),
      kv('hget', 'chat:supporters', clientId),
      kv('hget', 'chat:nicknames', clientId),
      kv('hget', 'chat:pseudos', clientId),
    ]);
    if (pausedJ.result) return res.status(200).json({ enabled: true, ok: false, paused: true });
    if (bannedJ.result) return res.status(200).json({ enabled: true, ok: false, banned: true });
    supporterName = supporterJ.result || null;
    renamedNick = nicknameJ.result || null;
    userPseudo = pseudoJ.result || null;
  } catch {
    return res.status(200).json({ enabled: false, ok: false });
  }

  if (LINK_RE.test(text)) return res.status(200).json({ enabled: true, ok: false, blocked: 'link' });

  try {
    const lockJ = await kv('set', `chat:rate:${clientId}`, '1', 'EX', '3', 'NX');
    if (lockJ.result !== 'OK') return res.status(200).json({ enabled: true, ok: false, rateLimited: true });

    // supporter:true et le nom associe viennent EXCLUSIVEMENT du hash Redis
    // chat:supporters (pose par /mark_supporter dans api/telegram.js) —
    // jamais du pseudo envoye par le client, meme principe que admin:true.
    // Ordre de priorite : badge supporter > renommage force par l'admin
    // (moderation d'un pseudo offensant) > pseudo choisi par l'auditeur via
    // "Set nickname" (chat:pseudos, source de verite serveur pour cet
    // appareil) > pseudo envoye avec le message (fallback, ex: Listener-XXXX).
    const finalNick = supporterName || renamedNick || userPseudo || nick;
    const msg = supporterName
      ? { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8), nick: finalNick, text, ts: Date.now(), supporter: true, clientId }
      : { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8), nick: finalNick, text, ts: Date.now(), clientId };
    await kv('lpush', 'chat:messages', JSON.stringify(msg));
    await kv('ltrim', 'chat:messages', '0', '99');
    // Compteur quotidien (jour UTC) lu par /stats du bot Telegram.
    const day = new Date().toISOString().slice(0, 10);
    await kv('incr', `stats:msg:${day}`);
    await kv('expire', `stats:msg:${day}`, '172800');
    await notifyTelegram(kv, msg, clientId);

    // Jeu "devine le BPM" : le message du joueur reste un message normal
    // (ci-dessus) ; s'il ressemble a une tentative, le bot repond en plus.
    // getCurrentTrackBpm() ne leve jamais -- un echec ne doit jamais faire
    // regresser la reponse ok:true deja acquise pour le message du joueur.
    const guess = parseBpmGuess(text);
    if (guess !== null) {
      const track = await getCurrentTrackBpm();
      if (track) {
        // Essentia detecte tres souvent le drum & bass / la jungle en
        // DEMI-TEMPO (87 pour un morceau reellement a 174 : Logistics, Netsky,
        // Hybrid Minds...). Avec une comparaison stricte, un auditeur qui
        // annonce le vrai tempo se voyait repondre qu'il a faux — pire que le
        // silence, et la bibliotheque compte desormais plus de 100 titres DnB.
        // On accepte donc aussi le double et la moitie de la valeur stockee.
        // L'alternative n'est ouverte que la ou l'ambiguite existe vraiment :
        // sous 100 BPM en electronique, la valeur est presque toujours un
        // demi-tempo ; au-dessus de 150, le double serait absurde. Une house a
        // 125 reste donc strictement a 125 (sinon "62" serait accepte et le
        // bot repondrait "is indeed 63 BPM", ce qui n'a aucun sens).
        const base = Math.round(track.bpm);
        const candidates = [base];
        if (base < 100) candidates.push(base * 2);
        if (base > 150) candidates.push(Math.round(base / 2));
        const hit = candidates.find((v) => Math.abs(guess - v) <= 1);
        const reply = hit
          ? `🎉 NICE ONE ${finalNick}! ${track.artist} — ${track.title} is indeed ${hit} BPM!`
          : `😅 NOT QUITE ${finalNick} — try again!`;
        const botMsg = {
          id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
          nick: 'BPM GUESSER', text: reply, ts: Date.now(), admin: true,
        };
        await kv('lpush', 'chat:messages', JSON.stringify(botMsg));
        await kv('ltrim', 'chat:messages', '0', '99');
      }
    }

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
async function notifyTelegram(kv, msg, clientId) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) return;
  try {
    const r = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: `${escapeHtml(msg.nick)}: ${escapeHtml(msg.text)}\n<code>${escapeHtml(clientId)}</code>`,
        reply_markup: { inline_keyboard: [[
          { text: '↩️ Répondre', callback_data: 'rep:' + msg.id },
          { text: '🗑 Supprimer', callback_data: 'del:' + msg.id },
          { text: '🔨 Bannir', callback_data: 'ban:' + clientId },
        ]] },
      }),
    });
    // Permet a l'admin de repondre nativement (Telegram "Reply") a cette
    // notification : on retient quel message live elle represente, pour que
    // api/telegram.js puisse retrouver le fil quand la reponse arrive.
    const j = await r.json().catch(() => null);
    const tgMessageId = j && j.result && j.result.message_id;
    if (tgMessageId) {
      await kv('set', `chat:tgmap:${tgMessageId}`, JSON.stringify({ id: msg.id, nick: msg.nick, text: msg.text }), 'EX', '259200');
    }
  } catch {}
}
