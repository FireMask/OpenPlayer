# GPIO Map — OpenPlayer

**Estado:** asignación propuesta. Confirmar orientación del encabezado y cableado antes de energizar.

## 1. Reglas eléctricas

- Los GPIO de Raspberry Pi usan lógica de **3.3 V** y no son tolerantes a 5 V.
- Nunca conectar 5 V a un GPIO.
- Apagar y desconectar la Pi antes de modificar el cableado.
- Para botones, conectar un terminal a GPIO y el otro a GND; activar pull-up interno.
- No conectar salidas de módulos desconocidos hasta verificar tensión y pinout.
- La pantalla GC9A01 (SPEC 17) es opcional. El módulo "1.28 TFT ver 1.0" funciona a 3.3 V en alimentación y lógica: VCC va a 3.3 V, nunca a 5 V.
- El DAC USB se conecta al puerto USB de datos mediante OTG, no a los GPIO.

## 2. Asignación propuesta

| Función | BCM GPIO | Pin físico | Conexión | Estado |
|---|---:|---:|---|---|
| Play/Pause | GPIO17 | 11 | Botón entre GPIO17 y GND | MVP |
| Anterior | GPIO27 | 13 | Botón entre GPIO27 y GND | MVP |
| Siguiente | GPIO22 | 15 | Botón entre GPIO22 y GND | MVP |
| Volumen + | GPIO23 | 16 | Botón entre GPIO23 y GND | MVP |
| Volumen − | GPIO24 | 18 | Botón entre GPIO24 y GND | MVP |
| Menú | GPIO25 | 22 | Botón entre GPIO25 y GND | Reservado |
| Pantalla SCL (SCLK) | GPIO11 / SPI0 SCLK | 23 | SCL del módulo | SPEC 17 |
| Pantalla SDA (MOSI) | GPIO10 / SPI0 MOSI | 19 | SDA del módulo | SPEC 17 |
| Pantalla CS | GPIO8 / SPI0 CE0 | 24 | CS del módulo | SPEC 17 |
| Pantalla DC | GPIO16 | 36 | DC del módulo (`hardware.display.dc`) | SPEC 17 |
| Pantalla RST | GPIO26 | 37 | RST del módulo (`hardware.display.rst`) | SPEC 17 |
| Pantalla VCC | — | 17 | 3.3 V | SPEC 17 |
| Pantalla GND | — | 20 | GND | SPEC 17 |

BCM GPIO y número físico son identificadores distintos. En el código usar los números BCM. Verificar el pinout oficial del modelo de Pi antes de conectar cables.

## 3. Esquema de botones

```text
GPIO17 ----[ botón momentáneo ]---- GND
GPIO27 ----[ botón momentáneo ]---- GND
GPIO22 ----[ botón momentáneo ]---- GND
GPIO23 ----[ botón momentáneo ]---- GND
GPIO24 ----[ botón momentáneo ]---- GND
GPIO25 ----[ botón momentáneo ]---- GND
```

Configurar entradas con pull-up interno. Estado en reposo: alto. Estado pulsado: bajo. No añadir pull-up externo sin motivo; si se añade, usar 3.3 V y calcular su valor apropiadamente.

## 4. Debounce y comportamiento

- Valor inicial sugerido: 50–100 ms (comenzar con 80 ms y probar botones reales).
- Una pulsación corta genera exactamente un evento `button.pressed`: al soltar en ⏭ ⏮ ▶︎ menu (para distinguirla de la larga), al apretar en vol±.
- Pulsación mantenida (SPEC 20): apretada al menos `hardware.holdSeconds` (0,6 s por defecto). Una larga nunca dispara la corta. La detecta `gestures.py` (un hilo hace tick cada 50 ms y suelta un botón cuyo `is_pressed` ya es falso, por si se pierde el evento de soltar).
- `holdSeconds` calibrado con los botones reales: 0,6 s (el valor por defecto; probado en la Pi el 2026-10-24, sin falsas pulsaciones largas).
- Evitar bloquear el proceso de lectura de botones mientras espera respuesta del servicio C#.
- Si el socket no está disponible, reintentar con backoff; no perder el control del loop de GPIO.

## 5. Asignación de eventos

| Nombre de evento | Acción del servicio |
|---|---|
| `play_pause` | Alternar reproducción/pausa |
| `previous` | Ir a pista anterior según política definida |
| `next` | Ir a siguiente pista |
| `volume_up` | Aumentar volumen según paso configurado |
| `volume_down` | Disminuir volumen según paso configurado |
| `menu` | Cicla el modo de la pantalla redonda: pista → reloj → carátula (SPEC 18, 19) |
| `refresh_library` | Reescanear la biblioteca (MPD `update`); solo desde el web agent |
| `seek_forward` / `seek_backward` | Seek ±`seekStepSeconds` (10 s), recortado a 0 y a duración − 1 s (SPEC 20) |
| `power_off` | `systemctl poweroff` vía la regla polkit (SPEC 20) |

