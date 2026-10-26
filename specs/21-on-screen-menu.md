# SPEC 21 — Menú en pantalla con los seis botones

**Estado:** Approved
**Depende de:** SPEC 10–14 (biblioteca, listas y cola por IPC), SPEC 17–19 (pantalla redonda), SPEC 20 (gestos, avisos y `power_off`)
**Fecha:** 2026-10-25

**Objetivo:** Agregar a la pantalla redonda un menú que se abre manteniendo `menu`, se navega con ⏮/⏭/▶︎/menu y permite explorar Biblioteca, Listas y Cola para reproducir o encolar, y apagar con confirmación, todo en el agente sobre la IPC existente.

## Alcance

### Entra
- **Abrir y cerrar:**
  - Afuera del menú:
    - `menu` mantenido abre el menú en la raíz (reemplaza el aviso "Menú: próximamente");
    - `menu` corto sigue ciclando los modos de pantalla.
  - Adentro del menú:
    - `menu` corto vuelve un nivel; en la raíz cierra;
    - `menu` mantenido cierra desde cualquier nivel.
  - Se cierra solo tras 30 s sin botones.
  - Sin pantalla habilitada, `menu` mantenido no hace nada.
- **Navegación:**
  - ⏮/⏭ suben y bajan; mantenidos repiten rápido. No hay vuelta al llegar a los extremos: el cursor se queda en el primero o el último.
  - ▶︎ corto elige.
  - ▶︎ mantenido apaga igual que afuera (cuenta de SPEC 20).
  - vol± siguen cambiando el volumen.
  - Mientras el menú está abierto, ⏮/⏭/▶︎ cortos y mantenidos no llegan al Service como `previous`/`next`/`play_pause`/`seek_*`.
- **Raíz:** Biblioteca · Listas · Cola · Apagar.
- **Biblioteca:**
  - Carpetas y pistas de `library.browse`, con migas implícitas (`menu` vuelve a la carpeta padre).
  - Elegir una carpeta entra en ella.
  - La primera fila de cada carpeta (excepto la raíz) es "▶ Reproducir todo".
  - Elegir una pista o "Reproducir todo" abre las acciones:
    - "Reproducir" (`library.play`, reemplaza la cola);
    - "Siguiente" (`queue.add` con `next`);
    - "Agregar a la cola" (`queue.add`).
- **Listas:**
  - Los nombres de `playlist.list`; elegir una muestra sus pistas (`playlist.get`).
  - La primera fila es "▶ Reproducir lista" (`playlist.play` desde 0).
  - Elegir una pista: "Reproducir desde aquí" (`playlist.play` con su posición).
- **Cola:**
  - La cola de `queue.get`, con la actual marcada.
  - Elegir una pista hace `queue.play` directo.
- **Apagar:** pantalla "¿Apagar?" con No (por defecto) y Sí. Sí envía `power_off` y muestra "Apagando…".
- **Listas largas:** al acercarse el cursor al final de lo cargado, se pide la página siguiente (100 por página). En memoria, solo el nivel actual y los cursores de los niveles anteriores.
- **Respuesta en pantalla:**
  - las acciones que reproducen cierran el menú;
  - "Siguiente" y "Agregar" muestran el aviso "Agregado" y dejan el menú abierto;
  - un error de IPC muestra el aviso "Error" y deja el menú donde estaba;
  - mientras carga un nivel, se ve "Cargando…".
- **Dibujo:**
  - lista vertical de 5 filas, con la seleccionada centrada en una píldora de color de acento;
  - cada fila se corta con "…" a la cuerda del círculo;
  - arriba, un encabezado con el nombre del nivel;
  - el indicador de volumen y los avisos se dibujan encima del menú;
  - la pantalla apagada (noche o detenida) se enciende al abrir el menú, como con cualquier botón.
- **Docs:**
  - README (gestos del menú);
  - `architecture.md` §8 y §13 (fase 8 al día: carátula hecha, menú hecho);
  - `gpio-map.md` (tabla de gestos con el menú);
  - `assembly.md` (probar el menú).

### No entra
- Cambios en el Service o en la IPC (todo usa mensajes existentes).
- Editar la cola o las listas desde el menú (quitar, mover, crear, renombrar o guardar): queda en la web.
- Búsqueda por texto, navegación por artista o álbum, carátulas en las filas.
- Ajustes en el menú (modo de pantalla, horario nocturno, `holdSeconds`, etc.).
- Reiniciar, o "Apagar" sin confirmación.
- Encoder rotativo, botones nuevos o interruptor de bloqueo (otra spec).
- Desplazamiento animado del texto de la fila seleccionada; se corta con "…".
- Configurar el timeout de 30 s.

