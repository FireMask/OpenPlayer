# SPEC 06 — Configuración MPD del DAC USB por nombre de tarjeta

> **Status:** Approved
> **Depends on:** SPEC 02
> **Date:** 2026-10-20
> **Objective:** Documentar cómo configurar el `audio_output` de MPD con el id ALSA de la tarjeta (`hw:CARD=<id>,DEV=0`) en lugar del índice, y validar en la Pi que MPD reproduce por el DAC USB tras un reinicio.

## Scope

**In:**

- `docs/assembly.md` §5: cómo obtener el id ALSA del DAC (`aplay -l`, `cat /proc/asound/cards`: el id es la palabra entre corchetes, p. ej. `[Device ]` → `Device`) y el bloque `audio_output` de referencia:
  `type "alsa"`, `name "USB DAC"`, `device "hw:CARD=<id>,DEV=0"`, `mixer_type "software"`.
- `docs/assembly.md`, solución de problemas: el síntoma `Failed to open ALSA device "hw:N,0"` / `Not playing` en `next` → el índice cambió; usar el id.
- `docs/architecture.md` (MPD y salida de audio): referenciar el formato `hw:CARD=<id>,DEV=0`.
- Validación en la Pi (`mpi3-player`): `/etc/mpd.conf` con el id (ya aplicado a mano), reproducción tras `sudo reboot`, y borrar `/etc/mpd.conf.bak` al terminar.

**Out of scope (for future specs):**

- Script o paso de `install.sh` que edite `/etc/mpd.conf`.
- Regla udev con id fijo por VID:PID (`0d8c:0014`); revisar si se agrega un segundo dispositivo de audio o Bluetooth.
- Mixer por hardware del DAC.
- Script de diagnóstico de audio.
- Campo `player.preferredOutput` de `player.json` (sin uso).
- Comportamiento con el DAC desconectado al arrancar.
- Verificación MVP "el Service se recupera de un reinicio de MPD".

## Data model

No aplica: solo documentación y configuración del sistema (`/etc/mpd.conf`) en la Pi.

## Implementation plan

1. `docs/assembly.md` §5: pasos para obtener el id ALSA del DAC y bloque `audio_output` de referencia con `hw:CARD=<id>,DEV=0`; §4 aclara que el id (no el índice) es lo que va a MPD.
2. `docs/assembly.md` solución de problemas y `docs/architecture.md` (MPD y salida de audio): síntoma de índice cambiado, nota sobre conservar `/etc/mpd.conf` al actualizar `mpd`, y referencia al formato por id.
3. Validación en la Pi: confirmar que `/etc/mpd.conf` usa `hw:CARD=Device,DEV=0` según los pasos documentados, `sudo reboot`, `mpc play` → `[playing]` sin error ALSA en `journalctl -u mpd -b`; dejar MPD detenido y borrar `/etc/mpd.conf.bak`.

## Acceptance criteria

**Documentación:**

- [ ] `assembly.md` §5 muestra cómo leer el id de la tarjeta en `aplay -l` o `/proc/asound/cards` y el bloque `audio_output` con `device "hw:CARD=<id>,DEV=0"` y `mixer_type "software"`.
- [ ] `assembly.md` no contiene `hw:<número>` como valor recomendado (verificable con `grep -nE 'hw:[0-9]' docs/`; solo puede aparecer citando el mensaje de error).
- [ ] La sección de solución de problemas de `assembly.md` cubre `Failed to open ALSA device "hw:N,0"`.
- [ ] `architecture.md` (MPD y salida de audio) menciona el formato `hw:CARD=<id>,DEV=0`.

**Raspberry Pi:**

- [ ] `grep device /etc/mpd.conf` (líneas sin comentar) muestra `hw:CARD=Device,DEV=0` y ningún índice numérico.
- [ ] Tras `sudo reboot`: `mpc play` muestra `[playing]` y `journalctl -u mpd -b` no tiene `Failed to open`.
- [ ] Tras la prueba, MPD queda detenido y `/etc/mpd.conf.bak` no existe.
- [ ] `dotnet test` y `pytest tests/hardware-agent` siguen pasando (sin cambios de código).

## Decisions

**Tomadas:**

- **Solo documentación, sin script.** Configurar MPD es un paso único por Pi, como instalar MPD; automatizarlo en `install.sh` acoplaría el deploy de la app a la config de audio del SO.
- **Id ALSA (`hw:CARD=Device,DEV=0`) en lugar de índice.** El índice depende del orden de detección (hoy el DAC pasó de card 1 a card 0 y MPD intentó abrir HDMI); el id es estable entre reinicios.
- **`hw:` y no `plughw:`.** MPD ya convierte formato y frecuencia; `plughw` agrega otra conversión sin necesidad.
- **Mixer `software` se conserva.** Funciona hoy y el snapshot reporta el volumen; cambiarlo es otra spec.
- **Verificación manual.** Un reinicio + `mpc play` cubre el caso real; un script de diagnóstico no se justifica aún.

**Descartadas:**

- **Regla udev con id propio por VID:PID.** Más robusta ante dos adaptadores C-Media iguales, pero hoy hay un solo DAC; revisar con Bluetooth o una segunda salida.
- **Editar `/etc/mpd.conf` desde `install.sh`.** Ver arriba.

## Risks

- **Id genérico `Device`.** Otro adaptador USB C-Media (o similar) usaría el mismo id y ALSA le asignaría `Device_1`, o tomaría el nombre primero según el orden de detección. Mitigación: un solo DAC conectado; si se agrega otro, regla udev (fuera de alcance).
- **Actualizar el paquete `mpd`.** `apt` puede proponer reemplazar `/etc/mpd.conf`; aceptar la versión del paquete borraría el `audio_output`. Mitigación: la documentación indica conservar la versión local (opción por defecto `N`) y revisar el bloque tras una actualización.
- **DAC desconectado al arrancar.** MPD falla al abrir la salida; el Service ya registra el error. Comportamiento sin cambios (fuera de alcance).
