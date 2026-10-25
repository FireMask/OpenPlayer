# SPEC 20 — Gestos de botones, apagado seguro y avisos en pantalla

**Estado:** Approved
**Depende de:** SPEC 04 (systemd), SPEC 05 (botones GPIO), SPEC 17 y 18 (pantalla y modos)
**Fecha:** 2026-10-24

**Objetivo:** Agregar pulsaciones largas a los botones físicos (seek ±10 s, repetición de volumen, apagado seguro de la Pi manteniendo ▶︎ 3 s) con avisos breves en la pantalla redonda.

## Alcance

### Entra
- **Agente, gestos:**
  - Una pulsación se considera mantenida a partir de `hardware.holdSeconds` (0,6 s por defecto).
  - **⏭ / ⏮:**
    - corta (al soltar): `next` / `previous`;
    - mantenida: `seek_forward` / `seek_backward`, repetido cada 0,5 s mientras siga apretado.
  - **vol+ / vol−:**
    - corta (al apretar, como hoy): `volume_up` / `volume_down`;
    - mantenida: el mismo comando repetido cada 0,25 s.
  - **▶︎⏸:**
    - corta (al soltar): `play_pause`;
    - mantenida `hardware.shutdownHoldSeconds` (3 s por defecto): `power_off`.
    - Si se suelta antes, se cancela y no hace nada (tampoco play/pause).
  - **menu:**
    - corta (al soltar): `menu` (cicla los modos de pantalla, como hoy);
    - mantenida: no envía nada y muestra el aviso "Menú: próximamente" (reservado para SPEC 21).
  - Una pulsación larga nunca dispara la acción corta.
- **Service:**
  - Tres botones nuevos en `ButtonName`: `seek_forward`, `seek_backward` y `power_off`.
  - Seek relativo de `SeekStepSeconds` (10 por defecto, en `PlayerSettings`).
    - Hacia atrás no baja de 0.
    - Hacia adelante llega como mucho a la duración menos 1 s.
    - Sin posición o detenido no hace nada.
  - `power_off`:
    - registra `Power off requested (button)` y ejecuta `systemctl poweroff`;
    - si falla, lo registra y sigue funcionando.
- **Sistema:**
  - Una regla polkit (`deploy/50-openplayer-poweroff.rules`) permite al usuario `openplayer` `org.freedesktop.login1.power-off` y `…power-off-multiple-sessions`.
  - `install.sh` la instala en `/etc/polkit-1/rules.d/`.
- **Pantalla, avisos:**
  - Una píldora oscura abajo, encima de cualquier modo, durante 1,5 s: `+10 s`, `−10 s` y "Menú: próximamente".
  - Mientras ▶︎ está mantenido, la cuenta "Apagar 3… 2… 1"; al llegar, "Apagando…" y `DISPOFF`.
  - Sin pantalla habilitada, el apagado funciona igual, sin aviso.
- **Config:** `hardware.holdSeconds` (0,2–2) y `hardware.shutdownHoldSeconds` (1–10), opcionales y validados.
- **Docs:**
  - README (tabla de gestos);
  - `architecture.md` §7 y §8 (botones nuevos);
  - `gpio-map.md` (gestos por botón);
  - `assembly.md` (probar el apagado y la regla polkit).

### No entra
- El menú en pantalla (SPEC 21); la pulsación larga de `menu` solo muestra un aviso.
- Botones nuevos en la web, para el seek o el apagado.
- Avisos en las pulsaciones cortas, o avisos que lleguen desde el Service.
- Doble pulsación u otros gestos (combinaciones de botones).
- Reinicio, suspensión o un botón de encendido (la Pi Zero no tiene botón de encendido nativo).
- Nivel de batería, o apagado automático por batería baja.

## Modelo de datos

### IPC: botones nuevos en `button.pressed` (agente → Service)
```json
{"type":"button.pressed","button":"seek_forward","sequence":12}
{"type":"button.pressed","button":"seek_backward","sequence":13}
{"type":"button.pressed","button":"power_off","sequence":14}
```
- `ButtonName` gana `SeekForward`, `SeekBackward` y `PowerOff`; `ButtonNames.TryParse` acepta los tres nombres nuevos.
- No hay respuesta, igual que el resto de `button.pressed`.