Gestos por botón (SPEC 20):

| Botón | Corta | Mantenida (≥ `holdSeconds`) |
|---|---|---|
| `next` / `previous` | Al soltar: `next` / `previous` | `seek_forward` / `seek_backward` enseguida y cada 0,5 s; aviso `+10 s` / `−10 s` |
| `volume_up` / `volume_down` | Al apretar | El mismo evento cada 0,25 s |
| `play_pause` | Al soltar: `play_pause` | Cuenta "Apagar 3… 2… 1"; a `shutdownHoldSeconds` (3 s) envía `power_off` una vez y muestra "Apagando…". Soltar antes no envía nada |
| `menu` | Al soltar: `menu` | Abre el menú en pantalla (SPEC 21); no envía nada al Service |

Con el menú abierto (SPEC 21), ⏮⏭▶︎`menu` producen nombres locales del agente (`menu_up`, `menu_down`, `menu_select`, `menu_back`, `menu_open`, `menu_close`) que nunca llegan al socket:

| Botón | Corta | Mantenida |
|---|---|---|
| `next` / `previous` | `menu_down` / `menu_up` | `menu_down` / `menu_up` enseguida y cada 0,15 s, sin aviso |
| `play_pause` | `menu_select` | Igual que afuera: cuenta y `power_off` |
| `menu` | `menu_back` | `menu_close` |
| `volume_up` / `volume_down` | Igual que afuera | Igual que afuera |

Los nombres de eventos son parte del contrato IPC. Si se renombran, actualizar Python, C#, pruebas y documentación en el mismo cambio.

## 6. Recomendación de cableado

1. Etiquetar cada cable por función o color.
2. Mantener cables de botones alejados de conexiones de alimentación conmutada.
3. Fijar el encabezado y los cables para que no se desprendan al cerrar la carcasa.
4. En la versión final, sustituir protoboard por perfboard/PCB o conectores asegurados.
5. Añadir alivio de tensión a cables que lleguen a conectores externos.

## 7. Validación antes de conectar la aplicación

- Confirmar continuidad de cada botón con multímetro.
- Con la Pi apagada, verificar que ningún botón cortocircuite 3.3 V a GND.
- Iniciar un script mínimo de lectura GPIO y comprobar cada botón por separado.
- Confirmar que GPIO17, 27, 22, 23, 24 y 25 corresponden al mapa elegido en la revisión de placa utilizada.
- Para la pantalla, activar SPI y confirmar que existe `/dev/spidev0.0` (§10) antes de habilitarla.

## 8. Reglas para LLMs

No cambiar el mapa GPIO por conveniencia sin revisar conflictos con I²C, SPI, UART u otras funciones. Nunca sugerir aplicar 5 V a GPIO. No afirmar que una pantalla es compatible solo por el tamaño o la cantidad de pines; comprobar pinout, tensión y controlador. Mantener asignaciones de hardware configurables cuando sea razonable, pero documentar un valor predeterminado único.

## 9. Prueba sin botones: cable de puente

Implementado por el hardware agent (SPEC 05). Mientras no haya botones cableados, un cable dupont hembra-hembra entre un GPIO y GND reproduce exactamente el circuito del botón (pull-up interno: tocar GND = pulsar).

Pines (encabezado de 40 pines; confirmar con el pinout oficial antes de tocar nada):

| Botón | GPIO (BCM) | Pin físico | GND más cercano |
|---|---|---|---|
| Play/Pause | GPIO17 | 11 | 9 |
| Anterior | GPIO27 | 13 | 9 o 14 |
| Siguiente | GPIO22 | 15 | 14 |
| Volumen + | GPIO23 | 16 | 14 |
| Volumen − | GPIO24 | 18 | 20 |
| Menú | GPIO25 | 22 | 20 o 25 |

Procedimiento:

1. Identificar el pin GND en el pinout oficial (pines físicos 6, 9, 14, 20, 25, 30, 34 y 39).
2. Conectar primero un extremo del cable en GND y dejarlo fijo.
3. Tocar brevemente el pin del GPIO con el otro extremo y retirarlo: es una pulsación.
4. Ver el resultado con `journalctl -u openplayer-hardware -f` y `mpc status`.

Reglas: el cable va **solo** entre un GPIO de la tabla y GND. Nunca tocar los pines de 3.3 V (1, 17) ni de 5 V (2, 4), ni otros GPIO: un cortocircuito a 3.3 V o 5 V puede dañar la Pi.

