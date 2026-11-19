#!/bin/sh
# Bootstrap the NetSync failover backend on an Oracle Always-Free VM
# (Ubuntu 24.04, arm64 — works on amd64 too).
#
# Usage (as the ubuntu user, from the cloud_backend dir of the repo):
#   sudo sh deploy/setup-oracle.sh
# Then edit .env (SUPABASE_*, DEVICE_STORE=supabase, CORS_ORIGINS, DOMAIN)
# and: docker compose -f deploy/docker-compose.yml --env-file .env up -d
set -e

# 1) Docker
if ! command -v docker >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y docker.io docker-compose-v2
  usermod -aG docker ubuntu
fi

# 2) Host firewall — Ubuntu images ship iptables rules that block the VCN;
#    keep ssh + http/https, drop the default-deny INPUT tail rule if present.
iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null \
  || iptables -I INPUT -p tcp --dport 443 -j ACCEPT
iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null \
  || iptables -I INPUT -p tcp --dport 80 -j ACCEPT
apt-get install -y iptables-persistent >/dev/null 2>&1 || true
netfilter-persistent save >/dev/null 2>&1 || true

# 3) Idle-VM keep-alive — Oracle can reclaim Always-Free VMs under ~20% CPU
#    for a week; a 30-second busy loop twice an hour keeps the window safe.
if ! crontab -l 2>/dev/null | grep -q "netsync-keepalive"; then
  (crontab -l 2>/dev/null; \
    echo "*/30 * * * * sh -c 'end=\$((SECONDS+30)); while [ \$SECONDS -lt \$end ]; do :; done' # netsync-keepalive") | crontab -
fi

echo "done — now create ../.env (see .env.example, set DEVICE_STORE=supabase"
echo "and DOMAIN=your-host) then:"
echo "  docker compose -f deploy/docker-compose.yml --env-file .env up -d"