## Modelo de datos

No hay mensajes IPC nuevos ni cambios en el Service. El agente usa los existentes, cada uno en una conexión corta como `player.get_cover`:

| Uso | Pedido | Respuesta |
|---|---|---|
| Biblioteca | `{"type":"library.browse","path":"Rock","offset":0}` | `library.page` |
| Listas | `{"type":"playlist.list"}` · `{"type":"playlist.get","name":"Viaje","offset":0}` | `playlist.list` · `library.page` |
| Cola | `{"type":"queue.get","offset":0}` | `queue.page` |
| Acciones | `library.play {uri}` · `queue.add {uri, next}` · `playlist.play {name, position}` · `queue.play {position}` | `ok` / `error` |
| Apagar | `button.pressed` `power_off`, por el `Sender` de siempre | — |

### `sender.py`: `request(connect, message, *, max_bytes=1 MiB, timeout=5) -> dict | None`
- Abre una conexión, envía una línea, lee una línea y cierra.
- Si falla (conexión, timeout, JSON inválido o `type: error`), devuelve `None` y lo registra como warning.
- `cover.fetch_cover` pasa a usarla, con `max_bytes` de 3 MB, en lugar de su propio bucle.

### `gestures.py`: nombres locales del menú
- `Gestures(..., menu_open=lambda: False)`: lo consulta en el momento en que dispara cada acción.

| Botón | Menú cerrado | Menú abierto |
|---|---|---|
| ⏭ / ⏮ corto | `next` / `previous` | `menu_down` / `menu_up` |
| ⏭ / ⏮ mantenido | `seek_*` cada 0,5 s + aviso | `menu_down` / `menu_up` cada 0,15 s, sin aviso |
| ▶︎ corto | `play_pause` | `menu_select` |
| ▶︎ mantenido | cuenta y `power_off` | igual |
| menu corto | `menu` | `menu_back` |
| menu mantenido | `menu_open` (reemplaza el aviso "Menú: próximamente") | `menu_close` |
| vol± | sin cambios | sin cambios |

- `main.py` reparte: los `menu_*` van a `Menu` y el resto al `Sender`, como hoy.
- Sin pantalla, `menu_open` se ignora y el menú nunca se abre, así que el resto funciona como en SPEC 20.

### `menu.py`: `Menu`, máquina de estados sin GPIO ni dibujo
```python
Menu(request, *, power_off, toast, changed, queue_position=lambda: None,
     run=<hilo daemon>, monotonic=time.monotonic, timeout=30)
```
- `request(message) -> dict | None`: `sender.request` con el `connect` del agente.
- `power_off()`: `main.py` envía `power_off` y llama `display.shutting_down()`.
- `toast(text)`: los avisos "Agregado" y "Error".
- `changed()`: hace que `Display` redibuje enseguida, como `toast`.
- `queue_position()`: la posición actual de la cola, sacada del último snapshot de `Display`, para marcar la pista que suena.
- `run(f)`: ejecuta los pedidos IPC fuera del hilo de los botones, para que la cuenta de apagado no se trabe. En las pruebas, `run=lambda f: f()`.
- Métodos:
  - `open()`, `close()`, `up()`, `down()`, `select()` y `back()`;
  - `view(t) -> MenuView | None`, que devuelve `None` si está cerrado o si pasaron `timeout` segundos desde el último botón; en ese caso, cierra.
- Estado interno, bajo un lock:
  - una pila de `_Level(title, rows, cursor, total, load)`;
  - `load(offset)` pide la página siguiente cuando el cursor queda a ≤ 10 filas del final de lo cargado y `len(rows) < total`;
  - un nivel con un pedido en curso está `loading`;
  - una respuesta que llega para un nivel que ya no está arriba de la pila se descarta.
- `_Row(label, action)` con `action` interno, por ejemplo:
  - `("browse", path)`, `("track_actions", uri)`, `("play_uri", uri)`, `("add", uri, next)`;
  - `("playlist", name)`, `("play_playlist", name, pos)`, `("queue_play", pos)`;
  - `("confirm_off",)`, `("power_off",)`, `("back",)`.