Debounce: un cable rebota más que un botón. Si un toque genera dos líneas `button …` en el log, subir `hardware.debounceSeconds` en `/opt/openplayer/player.json` (rango 0.01–1) y aplicar con `sudo systemctl restart openplayer-hardware`. Recalibrar al cablear los botones reales.

Validado (2026-10-20, Pi Zero 2 W, cable dupont): con `debounceSeconds` 0.08 (valor por defecto), 31 toques dieron 31 eventos, sin dobles.

## 10. Pantalla GC9A01 por SPI

Implementada por el hardware agent (SPEC 17). Módulo redondo de 1,28" 240x240 con 7 pines (VCC, GND, SCL, SDA, DC, CS, RST), sin pin de retroiluminación: la luz queda encendida mientras haya alimentación.

```text
Módulo        Pi (pin físico)
VCC  -------- 3.3 V (17)
GND  -------- GND   (34)
SCL  -------- GPIO11 / SCLK (23)
SDA  -------- GPIO10 / MOSI (19)
CS   -------- GPIO8  / CE0  (24)
DC   -------- GPIO16        (36)
RST  -------- GPIO26        (37)
```

- Cablear con la Pi apagada y verificar el pinout serigrafiado del módulo antes de energizar.
- La pantalla usa el bus SPI0, así que GPIO7–11 no quedan libres para otros usos. GPIO16 y GPIO26 no chocan con los botones (§2); si se cambian en `player.json`, el agente rechaza un pin repetido.
- Activar SPI una vez: `sudo raspi-config nonint do_spi 0`, y comprobar con `ls /dev/spidev0.0`. `install.sh` avisa si falta.
- Habilitar en `/opt/openplayer/player.json` con `"hardware": {"display": {"enabled": true, ...}}` y `sudo systemctl restart openplayer-hardware`.
- Calibración: si aparece basura o parpadeo con cables dupont largos, bajar `spiHz` (por ejemplo a 20000000). Si la imagen sale girada, ajustar `rotation` (0, 90, 180 o 270).

Validado (2026-10-24, Pi Zero 2 W, Pi OS trixie, cables dupont): con `rotation` 0 la imagen salía al revés; el valor por defecto quedó en 180. `spiHz` 40000000 sin problemas a la vista.

Cambio de pines (2026-10-24): DC y RST pasaron de GPIO5/GPIO6 (pines 29/31) a GPIO16/GPIO26 (36/37) y GND del 20 al 34 tras un cortocircuito entre los pines 29, 30 y 31 (RST unido a DC y GND: pantalla encendida pero negra). Si la pantalla queda negra o se desvanece a blanco, medir continuidad entre pines vecinos del header antes de tocar el código.

## 11. PCB portadora (SPEC 22)

La PCB Rev A (`hardware/pcb/`) solo puentea: mismos GPIO que `player.json`, sin cambios de software. La Pi va al lado, unida por un cable plano IDC de 40 pines (J1, pin N = pin físico N). La Pi se alimenta por los pines 2 y 4 (5 V); **no** enchufar el micro-USB de alimentación de la Pi con el cable plano conectado.

J4 `BUTTONS` (JST-XH 8 pines, a la placa de botones):

| J4 | Señal | BCM GPIO | Pin físico |
|---:|---|---:|---:|
| 1 | GND | — | GND |
| 2 | Play/Pause | GPIO17 | 11 |
| 3 | Anterior | GPIO27 | 13 |
| 4 | Siguiente | GPIO22 | 15 |
| 5 | Volumen + | GPIO23 | 16 |
| 6 | Volumen − | GPIO24 | 18 |
| 7 | Menú | GPIO25 | 22 |
| 8 | `PWR_KEY` | — | — |

`PWR_KEY` **no** es un GPIO: va solo a J3 y de ahí al pad `K` del módulo de carga (encendido con la Pi apagada).

J5 `DISPLAY` (hembra 1×7, 2,54 mm; la pantalla se enchufa directo), en el orden serigrafiado del módulo:

| J5 | Módulo | BCM GPIO | Pin físico |
|---:|---|---:|---:|
| 1 | VCC | 3.3 V | 1, 17 |
| 2 | GND | — | GND |
| 3 | SCL | GPIO11 / SCLK | 23 |
| 4 | SDA | GPIO10 / MOSI | 19 |
| 5 | DC | GPIO16 | 36 |
| 6 | CS | GPIO8 / CE0 | 24 |
| 7 | RST | GPIO26 | 37 |

Si se cambia un pin por defecto en `config/player.example.json`, actualizar `hardware/pcb/scripts/netlist.py` (su autocomprobación falla si no coinciden).
