/* Candidature d'un DJ pour passer son mix sur la radio, relayee a l'admin
   Telegram (jamais publiee dans le chat) et archivee dans Redis.

   Difference importante avec api/request.js : ici le lien est le coeur de la
   soumission, donc PAS de filtre anti-liens — a la place, l'URL du set est
   validee (http(s) + un point) et c'est le SEUL champ ou une URL est acceptee.
   Les autres champs (nom, style) sont au contraire filtres contre les liens,
   sinon le formulaire devient un canal de spam a trois lignes.

   Sans bot configure (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID), renvoie
   { enabled:false } et le front masque le bouton "Submit a mix".

   Le store Redis (KV_REST_API_URL / KV_REST_API_TOKEN, memes cles que
   api/chat.js) est optionnel : sans lui, plus de rate-limit ni d'archive, mais
   la soumission part quand meme vers Telegram — mieux vaut une candidature
   livree sans garde-fou qu'une candidature perdue.

   Structure Redis :
   - liste "mix:submissions"      : JSON {id, dj, email, url, style, ts}, LPUSH + LTRIM a 49
                                    (relu par /submissions dans api/telegram.js)
   - cle "mix:rate:<clientId>"    : posee avec EX 600 NX, 1 candidature / 10 min
   - set  "chat:banned"           : partage avec le chat — un auditeur banni ne
                                    peut pas non plus soumettre de mix.
*/
const LINK_RE = /(https?:\/\/|www\.|\b[a-z0-9-]+\.(com|net|org|fr|io|co|link|to|me|tv|info|biz|xyz|gg|app|shop))/i;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const URL_RE = /^https?:\/\/[^\s.]+\.[^\s]{2,}$/i;

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
  const dj = (body.dj || '').toString().trim().slice(0, 60);
  const email = (body.email || '').toString().trim().slice(0, 120);
  const url = (body.url || '').toString().trim().slice(0, 300);
  const style = (body.style || '').toString().trim().slice(0, 60);

  if (!clientId) return res.status(200).json({ enabled: true, ok: false });
  if (!dj || !email || !url || !style) return res.status(200).json({ enabled: true, ok: false, invalid: 'missing' });
  if (!EMAIL_RE.test(email)) return res.status(200).json({ enabled: true, ok: false, invalid: 'email' });
  if (!URL_RE.test(url)) return res.status(200).json({ enabled: true, ok: false, invalid: 'url' });
  // Le lien n'a droit de cite que dans le champ "url" : ailleurs, c'est du spam.
  if (LINK_RE.test(dj) || LINK_RE.test(style)) return res.status(200).json({ enabled: true, ok: false, blocked: 'link' });

  if (kv) {
    try {
      const bannedJ = await kv('sismember', 'chat:banned', clientId);
      if (bannedJ.result) return res.status(200).json({ enabled: true, ok: false, banned: true });
    } catch {}
    try {
      const lock = await kv('set', `mix:rate:${clientId}`, '1', 'EX', '600', 'NX');
      if (lock.result !== 'OK') return res.status(200).json({ enabled: true, ok: false, rateLimited: true });
    } catch {}
  }

  const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

  // L'archive Redis passe AVANT Telegram : c'est le filet de securite si la
  // notification echoue (bot revoque, panne reseau). Un echec d'ecriture ne
  // doit en revanche jamais empecher l'envoi.
  if (kv) {
    try {
      await kv('lpush', 'mix:submissions', JSON.stringify({ id, dj, email, url, style, ts: Date.now() }));
      await kv('ltrim', 'mix:submissions', '0', '49');
    } catch {}
  }

  try {
    const r = await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // disable_web_page_preview : la carte SoundCloud/Drive doublerait la
      // taille de chaque notification pour aucune information utile.
      body: JSON.stringify({
        chat_id: adminChat,
        parse_mode: 'HTML',
        disable_web_page_preview: true,
        text: `🎛 <b>Nouvelle candidature mix</b>\n`
          + `DJ : ${escapeHtml(dj)}\n`
          + `Style : ${escapeHtml(style)}\n`
          + `Mail : ${escapeHtml(email)}\n`
          + `Set : ${escapeHtml(url)}\n`
          + `<code>${escapeHtml(clientId)}</code>`,
        reply_markup: { inline_keyboard: [[
          { text: '🔨 Bannir', callback_data: 'ban:' + clientId },
        ]] },
      }),
    });
    if (!r.ok) return res.status(200).json({ enabled: false, ok: false });
    return res.status(200).json({ enabled: true, ok: true });
  } catch {
    return res.status(200).json({ enabled: false, ok: false });
  }
}