### Service (C#)
- `PlayerSettings.SeekStepSeconds` (int, 10 por defecto, rango 1–60), en la sección `player` de `player.json`, junto a `VolumeStep`.
- `ButtonCommandHandler`:
  - `SeekForward` / `SeekBackward` leen el snapshot y llaman `SeekAsync(clamp(pos ± step, 0, duración − 1))`.
  - Sin posición, o detenido, no hacen nada.
- `IPowerControl.PowerOffAsync(ct)` es una interfaz nueva.
  - Su implementación `SystemdPowerControl` ejecuta `systemctl poweroff` (un `Process`, con timeout de 5 s).
  - Si el proceso falla, lanza una excepción que `IpcServer` registra como `Power off failed: …`.
  - Las pruebas usan un `FakePowerControl`.

### Sistema
`deploy/50-openplayer-poweroff.rules` (JavaScript de polkit):
```js
polkit.addRule(function (action, subject) {
  if (subject.user === "openplayer" &&
      (action.id === "org.freedesktop.login1.power-off" ||
       action.id === "org.freedesktop.login1.power-off-multiple-sessions")) {
    return polkit.Result.YES;
  }
});
```
`install.sh` la copia a `/etc/polkit-1/rules.d/` (modo 644, root).

### Agente (Python)
- `hardware` en `player.json`, campos opcionales nuevos:
  - `holdSeconds` (0,6 por defecto, rango 0,2–2);
  - `shutdownHoldSeconds` (3 por defecto, rango 1–10).

  `AgentConfig` gana `hold_seconds` y `shutdown_hold_seconds`.
- `gestures.py` es una máquina de estados pura, sin GPIO ni hilos, probada con tiempo falso:
  - `Gestures(send, toast, *, hold, shutdown_hold, seek_repeat=0.5, volume_repeat=0.25)`;
  - `press(name, t)`, `release(name, t)` y `tick(t)` llaman `send(nombre_ipc)` y `toast(texto | None)`;
  - un estado por botón: el momento en que se apretó, si ya pasó a mantenida, y cuándo toca la siguiente repetición.
- `buttons.py`:
  - `when_pressed` y `when_released` de gpiozero llaman `gestures.press` / `release` con `time.monotonic()`;
  - un hilo llama `gestures.tick()` cada 50 ms.
- `Display`:
  - `toast(text, seconds=1.5)` muestra el aviso; con `None` lo quita.
  - `shutting_down()` muestra "Apagando…" fijo.
  - Al detener el agente, `main.py` llama `panel.sleep_display()` (`DISPOFF`) antes de cerrar el panel.
- `View` gana `toast: str | None`. `render` dibuja una píldora (fondo `(40, 40, 40)`, texto blanco a 16 px) centrada en y≈180, encima de todo, incluido el indicador de volumen. (Se subió de y≈200 al implementar: a 16 px, "Menú: próximamente" mide 172 px y en y≈200 la cuerda del círculo deja ~152 px.)

## Plan de implementación

1. **Service: seek relativo.**
   - `ButtonName.SeekForward` / `SeekBackward`.
   - `PlayerSettings.SeekStepSeconds`, leído de `player.json` y validado.
   - `ButtonCommandHandler`, con el recorte a 0 y a duración − 1.
   - Pruebas: los extremos, sin posición, detenido y el paso configurado.
2. **Service: apagado.**
   - `ButtonName.PowerOff`, `IPowerControl` y `SystemdPowerControl`.
   - El log `Power off requested (button)`; si falla, `Power off failed: …` y el Service sigue.
   - Pruebas con `FakePowerControl`.
   - Se actualizan `architecture.md` §7 y §8.
3. **Sistema: polkit.**
   - `deploy/50-openplayer-poweroff.rules`.
   - `install.sh` la instala y avisa si falta `polkitd`.
4. **Agente, config:**
   - `holdSeconds` y `shutdownHoldSeconds` en `AgentConfig`, con validación y pruebas.
   - Se actualiza `player.example.json`.