- Niveles:
  - **Raíz:** "Biblioteca", "Listas", "Cola", "Apagar".
  - **Biblioteca:**
    - en cada carpeta, la etiqueta es el último segmento del `uri`; en una pista, `title` o, si no tiene, el nombre del archivo;
    - fuera de la raíz, la primera fila es "▶ Reproducir todo" (`track_actions` sobre la carpeta);
    - las acciones son "Reproducir", "Siguiente" y "Agregar a la cola".
  - **Listas:**
    - nombres de lista → pistas;
    - la primera fila es "▶ Reproducir lista" (`play_playlist`, 0);
    - una pista abre un nivel con "Reproducir desde aquí".
  - **Cola:** el `title` (o el archivo) de cada entrada; la que coincide con `queue_position()` lleva el prefijo "♪ ".
  - **"¿Apagar?":** las filas "No" (cursor inicial) y "Sí".
- Después de una acción:
  - las que reproducen cierran el menú;
  - "Siguiente" y "Agregar" muestran el aviso "Agregado";
  - con `None`, aviso "Error" y el nivel no cambia.

### `screen.py`
```python
@dataclass(frozen=True)
class MenuView:
    title: str              # "Menú", "Biblioteca", "Rock", "¿Apagar?"…
    rows: tuple[str, ...]   # etiquetas ya cargadas
    cursor: int
    loading: bool = False   # sin filas aún: "Cargando…"
```
- `View` gana `menu: MenuView | None = None`. Con menú, `render` dibuja el menú en lugar del modo, con el anillo de progreso apagado.
- Cinco filas de 30 px, con la seleccionada centrada en y=120:
  - la seleccionada va en una píldora `ACCENT`, texto blanco a 18 px;
  - las demás, texto `GRAY` a 16 px;
  - cada fila con `fit()` a su cuerda.
- El encabezado (`title`), en `GRAY` a 14 px, arriba (y≈30).
- En los extremos, las filas que no existen quedan vacías.
- Encima, como siempre: el indicador de volumen y luego el aviso.

### `display.py`
- `Display(..., menu=None)`.
- `_draw_locked` agrega `menu=self._menu.view(now)` a la `View`.
- El tick de 1 s también vence el timeout.
- `refresh()` (público) redibuja enseguida si el panel está listo. Es el `changed` del menú.
- `wake()` también se llama al abrir el menú (ya pasa: es un botón).

## Plan de implementación

1. **Agente, `request()` compartido.**
   - `sender.request(connect, message, *, max_bytes, timeout)`.
   - `cover.fetch_cover` pasa a usarla, sin cambiar su comportamiento: siguen pasando las pruebas de SPEC 19.
   - Pruebas de `request` con un servidor TCP falso: `ok`, `error`, línea demasiado larga, conexión cerrada y timeout.
2. **Agente, `gestures.py` con `menu_open`.**
   - Los nombres `menu_*` según la tabla, la repetición de 0,15 s mantenida y `menu_open` en lugar del aviso "Menú: próximamente".
   - Pruebas: con el menú cerrado no cambia nada respecto de SPEC 20 (salvo `menu_open`). Con el menú abierto, cada botón produce lo que dice la tabla; ▶︎ mantenido sigue apagando; vol± sin cambios.
3. **Agente, `menu.py`.**
   - La máquina de estados con `request` falso y `run` síncrono.
   - Pruebas:
     - raíz → Biblioteca → carpeta → pista → acciones, y que se envíe el mensaje correcto en cada una;
     - "Reproducir todo" ausente en la raíz de la biblioteca;
     - Listas → pistas → "Reproducir desde aquí" con la posición;
     - "Reproducir lista";
     - Cola con "♪ " y `queue.play`;
     - "¿Apagar?" con No por defecto; Sí llama `power_off`;
     - sin vuelta en los extremos;
     - pedido de la página siguiente al acercarse al final, sin pedirla dos veces;
     - error → aviso "Error" sin cambiar de nivel;
     - una respuesta tardía de un nivel ya cerrado se descarta;
     - `back`, `close` y el timeout de 30 s;
     - "Reproducir" cierra; "Agregar" deja abierto y da el aviso.
4. **Agente, dibujo.**
   - `MenuView`, `View.menu` y el dibujo del menú en `screen.py`.
   - Pruebas de render:
     - la píldora de acento en la fila central;
     - el cursor en el primero y en el último;
     - etiqueta larga cortada dentro del círculo;
     - "Cargando…";
     - volumen y aviso encima del menú;
     - sin menú, todo sigue igual.
