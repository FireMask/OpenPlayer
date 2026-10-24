#!/bin/bash
# Instala OpenPlayer.Service (SPEC 04), el hardware agent (SPEC 05, pantalla SPEC 17) y el web agent (SPEC 08) en /opt/openplayer como unidades systemd. Idempotente.
# Uso: sudo bash install.sh <ruta.tgz> <openplayer.service> <usuario-que-despliega>
# El .tgz trae el publish del Service, hardware-agent/ y web-agent/; las unidades de los agentes van junto a openplayer.service.
set -euo pipefail

if [ $# -ne 3 ]; then
    echo "Usage: sudo bash install.sh <publish.tgz> <openplayer.service> <deploy-user>" >&2
    exit 2
fi
TGZ=$1
UNIT=$2
AGENT_UNIT=$(dirname "$UNIT")/openplayer-hardware.service
WEB_UNIT=$(dirname "$UNIT")/openplayer-web.service
DEPLOYER=$3
DIR=/opt/openplayer
SOCK=/run/openplayer/hardware.sock

[ "$(id -u)" -eq 0 ] || { echo "Must run as root (sudo)" >&2; exit 1; }
[ -f "$TGZ" ] || { echo "Not found: $TGZ" >&2; exit 1; }
[ -f "$UNIT" ] || { echo "Not found: $UNIT" >&2; exit 1; }
[ -f "$AGENT_UNIT" ] || { echo "Not found: $AGENT_UNIT" >&2; exit 1; }
[ -f "$WEB_UNIT" ] || { echo "Not found: $WEB_UNIT" >&2; exit 1; }
id "$DEPLOYER" >/dev/null 2>&1 || { echo "Unknown user: $DEPLOYER" >&2; exit 1; }

# El agente usa los paquetes del sistema (sin venv). Solo se verifican: instalarlos es decisión del administrador.
# python3-pil, python3-spidev y fonts-dejavu-core son de la pantalla (SPEC 17).
PACKAGES="python3-gpiozero python3-lgpio python3-pil python3-spidev fonts-dejavu-core"
for pkg in $PACKAGES; do
    dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed" ||
        { echo "Missing package $pkg: sudo apt install $PACKAGES" >&2; exit 1; }
done
# SPI apagado no es error: la pantalla puede estar deshabilitada (hardware.display.enabled).
[ -e /dev/spidev0.0 ] ||
    echo "Warning: /dev/spidev0.0 not found; the display needs SPI: sudo raspi-config nonint do_spi 0" >&2

# Usuario de sistema sin login ni home; el que despliega entra al grupo para usar el socket (socat).
getent group openplayer >/dev/null || groupadd --system openplayer
id openplayer >/dev/null 2>&1 ||
    useradd --system --gid openplayer --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin openplayer
usermod -aG openplayer "$DEPLOYER"

# player.json existente se conserva: puede tener ajustes hechos en la Pi.
mkdir -p "$DIR"
tar -xzmf "$TGZ" -C "$DIR" --no-same-owner --exclude=./player.json
[ -f "$DIR/player.json" ] || tar -xzmf "$TGZ" -C "$DIR" --no-same-owner ./player.json
# Un player.json anterior a SPEC 08 no tiene "web": se agrega con el valor del ejemplo y el resto queda igual.
python3 - "$DIR/player.json" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
if "web" not in data:
    data["web"] = {"port": 8080}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("player.json: added web.port 8080")
PY
chown -R root:root "$DIR"
chmod -R u=rwX,go=rX "$DIR"
chmod 755 "$DIR/OpenPlayer.Service"

install -m 644 "$UNIT" /etc/systemd/system/openplayer.service
install -m 644 "$AGENT_UNIT" /etc/systemd/system/openplayer-hardware.service
install -m 644 "$WEB_UNIT" /etc/systemd/system/openplayer-web.service
systemctl daemon-reload
systemctl enable --quiet openplayer openplayer-hardware openplayer-web
# Un "failed" previo por StartLimitBurst bloquearía el restart.
systemctl reset-failed openplayer openplayer-hardware openplayer-web 2>/dev/null || true
systemctl restart openplayer

# Type=simple da "active" apenas arranca el proceso; el socket confirma que el Service llegó a escuchar.
for _ in $(seq 30); do
    systemctl is-active --quiet openplayer && [ -S "$SOCK" ] && break
    sleep 0.5
done
if ! systemctl is-active --quiet openplayer || [ ! -S "$SOCK" ]; then
    echo "openplayer did not become active" >&2
    journalctl -u openplayer -n 20 --no-pager >&2
    exit 1
fi
echo "openplayer: active, listening on $SOCK"

# Los agentes confirman con "ready:" (GPIO configurados / HTTP escuchando); se busca solo en los logs de este arranque.
wait_ready() {
    systemctl restart "$1"
    for _ in $(seq 30); do
        invocation=$(systemctl show -p InvocationID --value "$1")
        if systemctl is-active --quiet "$1" && [ -n "$invocation" ] &&
            journalctl _SYSTEMD_INVOCATION_ID="$invocation" --no-pager -q | grep -q "ready:"; then
            echo "$1: active"
            return 0
        fi
        sleep 0.5
    done
    echo "$1 did not become active" >&2
    journalctl -u "$1" -n 20 --no-pager >&2
    exit 1
}
wait_ready openplayer-hardware
wait_ready openplayer-web