5. **Agente, `gestures.py`:** la máquina de estados y sus pruebas con tiempo falso:
   - acción corta al soltar;
   - mantenida con repetición de seek y de volumen;
   - el volumen se envía al apretar;
   - la cuenta y el envío de `power_off`, y cancelar soltando antes;
   - la pulsación larga de `menu` solo da aviso;
   - una pulsación larga nunca dispara la corta.
6. **Agente, botones y avisos:**
   - `buttons.py` cableado a `Gestures`, con el hilo de 50 ms.
   - `View.toast` y la píldora en `screen.py`.
   - `Display.toast()` / `shutting_down()`.
   - `DISPOFF` al detener el agente.
   - `main.py` une los gestos con el sender y la pantalla.
   - Pruebas de render y de `Display`, y la de los botones con `MockFactory`.
7. **Docs y verificación en la Pi:**
   - README, `gpio-map.md` y `assembly.md`.
   - Desplegar y probar cada gesto en los botones reales.
   - Calibrar `holdSeconds`.
   - Activar el journal persistente (`sudo mkdir -p /var/log/journal`), apagar con ▶︎ 3 s y confirmar en el siguiente arranque que el apagado fue limpio: `journalctl -b -1 | tail` muestra `Reached target poweroff`.

## Criterios de aceptación

### Service
- [ ] `seek_forward` / `seek_backward` mueven la posición ±`SeekStepSeconds` (10 por defecto); no bajan de 0 ni pasan de duración − 1, y no cambian de pista.
- [ ] Sin posición conocida, o detenido, `seek_*` no llama a MPD y no falla.
- [ ] `power_off` registra `Power off requested (button)` y llama a `IPowerControl`; si falla, registra `Power off failed: …` y el Service sigue respondiendo.
- [ ] `SeekStepSeconds` fuera de 1–60 se rechaza al arrancar con un error claro, como `VolumeStep`.
- [ ] Las pruebas .NET y las de la web pasan.

### Agente
- [ ] Una pulsación corta de ⏭ ⏮ ▶︎ menu se envía una sola vez, al soltar; vol± se envía al apretar, como hoy.
- [ ] ⏭/⏮ mantenido ≥ `holdSeconds` envía `seek_forward`/`seek_backward` enseguida y luego cada 0,5 s mientras siga apretado, con el aviso `+10 s`/`−10 s`; al soltar no envía `next`/`previous`.
- [ ] vol± mantenido repite el comando cada 0,25 s mientras siga apretado.
- [ ] ▶︎ mantenido muestra "Apagar 3… 2… 1". Soltar antes de `shutdownHoldSeconds` no envía nada (ni `play_pause`). Al llegar envía `power_off` una sola vez y muestra "Apagando…".
- [ ] menu mantenido muestra "Menú: próximamente" y no envía nada.
- [ ] Sin pantalla habilitada, los gestos y el apagado funcionan igual.
- [ ] Al detenerse el agente, el panel recibe `DISPOFF` antes de cerrarse.
- [ ] `holdSeconds` fuera de 0,2–2 y `shutdownHoldSeconds` fuera de 1–10 se rechazan; si faltan, se usan los valores por defecto.
- [ ] Todas las pruebas del hardware-agent pasan, también con las advertencias de obsolescencia tratadas como errores.

### En la Pi
- [ ] `install.sh` instala la regla polkit, y `sudo -u openplayer busctl call org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager CanPowerOff` responde `s "yes"`. (Cambiado al implementar: `systemctl poweroff --dry-run` termina antes de consultar a logind y polkit, así que no prueba la regla.)
- [ ] Mantener ▶︎ 3 s apaga la Pi. En el arranque siguiente, `journalctl -b -1` termina con `Reached target poweroff` / `System Power Off`, sin cortes (requiere journal persistente: `sudo mkdir -p /var/log/journal`, ver `assembly.md` §8).
- [ ] Mantener ⏭ durante una canción avanza de 10 en 10 s y nunca salta a la siguiente pista.
- [ ] Con los botones reales no hay falsas pulsaciones largas, con `holdSeconds` calibrado y el valor anotado en `gpio-map.md`.

### General
- [ ] README (tabla de gestos), `architecture.md` §7/§8, `gpio-map.md` y `assembly.md` describen los gestos, el apagado y la regla polkit.

## Decisiones tomadas y descartadas

