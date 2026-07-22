/* Chat live anonyme entre auditeurs, partage via Vercel Storage / Upstash Redis
   (variables d'env KV_REST_API_URL + KV_REST_API_TOKEN, memes que api/supporters.js
   et api/flappy.js). Sans store configure, renvoie { enabled:false } et le front bascule en mode
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

   Charge via fs.readFileSync plutot qu'un import JSON direct : evite toute
   dependance a l'assertion d'import JSON (`with { type: 'json' }`), pas
   uniformement supportee selon la version de Node -- readFileSync fonctionne
   partout, bundle ou non. */
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
const bpmTable = JSON.parse(
  fs.readFileSync(fileURLToPath(new URL('./bpm-table.json', import.meta.url)), 'utf8')
);

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

// Messages automatiques d'animation du chat, postes "paresseusement" au fil
// des GET (le chat est polle toutes les 3s par les auditeurs — pas besoin de
// cron). Un verrou Redis SET NX par annonce et par jour garantit un envoi
// unique meme avec des dizaines de clients simultanes ; si personne n'ecoute
// pendant la fenetre de tir (15 premieres minutes de l'heure), l'annonce est
// simplement sautee — personne n'aurait ete la pour la lire.
const ANNOUNCEMENTS = [
  { h: 6,  key: 'sunrise',   text: '🌅 6AM UTC-4 — Sunrise: ambient, downtempo & mellow grooves to open the day' },
  { h: 9,  key: 'groove',    text: '☀️ 9AM UTC-4 — Solar Groove: disco, funk & nu-disco until 1PM' },
  { h: 13, key: 'breeze',    text: '🌴 1PM UTC-4 — Trade Winds: eclectic house all afternoon' },
  { h: 17, key: 'sunset',    text: '🌇 5PM UTC-4 — Sunset: deep & melodic house for the golden hour' },
  { h: 20, key: 'warmup',    text: '🔥 8PM UTC-4 — Warm-up: tech house, slowly heating up...' },
  { h: 23, key: 'peak',      text: '⚡ 11PM UTC-4 — Peak time: techno until 2AM, turn it up' },
  { h: 2,  key: 'deepnight', text: '🌙 2AM UTC-4 — Deep Night: deep, minimal, dub... for the night owls' },
];
const ANNOUNCE_WINDOW_MIN = 15;

async function maybeAnnounce(kv) {
  try {
    const mq = new Date(Date.now() - 4 * 3600 * 1000); // heure Martinique (UTC-4 fixe, pas de DST)
    const a = ANNOUNCEMENTS.find((x) => x.h === mq.getUTCHours() && mq.getUTCMinutes() < ANNOUNCE_WINDOW_MIN);
    if (!a) return;
    const day = mq.toISOString().slice(0, 10);
    const lock = await kv('set', `chat:auto:${a.key}:${day}`, '1', 'EX', '90000', 'NX');
    if (lock.result !== 'OK') return;
    const msg = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8), nick: '📻 KALBASSFM', text: a.text, ts: Date.now(), admin: true, auto: true };
    await kv('lpush', 'chat:messages', JSON.stringify(msg));
    await kv('ltrim', 'chat:messages', '0', '99');
  } catch {}
}

// Annonce ponctuelle (pas quotidienne comme ANNOUNCEMENTS ci-dessus) pour un
// lancement de feature : verrou SET NX sans expiration -> part une seule fois,
// au premier GET qui arrive apres le deploiement, quel que soit le nombre
// d'auditeurs connectes en meme temps.
async function maybeAnnounceOnce(kv) {
  try {
    const lock = await kv('set', 'chat:announced:flappy', '1', 'NX');
    if (lock.result !== 'OK') return;
    const msg = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
      nick: '📻 KALBASSFM',
      text: '🐦 New: Flappy Kalbass is live — tap the bird icon up top and go smash the leaderboard!',
      ts: Date.now(),
      admin: true,
      auto: true,
    };
    await kv('lpush', 'chat:messages', JSON.stringify(msg));
    await kv('ltrim', 'chat:messages', '0', '99');
  } catch {}
}

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
      await maybeAnnounce(kv);
      await maybeAnnounceOnce(kv);
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
  // Anti-usurpation : le pseudo reserve a l'admin (messages du bot Telegram,
  // flag admin:true pose cote serveur) ne peut pas etre pris par un auditeur.
  let nick = (body.nick || 'Listener').toString().slice(0, 30);
  if (/kalbassfm/i.test(nick)) nick = 'Listener';
  const text = (body.text || '').toString().trim().slice(0, 200);

  if (!clientId || !text) return res.status(200).json({ enabled: true, ok: false });

  let supporterName = null;
  let renamedNick = null;
  try {
    const [pausedJ, bannedJ, supporterJ, nicknameJ] = await Promise.all([
      kv('get', 'chat:paused'),
      kv('sismember', 'chat:banned', clientId),
      kv('hget', 'chat:supporters', clientId),
      kv('hget', 'chat:nicknames', clientId),
    ]);
    if (pausedJ.result) return res.status(200).json({ enabled: true, ok: false, paused: true });
    if (bannedJ.result) return res.status(200).json({ enabled: true, ok: false, banned: true });
    supporterName = supporterJ.result || null;
    renamedNick = nicknameJ.result || null;
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
    // A defaut de badge supporter, un pseudo impose par l'admin via /rename
    // (hash chat:nicknames, moderation d'un pseudo offensant) prend le pas
    // sur celui choisi par le client.
    const finalNick = supporterName || renamedNick || nick;
    const msg = supporterName
      ? { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8), nick: finalNick, text, ts: Date.now(), supporter: true, clientId }
      : { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8), nick: finalNick, text, ts: Date.now(), clientId };
    await kv('lpush', 'chat:messages', JSON.stringify(msg));
    await kv('ltrim', 'chat:messages', '0', '99');
    // Compteur quotidien (jour Martinique UTC-4) lu par /stats du bot Telegram.
    const day = new Date(Date.now() - 4 * 3600 * 1000).toISOString().slice(0, 10);
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
        const correct = Math.abs(guess - Math.round(track.bpm)) <= 1;
        const reply = correct
          ? `🎉 NICE ONE ${finalNick}! ${track.artist} — ${track.title} is indeed ${Math.round(track.bpm)} BPM!`
          : `😅 NOT QUITE ${finalNick} — try again!`;
        const botMsg = {
          id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
          nick: '📻 KALBASSFM', text: reply, ts: Date.now(), admin: true,
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
