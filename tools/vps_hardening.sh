#!/usr/bin/env bash
# Durcissement du VPS KALBASSFM (167.233.226.128) — a lancer EN ROOT, sur le
# VPS, via PuTTY. Ecrit le 2026-09-17 apres l'audit ; je n'ai pas d'acces SSH
# depuis Claude Code, ce script est donc a executer a la main :
#
#     bash vps_hardening.sh
#
# Chaque bloc est independant et se relance sans dommage. Les blocs marques
# [OPTIONNEL] sont commentes : lire l'explication avant de les activer.
set -euo pipefail

echo "=== 1. SSH : refuser les mots de passe, cle uniquement ==="
# GARDE-FOU : ne coupe les mots de passe QUE si une cle publique est deja
# installee, sinon on se verrouille dehors. Pour poser une cle depuis Windows :
#     ssh-keygen -t ed25519            (une fois, sur le PC)
#     type %USERPROFILE%\.ssh\id_ed25519.pub | ssh root@167.233.226.128 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
# puis tester une NOUVELLE connexion sans mot de passe AVANT de relancer ce script.
if [ -s /root/.ssh/authorized_keys ]; then
  cat > /etc/ssh/sshd_config.d/90-kalbassfm.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
MaxAuthTries 3
EOF
  sshd -t && systemctl reload ssh && echo "  mots de passe SSH desactives (cle seule)"
else
  echo "  AUCUNE cle dans /root/.ssh/authorized_keys : bloc saute (voir ci-dessus)."
fi

echo "=== 2. fail2ban : bannir les IP qui martelent SSH ==="
apt-get install -y -q fail2ban >/dev/null
cat > /etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
maxretry = 4
findtime = 10m
bantime = 24h
EOF
systemctl enable --now fail2ban >/dev/null
fail2ban-client reload >/dev/null && echo "  fail2ban actif : $(fail2ban-client status sshd | grep 'Currently banned')"

echo "=== 3. Pare-feu : n'ouvrir que ce qui sert ==="
# 22 SSH · 80/443 AzuraCast (nginx, HTTPS force depuis le 2026-09-17) · 2022 SFTP.
# Icecast ecoute aussi en direct sur 8000 (HTTP, sans TLS) : le player et
# l'URL publique passent par https://kalbassfm.duckdns.org/listen/..., donc
# 8000 n'a pas besoin d'etre joignable depuis Internet. Il est ferme ici ;
# si un auditeur se plaint d'un flux « :8000 » qui ne repond plus, c'est ca.
apt-get install -y -q ufw >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow 2022/tcp >/dev/null
ufw --force enable >/dev/null
ufw status numbered

echo "=== 4. AzuraCast 0.23.7 -> derniere version ==="
# Coupe le flux ~1-2 min le temps du redemarrage des conteneurs : a lancer
# hors du dimanche 18h (mixtape). Repond aux questions tout seul (-y).
cd /var/azuracast && ./docker.sh update -y
echo "  version : $(./docker.sh cli azuracast:version 2>/dev/null | tail -1)"

echo
echo "Termine. A verifier depuis le PC :"
echo "  curl -sI http://kalbassfm.duckdns.org/ | grep -i location     -> https://"
echo "  curl -s -m 5 -o /dev/null -w '%{http_code}' http://167.233.226.128:8000/ ; echo   -> doit echouer (timeout)"
