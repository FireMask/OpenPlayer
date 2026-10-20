#!/bin/bash
# Instala OpenPlayer.Service en /opt/openplayer como unidad systemd (SPEC 04). Idempotente.
# Uso: sudo bash install.sh <ruta.tgz> <unit.service> <usuario-que-despliega>
set -euo pipefail

if [ $# -ne 3 ]; then
    echo "Usage: sudo bash install.sh <publish.tgz> <openplayer.service> <deploy-user>" >&2
    exit 2
fi
TGZ=$1
UNIT=$2
DEPLOYER=$3
DIR=/opt/openplayer
SOCK=/run/openplayer/hardware.sock

[ "$(id -u)" -eq 0 ] || { echo "Must run as root (sudo)" >&2; exit 1; }
[ -f "$TGZ" ] || { echo "Not found: $TGZ" >&2; exit 1; }
[ -f "$UNIT" ] || { echo "Not found: $UNIT" >&2; exit 1; }
id "$DEPLOYER" >/dev/null 2>&1 || { echo "Unknown user: $DEPLOYER" >&2; exit 1; }

# Usuario de sistema sin login ni home; el que despliega entra al grupo para usar el socket (socat).
getent group openplayer >/dev/null || groupadd --system openplayer
id openplayer >/dev/null 2>&1 ||
    useradd --system --gid openplayer --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin openplayer
usermod -aG openplayer "$DEPLOYER"

# player.json existente se conserva: puede tener ajustes hechos en la Pi.
mkdir -p "$DIR"
tar -xzmf "$TGZ" -C "$DIR" --no-same-owner --exclude=./player.json
[ -f "$DIR/player.json" ] || tar -xzmf "$TGZ" -C "$DIR" --no-same-owner ./player.json
chown -R root:root "$DIR"
chmod -R u=rwX,go=rX "$DIR"
chmod 755 "$DIR/OpenPlayer.Service"

install -m 644 "$UNIT" /etc/systemd/system/openplayer.service
systemctl daemon-reload
systemctl enable --quiet openplayer
# Un "failed" previo por StartLimitBurst bloquearía el restart.
systemctl reset-failed openplayer 2>/dev/null || true
systemctl restart openplayer

# Type=simple da "active" apenas arranca el proceso; el socket confirma que el Service llegó a escuchar.
for _ in $(seq 30); do
    if systemctl is-active --quiet openplayer && [ -S "$SOCK" ]; then
        echo "openplayer: active, listening on $SOCK"
        exit 0
    fi
    sleep 0.5
done
echo "openplayer did not become active" >&2
journalctl -u openplayer -n 20 --no-pager >&2
exit 1
