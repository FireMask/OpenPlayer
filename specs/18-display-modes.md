# SPEC 18 — Modos de pantalla, anillo de volumen y ahorro nocturno

**Estado:** Approved
**Depende de:** SPEC 05 (botones GPIO), SPEC 16 (player.subscribe), SPEC 17 (pantalla GC9A01)
**Fecha:** 2026-10-24

**Objetivo:** Dar a la pantalla redonda dos modos (pista y reloj), elegidos por el Service y alternados con el botón `menu`, con un anillo de volumen temporal, más datos de la pista, título con desplazamiento y apagado nocturno o por inactividad.

## Alcance

### Entra
- **Service (C#):**
  - `player.snapshot` gana tres campos: `trackAlbum`, `queueLength` y `displayMode` (`"track"` | `"clock"`).
  - El botón `menu` alterna `displayMode` (track ↔ clock) y empuja un snapshot nuevo a los suscriptores.
  - El modo vive en memoria: al reiniciar el Service vuelve a `"track"`.
- **Modo pista:**
  - icono de estado;
  - título (22 px);
  - artista (16 px, gris);
  - álbum (14 px, gris);
  - tiempo `1:23 / -2:40`;
  - posición en la cola `3 / 12`;
  - anillo exterior de progreso, como en SPEC 17.

  El texto fijo "Vol N" se elimina.
- **Modo reloj:**
  - HH:MM de 24 h a 48 px, en la zona horaria local de la Pi;
  - debajo, la fecha en español (`vie 24 oct`);
  - el anillo de progreso sigue visible si hay pista en reproducción o en pausa;
  - se redibuja al cambiar el minuto.
- **Reloj automático:** con la reproducción detenida o en pausa durante `idleClockSeconds` (60 por defecto), el agente muestra el reloj. Vuelve al modo del Service al reanudar la reproducción. Es una superposición local: no cambia `displayMode`.
- **Indicador de volumen:** cada cambio de volumen (botones o web) muestra durante 2 s un anillo interior azul y el número grande en el centro, encima de cualquier modo.
- **Título con desplazamiento:** solo el título y solo en reproducción, a unos 10 fps, con una pausa de 1 s en cada extremo. Los títulos que caben no se mueven.
- **Ahorro de pantalla (`DISPOFF`/`DISPON`), ambos opcionales y apagados por defecto:**
  - **Nocturno:** entre `nightStart` y `nightEnd` (`"HH:MM"`, el rango puede cruzar la medianoche).
  - **Por inactividad:** tras `offAfterStoppedMinutes` minutos detenida.
  - Cualquier botón la despierta 10 s y además hace su acción normal. Si empieza la reproducción, la pantalla también despierta.
- **Config:** los campos opcionales `idleClockSeconds`, `nightStart`, `nightEnd` y `offAfterStoppedMinutes` en `hardware.display`, con validación.
- **Docs:** README, `architecture.md` (§7, campos nuevos del snapshot), `assembly.md` §11 y `player.example.json`.

### No entra
- El modo carátula del álbum (SPEC 19: petición de imagen al Service, transferencia, redimensionado y caché).
- Un selector de modo en la web o un comando IPC para fijar el modo.
- Guardar el modo entre reinicios.
- Desplazamiento del artista o del álbum.
- Atenuación real del brillo (el módulo no tiene pin BL).
- La IP o el estado del Wi-Fi, y la batería.
- Tragar la pulsación que despierta la pantalla.
- Reloj de 12 h y otros idiomas para la fecha.

## Modelo de datos

### `player.snapshot` (Service → suscriptores), tres campos nuevos
```json
{"type":"player.snapshot","state":"playing","trackTitle":"Song","trackArtist":"Artist",
 "trackAlbum":"Album","positionSeconds":83,"durationSeconds":243,"volume":35,
 "queuePosition":2,"queueLength":12,"queueVersion":7,"displayMode":"track"}
```
- `trackAlbum`: `string | null`, tomado de la etiqueta `Album` de `currentsong`. El modelo `Track.Album` ya existe.
- `queueLength`: `int | null`, tomado de `playlistlength` del `status` de MPD. Es un campo nuevo de `PlaybackSnapshot`: `int? QueueLength = null`.
- `displayMode`: `"track" | "clock"`. No viene de MPD: lo guarda en memoria `IpcServer` (`_displayMode`, que arranca en `"track"`), y `SnapshotMessage.Serialize(snapshot, displayMode)` lo agrega al mensaje.
- Los clientes que no conocen los campos nuevos los ignoran; la web no cambia.

### `menu` en el Service
`IpcServer` atiende `menu` antes de `ButtonCommandHandler`, como ya hace con `previous`:
1. Bajo el lock, alterna `_displayMode`.
2. Toma el snapshot.
3. Empuja la línea a todos los suscriptores.

Hace falta porque MPD no cambia y el observador no despertaría.

### `hardware.display` en `player.json`, campos nuevos opcionales
```json
"display": {
  "enabled": true, "spiBus": 0, "spiDevice": 0, "dc": 5, "rst": 6,
  "spiHz": 40000000, "rotation": 180,
  "idleClockSeconds": 60,
  "nightStart": null, "nightEnd": null,
  "offAfterStoppedMinutes": null
}
```
| Campo | Tipo | Defecto | Validación |
|---|---|---|---|
| `idleClockSeconds` | int \| null | 60 | 1–3600; `null` desactiva el reloj automático |
| `nightStart`, `nightEnd` | `"HH:MM"` \| null | null | los dos o ninguno, y distintos entre sí |
| `offAfterStoppedMinutes` | int \| null | null | 1–1440 |

`DisplayConfig` gana `idle_clock_seconds: int | None`, `night: tuple[datetime.time, datetime.time] | None` y `off_after_stopped_minutes: int | None`.

### `View` en `screen.py`, ampliada
```python
@dataclass(frozen=True)
class View:
    status: str                        # igual que SPEC 17
    title: str | None = None
    artist: str | None = None
    album: str | None = None           # nuevo
    position: int | None = None
    duration: int | None = None
    volume: int | None = None
    queue_position: int | None = None  # nuevo, 0-based (se muestra +1)
    queue_length: int | None = None    # nuevo
    mode: str = "track"                # nuevo: "track" | "clock" (ya con el reloj automático aplicado)
    clock: str | None = None           # nuevo: "HH:MM", solo en modo reloj
    date: str | None = None            # nuevo: "vie 24 oct", solo en modo reloj
    volume_popup: bool = False         # nuevo: anillo interior y número grande
    scroll: int = 0                    # nuevo: desplazamiento del título en px
```
`render(view)` sigue siendo una función pura. La hora, la fecha y el desplazamiento llegan dentro de la `View`, así las pruebas no dependen del reloj.

### Estado local de `Display` (solo en memoria)
- `_idle_since`: el momento en que la reproducción quedó detenida o en pausa.
- `_volume_until`: hasta cuándo se ve el indicador de volumen.
- `_wake_until`: hasta cuándo sigue despierta tras un botón.
- `_panel_on`: si la pantalla está encendida o en `DISPOFF`.
- La fase del desplazamiento.
- Método nuevo `Display.wake()`: lo llama el callback de cada botón, en `main.py`.

### `GC9A01`, métodos nuevos
`sleep_display()` envía `DISPOFF` (0x28) y `wake_display()` envía `DISPON` (0x29).

## Plan de implementación

1. **Service: álbum y largo de la cola en el snapshot.**
   - `PlaybackSnapshot.QueueLength`, leído de `playlistlength` en `MpdSnapshotParser`.
   - `SnapshotMessage` agrega `trackAlbum` y `queueLength`.
   - Pruebas del parser y del mensaje.
   - Al terminar: la web y el agente siguen funcionando, porque ignoran los campos nuevos.
2. **Service: `displayMode` y `menu`.**
   - `_displayMode` en `IpcServer` y `SnapshotMessage.Serialize(snapshot, displayMode)`.
   - `menu` alterna el modo y empuja el snapshot a los suscriptores.
   - `ButtonCommandHandler` deja de recibir `menu`.
   - Pruebas: el modo arranca en `"track"`, alterna y se empuja a los suscriptores.
   - Se actualiza `architecture.md` §7.
3. **Agente, config:**
   - `idleClockSeconds`, `nightStart`/`nightEnd` y `offAfterStoppedMinutes` en `DisplayConfig`, con validación y pruebas.
   - Se actualiza `player.example.json`.
4. **`screen.py`, modo pista nuevo:**
   - `View` ampliada.
   - Diseño con álbum, tiempo `m:ss / -m:ss` y `n / total`, sin "Vol N".
   - Pruebas de render: con y sin álbum, sin duración y sin cola.
5. **`screen.py`, reloj, indicador de volumen y desplazamiento:**
   - El modo reloj, con el anillo de progreso si hay pista.
   - `volume_popup`, con el anillo interior azul y el número grande.
   - `scroll`, que desplaza el título recortado al círculo.
   - Pruebas de render.
6. **`display.py`, modos y temporizadores:**
   - `parse` lee los campos nuevos.
   - Reloj automático tras `idleClockSeconds`.
   - Indicador de volumen durante 2 s cuando el volumen cambia (no en el primer snapshot).
   - Redibujado al cambiar el minuto en modo reloj.
   - Pruebas con `FakeService`, un reloj inyectable (`now`) y ticks cortos.
7. **`display.py`, desplazamiento del título:**
   - Tick de unos 0,1 s solo mientras el título no cabe y se reproduce; si no, 1 s.
   - Pausa de 1 s en cada extremo.
   - Pruebas: el título corto no se redibuja y el largo avanza y vuelve.
8. **Ahorro de pantalla:**
   - `GC9A01.sleep_display()` y `wake_display()`.
   - En `Display`: horario nocturno, apagado tras `offAfterStoppedMinutes` detenida y `wake()` durante 10 s.
   - Al empezar la reproducción la pantalla también despierta.
   - En `main.py`, el callback de los botones también llama a `display.wake()`.
   - Pruebas: los comandos 0x28/0x29, un horario que cruza la medianoche y el despertar por botón y por reproducción.
9. **Docs y verificación en la Pi:**
   - README, `assembly.md` §11 y `gpio-map.md` si aplica.
   - Medir el uso de CPU del desplazamiento en la Pi Zero 2 W.
   - Recorrer los criterios en el hardware real.

## Criterios de aceptación

### Service
- [ ] `player.snapshot` incluye `trackAlbum` (`null` si no hay etiqueta), `queueLength` (`null` sin cola) y `displayMode`.
- [ ] `displayMode` vale `"track"` al arrancar el Service.
- [ ] Cada `button.pressed` `menu` alterna `displayMode` entre `track` y `clock` y empuja un snapshot a todos los suscriptores, sin que cambie nada en MPD.
- [ ] `menu` no llega a `ButtonCommandHandler` ni toca MPD.
- [ ] La web sigue funcionando sin cambios: las pruebas .NET y las de la web pasan.

### Config
- [ ] Una config sin los campos nuevos carga con `idleClockSeconds=60`, sin modo nocturno y sin apagado por inactividad.
- [ ] Se rechaza con un error claro:
  - `idleClockSeconds` fuera de 1–3600;
  - `offAfterStoppedMinutes` fuera de 1–1440;
  - `nightStart` sin `nightEnd`, o al revés;
  - una hora que no sea `HH:MM` válido;
  - `nightStart == nightEnd`.

### Modo pista
- [ ] Muestra el icono, el título, el artista, el álbum, `m:ss / -m:ss` y `n / total` (con `n` 1-based).
- [ ] Sin álbum, duración o cola, esa línea no se dibuja y nada falla.
- [ ] Ya no aparece el texto "Vol N".

### Modo reloj
- [ ] Muestra HH:MM de 24 h y la fecha en español (`vie 24 oct`), con la hora local de la Pi.
- [ ] El anillo de progreso sigue visible en reproducción o en pausa con duración; detenida, no hay anillo.
- [ ] La pantalla se redibuja al cambiar el minuto y no en cada tick.
- [ ] Con `menu` en la Pi, la pantalla cambia de modo en menos de 1 s.

### Reloj automático
- [ ] Detenida o en pausa durante `idleClockSeconds`, el agente muestra el reloj aunque `displayMode` sea `track`.
- [ ] Al reanudar la reproducción vuelve al modo pista.
- [ ] Con `idleClockSeconds: null` nunca pasa.

### Indicador de volumen
- [ ] Un cambio de volumen (botón o web) muestra el anillo interior azul y el número grande durante 2 s, sobre cualquier modo, y luego desaparece.
- [ ] El primer snapshot tras conectar no lo muestra.

### Desplazamiento del título
- [ ] Un título que no cabe se desplaza mientras se reproduce, con una pausa de 1 s en cada extremo.
- [ ] Un título que cabe, o la reproducción en pausa o detenida, no genera redibujados extra.
- [ ] En la Pi Zero 2 W, el proceso del agente usa menos del 25 % de un núcleo mientras desplaza (medido con `top`).

### Ahorro de pantalla
- [ ] Con `nightStart`/`nightEnd` (incluido un rango que cruza la medianoche), la pantalla recibe `DISPOFF` dentro del horario y `DISPON` al salir de él.
- [ ] Con `offAfterStoppedMinutes`, detenida durante ese tiempo recibe `DISPOFF`.
- [ ] Apagada, cualquier botón la enciende durante 10 s y además hace su acción normal.
- [ ] Apagada por inactividad, empezar la reproducción la enciende.
- [ ] Apagada por el horario nocturno, empezar la reproducción la enciende 10 s.
- [ ] Sin los campos de ahorro, la pantalla nunca se apaga.

### General
- [ ] Todas las pruebas del hardware-agent pasan, también con las advertencias de obsolescencia tratadas como errores.
- [ ] La documentación (README, `architecture.md` §7, `assembly.md` §11 y `player.example.json`) refleja los campos y el comportamiento nuevos.

## Decisiones tomadas y descartadas

| Decisión | Alternativa descartada | Por qué |
|---|---|---|
| El Service guarda `displayMode` y `menu` lo alterna | Que el agente intercepte `menu` en local | Una sola fuente de verdad: la web podrá mostrar o fijar el modo más adelante sin rediseñar. |
| El modo vive en memoria y vuelve a `"track"` al reiniciar | Guardarlo en un archivo de estado | YAGNI: reiniciar es raro y `track` es un buen modo por defecto. |
| El reloj automático es una superposición local del agente | Que el Service cambie `displayMode` | Es una cuestión de presentación: no debe pisar la elección del usuario ni empujar snapshots por un temporizador. |
| El volumen se ve 2 s tras cada cambio | Un anillo de volumen siempre visible | Menos ruido visual; el anillo de progreso sigue siendo el protagonista. |
| El número del volumen va grande en el centro, junto al anillo | Solo el anillo | El anillo por sí solo no da un valor preciso. |
| Solo se desplaza el título | Desplazar también el artista y el álbum | Limita los redibujados y el uso de CPU en la Pi Zero; el título es lo que más importa. |
| El tick rápido (0,1 s) corre solo mientras se desplaza | Tick rápido fijo | Sin desplazamiento, el agente queda casi inactivo como en SPEC 17. |
| El ahorro usa `DISPOFF`/`DISPON` | Atenuar con una paleta más oscura | Sin pin BL no hay brillo real; `DISPOFF` deja el panel en negro y consume menos. |
| El botón que despierta también hace su acción | Tragarse esa pulsación | Más simple, y en la oscuridad se puede pulsar play sin tener que mirar. |
| La hora, la fecha y el desplazamiento entran en la `View` | Que `render()` lea el reloj | `render` queda pura y las pruebas son deterministas. |
| La fecha en español se arma con una tabla propia de días y meses | `locale` / `strftime("%a")` | La Pi puede no tener el locale `es` instalado. |
| La carátula queda en SPEC 19 | Hacerla en esta spec | Necesita una petición binaria nueva al Service, transferencia, redimensionado y caché: otro dominio y otros riesgos. |
| No hay selector en la web en esta spec | Agregarlo ahora | Fuera de alcance; el modelo ya lo deja preparado. |
| Reloj de 24 h | 12 h o configurable | Lo eligió el usuario. |

## Riesgos identificados

| Riesgo | Impacto | Mitigación |
|---|---|---|
| La Pi no tiene RTC: sin red, la hora es falsa hasta que NTP sincroniza | El reloj y el horario nocturno quedan mal tras arrancar sin Wi-Fi | Se acepta; queda documentado en `assembly.md`. El horario nocturno se recalcula en cada tick, así se corrige solo cuando NTP sincroniza. |
| El desplazamiento a 10 fps (unos 115 KB por SPI y un render por cuadro) carga la Pi Zero | Más CPU y temperatura; puede competir con MPD | Solo con un título largo y en reproducción. Hay un criterio de < 25 % de un núcleo medido en la Pi. Si no se cumple, se baja a 5 fps (`ponytail:` con el límite). |
| Un cambio de volumen por reconexión o por un snapshot repetido dispara el indicador | Aparece sin que nadie tocara el volumen | Solo cuenta un cambio respecto del snapshot anterior de la misma conexión; el primero tras conectar no cuenta. |
| `menu` se pulsa sin suscriptores, o con el Service sin MPD | El modo cambia pero nadie lo ve, o falla el snapshot | El modo cambia igual. Si el snapshot falla se registra y se empuja el error como hoy; el siguiente snapshot lleva el modo correcto. |
| `DISPOFF` deja el panel sin responder en algunos módulos | La pantalla no vuelve a encenderse | Se prueba en la Pi real. Si pasa, `wake_display()` puede rehacer `init()` (`ponytail:` con la alternativa). |
| El texto y los anillos se pisan en modo reloj con el indicador de volumen | Se ven superpuestos | El indicador se dibuja al final y tapa el centro; hay una prueba de render del caso combinado. |
| Las pruebas con tiempo real son lentas o inestables | CI frágil | Un reloj inyectable (`now`) en `Display` y ticks cortos, igual que en las pruebas de SPEC 17. |