| Decisión | Alternativa descartada | Por qué |
|---|---|---|
| Los gestos se detectan en el agente, que envía nombres de botón nuevos (`seek_forward`, `seek_backward`, `power_off`) | Un mensaje nuevo `player.seek_relative`, o enviar los eventos crudos (apretar/soltar) al Service | Reusa `button.pressed` y su manejo; el tiempo de pulsación es cosa del hardware; la web puede reusar los mismos nombres. |
| La acción corta se dispara al soltar en ⏭⏮▶︎menu, y al apretar en vol± | Disparar siempre al apretar | Solo al soltar se distingue la corta de la larga sin dispararlas a las dos; en vol± la larga repite la misma acción y no hace falta esperar. |
| Una pulsación larga nunca dispara la corta | Disparar las dos | Evita que apagar haga play/pause o que un seek salte de pista. |
| `holdSeconds` y `shutdownHoldSeconds` se configuran en `player.json` | Fijos en el código | Hay que calibrar con los botones reales (rebote, dureza). |
| `SeekStepSeconds` en `PlayerSettings` | En el agente | La posición y la duración viven en el Service; va junto a `VolumeStep`. |
| El seek adelante llega como mucho a duración − 1 s | Dejar que pase de pista | Un seek largo no debe cambiar de canción; para eso está la pulsación corta de ⏭. |
| Apaga el Service con `systemctl poweroff` y una regla polkit | `sudo` en el agente, o un setuid | Las unidades corren con `NoNewPrivileges` (sudo no funciona); polkit vía logind sí funciona y da solo el permiso de apagar. |
| Un único lugar ejecuta el apagado (el Service) | Que el agente apague | La web podrá ofrecer apagar más adelante sin duplicar permisos. |
| Mantener 3 s con cuenta regresiva; soltar antes cancela | Confirmar con un segundo botón, o doble pulsación | Una sola mano y sin mirar mucho; la cuenta evita apagados por accidente. |
| Los avisos son locales del agente y solo para los gestos | Avisos en cada pulsación, o enviados por el Service | Las pulsaciones cortas ya se ven en el modo pista; los avisos del Service quedan para SPEC 21 si hacen falta. |
| `DISPOFF` al detener el agente | Dejar la última imagen | Al apagar la Pi, el panel queda alimentado y mostraría "Apagando…" para siempre. |
| La pulsación larga de `menu` solo da un aviso por ahora | Dejarla sin efecto | Reserva el gesto para SPEC 21 y deja claro que es intencional. |

## Riesgos identificados

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Tras `poweroff`, la Pi Zero mantiene los 3,3 V mientras haya alimentación: el panel sin pin BL queda con la luz encendida | Gasta batería con la Pi apagada | `DISPOFF` deja el panel negro, pero la luz sigue. Queda documentado en `assembly.md` y `battery-design.md`: hace falta el interruptor de alimentación (o un MOSFET en VCC del panel más adelante). |
| El rebote de los botones reales genera falsos soltar/apretar durante una pulsación larga | Una pulsación larga se corta y dispara la corta | El debounce de gpiozero ya está; `holdSeconds` es configurable; hay un criterio de calibración en la Pi. |
| Disparar al soltar agrega latencia percibida en ⏭⏮▶︎menu | Se siente más lento | Es la duración real de la pulsación (~0,1 s); vol± sigue inmediato. Se evalúa en la Pi. |
| La regla polkit no se carga (polkitd ausente, otra ruta, versión vieja de JS) | `power_off` falla | `install.sh` avisa si falta `polkitd`; el criterio en la Pi prueba `CanPowerOff` (busctl) como `openplayer`; el Service registra `Power off failed` y sigue. |
| Un `power_off` por accidente (algo apoyado sobre el botón) | La Pi se apaga sola | Hacen falta 3 s seguidos, con cuenta regresiva visible; soltar cancela. |
| La repetición de seek o de volumen sigue si el GPIO no informa el soltar (cable flojo) | Seek o volumen sin control | La repetición se basa en `is_pressed` en cada tick, no solo en el evento de soltar; el volumen ya queda recortado a 0–100. |
| Varias pulsaciones a la vez (dos botones mantenidos) | Estados cruzados | Un estado independiente por botón en `Gestures`; hay pruebas con dos botones a la vez. |