5. **Agente, unir todo.**
   - `Display(menu=…)`, `refresh()` y el timeout en el tick.
   - `main.py`:
     - crea `Menu` solo si hay pantalla;
     - pasa `menu_open` a `Gestures`;
     - reparte los `menu_*`;
     - `power_off` del menú usa el mismo camino que el gesto.
   - Pruebas de `Display` con un menú abierto (redibuja con `changed`; cierra por timeout con `monotonic` falso).
   - Prueba de los botones con `MockFactory`: menu mantenido, ⏭ y ▶︎ eligen sin llegar al Service.
6. **Docs y verificación en la Pi.**
   - README, `architecture.md` §8 y §13, `gpio-map.md` y `assembly.md`.
   - Desplegar y recorrer el menú con los botones reales:
     - reproducir una carpeta, agregar una pista, reproducir una lista desde la pista 3 y saltar en la cola;
     - apagar desde el menú;
     - medir que una carpeta de más de 100 entradas se recorra sin cortes.

## Criterios de aceptación

### Gestos
- [ ] Con el menú cerrado, todos los gestos de SPEC 20 siguen iguales, salvo que `menu` mantenido abre el menú en lugar de mostrar el aviso.
- [ ] Con el menú abierto, ⏭/⏮ cortos mueven el cursor una fila y mantenidos repiten cada 0,15 s. Ninguno envía `next`, `previous` ni `seek_*` al Service.
- [ ] Con el menú abierto, ▶︎ corto elige sin enviar `play_pause`; ▶︎ mantenido muestra la cuenta y apaga como en SPEC 20.
- [ ] Con el menú abierto, `menu` corto vuelve un nivel (en la raíz cierra) y mantenido cierra desde cualquier nivel; vol± cambian el volumen.
- [ ] Sin pantalla habilitada, `menu` mantenido no hace nada, y el resto de los gestos funciona como en SPEC 20.

### Menú
- [ ] La raíz muestra Biblioteca, Listas, Cola y Apagar.
- [ ] Biblioteca:
  - navega carpetas;
  - "▶ Reproducir todo" aparece en toda carpeta excepto la raíz;
  - en una pista o en "Reproducir todo", "Reproducir" envía `library.play` y cierra; "Siguiente" envía `queue.add` con `next: true` y muestra "Agregado"; "Agregar a la cola" envía `queue.add` y muestra "Agregado".
- [ ] Listas:
  - muestra los nombres;
  - "▶ Reproducir lista" envía `playlist.play` con posición 0;
  - "Reproducir desde aquí" en la pista N envía `playlist.play` con posición N.
- [ ] Cola: muestra la cola con "♪ " en la actual, y elegir la pista N envía `queue.play` con posición N.
- [ ] "Apagar" pide "¿Apagar?" con el cursor en No. No vuelve; Sí envía `power_off` una vez y muestra "Apagando…".
- [ ] El cursor no da vuelta: ⏮ en la primera fila y ⏭ en la última no hacen nada.
- [ ] En una carpeta con más de 100 entradas, al acercarse al final se pide la página siguiente una sola vez y se puede llegar a la última entrada.
- [ ] Un pedido que falla muestra el aviso "Error" y deja el menú en el mismo nivel y la misma fila. Una respuesta de un nivel que ya se dejó no cambia nada.
- [ ] El menú se cierra solo tras 30 s sin botones.
- [ ] Mientras un nivel carga se ve "Cargando…", y los botones (y la cuenta de apagado) siguen respondiendo.

### Pantalla
- [ ] La fila seleccionada se dibuja centrada en una píldora de acento, con 2 filas arriba y 2 abajo cuando existen, y el encabezado del nivel arriba.
- [ ] Una etiqueta larga se corta con "…" dentro del círculo, sin salirse.
- [ ] El indicador de volumen y los avisos se dibujan encima del menú.
- [ ] Abrir el menú enciende la pantalla apagada (noche o detenida).
- [ ] Sin menú, `render` produce exactamente las mismas imágenes que antes.

### General
- [ ] No hay cambios en el Service ni en la IPC; las pruebas .NET y las de la web pasan sin tocarlas.
- [ ] Todas las pruebas del hardware-agent pasan, también con las advertencias de obsolescencia tratadas como errores.
- [ ] En la Pi, con los botones reales: se reproduce una carpeta, se agrega una pista, se reproduce una lista desde la pista 3, se salta en la cola y se apaga desde el menú.
- [ ] README, `architecture.md` §8 y §13 (fase 8 al día), `gpio-map.md` y `assembly.md` describen el menú y sus gestos.

## Decisiones tomadas y descartadas

| Decisión | Alternativa descartada | Por qué |
|---|---|---|
| Seis botones, sin botones nuevos | Encoder rotativo, botón "atrás" dedicado | ⏮⏭▶︎menu alcanzan para navegar (como un iPod); el encoder queda como opción de hardware si el scroll se siente lento en la Pi. |
| El menú vive solo en el agente, sobre la IPC existente | Estado del menú en el Service, empujado por snapshot | Cero cambios en el Service; el menú es visual y solo existe con pantalla; la web ya tiene su propia UI. |
| `Gestures` produce nombres locales `menu_*` según `menu_open()`, y `main.py` los reparte | Que `Menu` intercepte los botones del Service, o un segundo `Gestures` | `Gestures` sigue puro y probado con tiempo falso; un único lugar decide adónde va cada gesto. |
| `menu` mantenido abre; adentro, corto = atrás y mantenido = cerrar | Abrir con `menu` corto | `menu` corto ya cicla los modos de pantalla (SPEC 18); el gesto largo estaba reservado (SPEC 20). |
| ▶︎ mantenido apaga también dentro del menú | Deshabilitarlo con el menú abierto | Un gesto, un significado; menos sorpresas. |
| Raíz: Biblioteca · Listas · Cola · Apagar | Solo biblioteca y listas; ajustes en el menú | Refleja las pestañas de la web y reusa la IPC; los ajustes son otra spec. |
| Pista o carpeta → acciones (Reproducir / Siguiente / Agregar) | Elegir = reproducir directo | Encolar sin cortar lo que suena es lo más útil con el reproductor en la mano. |
| "Apagar" del menú pide confirmación, con No por defecto | Apagar directo | Un ▶︎ de más en la raíz no debe apagar. |
| Lista de 5 filas con la seleccionada centrada en una píldora | Un ítem grande con vecinos tenues (3 filas) | Más contexto visible; el centro del círculo es la parte más ancha. |
| Página siguiente automática al acercarse al final | Fila "Más…", como en la web | Navegar con ⏭ mantenido no debería frenar. |
| Sin vuelta en los extremos | Del último al primero | Con scroll rápido es fácil perderse dando vueltas. |
| Pedidos IPC en otro hilo (`run`), con "Cargando…" | Pedidos en el hilo de los botones | Un MPD lento (timeout de 3 s) frenaría los ticks y la cuenta de apagado. |
| `sender.request` compartido; `fetch_cover` lo usa | Otro bucle de lectura copiado en `menu.py` | Una sola implementación de pedido y respuesta de una línea. |
| Timeout fijo de 30 s | Configurable en `player.json` | No hay razón todavía para calibrarlo. |
| "Reproducir" cierra el menú; "Agregar" lo deja abierto con aviso | Siempre cerrar, o nunca | Tras reproducir se quiere ver la pista; tras encolar se suele seguir eligiendo. |
| Errores como aviso "Error", sin cambiar de nivel | Pantalla de error | El usuario reintenta con ▶︎ sin perder dónde estaba; el detalle va al log. |

## Riesgos identificados

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Una carpeta enorme (miles de entradas) | Memoria y pedidos en una Pi Zero | Páginas de 100; solo el nivel actual en memoria, más los cursores de los anteriores; se verifica en la Pi con una carpeta de más de 100. |
| Scroll mantenido a 0,15 s, con cuadro completo por SPI (~27 ms de CPU, SPEC 18) | Uso de CPU o lag al recorrer rápido | Se redibuja solo cuando cambia el cursor (~7 fps). Si hace falta, se ajusta la repetición en la Pi. |
| La cola cambia mientras se ve (termina una pista con `consume`) | `queue.play N` toca otra pista | Se acepta: la ventana es corta y el peor caso es saltar a una vecina. Se recarga al entrar a Cola. |
| Una respuesta tardía llega cuando el usuario ya cambió de nivel | Filas de otro nivel o acción duplicada | Cada respuesta se aplica solo si su nivel sigue arriba de la pila; hay una prueba. |
| La fuente DejaVu no tiene algún carácter de un nombre de archivo | Cuadros vacíos en las filas | Como en el modo pista; aceptado. |
| Se abre el menú con una pulsación accidental de `menu` mantenido | Los botones dejan de controlar la reproducción | Se cierra solo a los 30 s; `menu` corto en la raíz cierra; vol± siguen funcionando. |
| Hilos: el de botones, el de pantalla y el de pedidos tocan el estado del menú | Estados cruzados | Un lock en `Menu`; `run` síncrono en las pruebas; `Display` dibuja con su `_lock` de siempre. |
