# OpenPlayer

Reproductor musical DIY modular basado en Raspberry Pi Zero 2 W, Raspberry Pi OS Lite, MPD, un servicio de control en C#/.NET y un agente de hardware en Python.

## Estado del proyecto

Este repositorio contiene la documentación base para que una persona o un LLM pueda implementar el sistema de forma incremental. Las decisiones que requieren validación física están marcadas como **POR VALIDAR**; no deben asumirse como hardware ya probado.

## Objetivo de la primera versión

- Reproducir archivos locales MP3 y FLAC mediante MPD.
- Utilizar el DAC USB existente con salida de auriculares de 3.5 mm.
- Controlar reproducción, navegación y volumen mediante botones GPIO.
- Controlar y diagnosticar el sistema por SSH.
- Mantener separadas las responsabilidades del servicio C# y del agente Python.
- Pantalla redonda GC9A01 opcional con la pista actual (SPEC 17).
- Preparar soporte futuro para salida Bluetooth A2DP y alimentación portátil.

## Documentación de diseño

- [`docs/architecture.md`](docs/architecture.md): arquitectura, contratos, IPC, software, estados y plan de implementación.
- [`docs/gpio-map.md`](docs/gpio-map.md): asignación GPIO, cableado, seguridad eléctrica y pruebas.
- [`docs/battery-design.md`](docs/battery-design.md): requisitos y opciones para la alimentación portátil.
- [`docs/assembly.md`](docs/assembly.md): montaje, instalación, despliegue, pruebas y solución de problemas. Para cargar música desde Windows, ver §5 "Importar música por Samba" (`\\mpi3-player.local\music`).

> Nota sobre el nombre: el archivo se llama `battery-design.md` (ortografía corregida de `battery-desing.md`).

## Reglas de desarrollo

1. No acoplar el Core a MPD, GPIO, Linux, sockets ni bibliotecas de terceros.
2. MPD es la fuente de verdad para el estado de reproducción.
3. Python detecta entradas físicas y envía eventos; no ejecuta comandos MPD.
4. C# valida los eventos y decide las acciones.
5. No asumir que el DAC es siempre `card 1`; descubrir dispositivos con ALSA.
6. No conectar GPIO a 5 V. Los GPIO de Raspberry Pi son de 3.3 V.
7. No implementar alimentación con batería Li-ion/LiPo sin verificar carga, protección, regulación y apagado seguro.
8. No exponer MPD ni el socket IPC a Internet.
9. Añadir pruebas y actualizar los documentos cuando cambien interfaces o cableado.

## Compilar y probar

Requiere el SDK de .NET 10 (fijado en `global.json`). Las pruebas corren en Windows o Linux:

```bash
dotnet build OpenPlayer.slnx
dotnet test OpenPlayer.slnx
```

## Ejecutar el Service

En la Pi corre como unidad systemd `openplayer` (usuario de sistema `openplayer`, binario en `/opt/openplayer`). Lee `/opt/openplayer/player.json` (copia de `config/player.example.json`) y escucha en el socket Unix `ipc.unixSocketPath` (por defecto `/run/openplayer/hardware.sock`, directorio creado por systemd) mensajes JSON Lines; contrato en [`docs/architecture.md`](docs/architecture.md) §7.

```bash
systemctl status openplayer              # estado
sudo systemctl restart openplayer        # p. ej. tras editar /opt/openplayer/player.json
sudo systemctl stop openplayer
journalctl -u openplayer -b -f           # logs
```

Probar con `socat` (`sudo apt install socat`). El usuario que despliega está en el grupo `openplayer`; tras el primer deploy, abrir una sesión SSH nueva para que el grupo aplique.

```bash
S=UNIX-CONNECT:/run/openplayer/hardware.sock
echo '{"type":"player.get_snapshot"}' | socat - $S
echo '{"type":"button.pressed","button":"play_pause"}' | socat - $S
```

| Mensaje | Efecto |
|---|---|
| `{"type":"button.pressed","button":"<nombre>"}` con `play_pause`, `previous`, `next`, `volume_up`, `volume_down`, `menu` | Igual que el botón físico; sin respuesta |
| `{"type":"player.get_snapshot"}` | Responde una línea `player.snapshot`, o `error` si MPD no responde |

Un mensaje inválido o sin MPD accesible solo registra un warning; el proceso sigue. Si `socat` corta la respuesta, usar `socat -t 2`.

Para ejecutarlo a mano (depurar), detener antes la unidad: dos instancias compiten por el socket. Al detenerse, systemd borra `/run/openplayer`, así que hay que recrearlo. Ctrl+C sale con código 0 y borra el socket.

```bash
sudo systemctl stop openplayer
sudo install -d -o openplayer -g openplayer -m 0770 /run/openplayer
sudo -u openplayer /opt/openplayer/OpenPlayer.Service
sudo systemctl start openplayer
```

En Windows (`dotnet run --project src/OpenPlayer.Service`) hay que apuntar `ipc.unixSocketPath` a una carpeta existente (ruta de máximo 108 caracteres).

## Publicar para la Raspberry Pi

Publicación autocontenida (no requiere instalar .NET en la Pi). Desde Windows, `deploy.ps1` compila, copia y ejecuta `deploy/install.sh` con sudo en la Pi:

```powershell
.\deploy.ps1 -Device openplayer.local -User <usuario> [-Password <contraseña>]
```

`install.sh` es idempotente: verifica `python3-gpiozero` y `python3-lgpio` (no los instala), crea el usuario y grupo `openplayer` si faltan, añade `<usuario>` al grupo, instala en `/opt/openplayer` el Service, `hardware-agent/` y `web-agent/` (sin sobrescribir un `player.json` existente; solo le agrega la sección `web` si falta), instala `deploy/openplayer.service`, `deploy/openplayer-hardware.service` y `deploy/openplayer-web.service`, las habilita y las reinicia. Termina con error y muestra `journalctl` si alguna unidad no queda lista.

`-Password` sirve para ssh y sudo, pero queda en el historial de PowerShell; sin él, ssh usa tu clave (`ssh-copy-id`) y sudo pide la contraseña en la terminal.

Sin PowerShell, el equivalente manual:

```bash
dotnet publish src/OpenPlayer.Service -c Release -r linux-arm64 --self-contained true -o publish/linux-arm64
tar -czf openplayer.tgz --exclude=__pycache__ --exclude=requirements-dev.txt -C publish/linux-arm64 . -C "$PWD/src" hardware-agent web-agent
scp openplayer.tgz deploy/install.sh deploy/openplayer.service deploy/openplayer-hardware.service deploy/openplayer-web.service <usuario>@openplayer.local:/tmp/
ssh -t <usuario>@openplayer.local 'sudo bash /tmp/install.sh /tmp/openplayer.tgz /tmp/openplayer.service $USER'
```

La instalación anterior en `~/openplayer` (SPEC 02/03) ya no se usa; se puede borrar con `rm -r ~/openplayer`.

## Hardware agent (botones GPIO)

`src/hardware-agent` (Python, stdlib y `gpiozero`; Pillow y `spidev` solo con pantalla) lee los botones de `hardware.buttons` en `player.json` (BCM, pull-up interno, debounce `hardware.debounceSeconds`) y envía `button.pressed` al socket. Corre como unidad `openplayer-hardware`; si el Service no está disponible, descarta la pulsación con un warning y reconecta solo.

```bash
systemctl status openplayer-hardware
journalctl -u openplayer-hardware -b -f   # connected / disconnected / button <nombre> (sequence N)
```

Sin botones cableados se prueba con un cable dupont entre el GPIO y GND, siguiendo el procedimiento seguro de [`docs/gpio-map.md`](docs/gpio-map.md) §9. Nunca tocar pines de 3.3 V o 5 V.

Pruebas en Windows o Linux (GPIO simulado con `MockFactory`, socket con un servidor TCP local):

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r src/hardware-agent/requirements-dev.txt   # Linux: .venv/bin/python
.venv/Scripts/python -m pytest tests/hardware-agent
```

Para correrlo en Windows sin hardware: `GPIOZERO_PIN_FACTORY=mock python src/hardware-agent/main.py config/player.example.json` (sin `AF_UNIX`, solo queda desconectado).

### Pantalla redonda (opcional)

El mismo agente dibuja la pista actual (título, artista, álbum, ícono y anillo de progreso) o un reloj en una pantalla GC9A01 de 1,28" 240x240 por SPI (SPEC 17), con el estado que publica el Service (`player.subscribe`). Viene deshabilitada. Para usarla:

1. Cablear según [`docs/gpio-map.md`](docs/gpio-map.md) §10 (VCC a 3.3 V).
2. Activar SPI (`sudo raspi-config nonint do_spi 0`) e instalar `sudo apt install python3-pil python3-spidev fonts-dejavu-core`.
3. Poner `hardware.display.enabled` en `true` en `/opt/openplayer/player.json` y `sudo systemctl restart openplayer-hardware`.

```bash
journalctl -u openplayer-hardware -b -f   # display ready (spi0.0, 40000000 Hz) / display init failed: … / display: disconnected …
```

Con el Service detenido muestra "Sin conexión"; si la pantalla falla, el log lo dice y los botones siguen. `spiHz` y `rotation` se calibran en `player.json`; montaje y problemas en [`docs/assembly.md`](docs/assembly.md) §11.

Modos (SPEC 18): el botón `menu` alterna entre **pista** (ícono, título, artista, álbum, `1:23 / -2:40`, `3 / 12` y anillo de progreso) y **reloj** (HH:MM de 24 h, fecha como `sáb 24 oct` y el anillo si hay pista). El modo lo guarda el Service en memoria y vuelve a pista al reiniciarlo. Además:

- En pausa o detenida durante `idleClockSeconds` (60 por defecto; `null` lo desactiva) muestra el reloj; al reproducir vuelve a la pista.
- Cada cambio de volumen muestra 2 s un anillo azul interior y el número grande.
- Un título que no entra se desplaza mientras suena (pausa de 1 s en cada extremo).
- Ahorro opcional (apagado por defecto): `nightStart`/`nightEnd` (`"HH:MM"`, puede cruzar la medianoche) y `offAfterStoppedMinutes` apagan el panel (`DISPOFF`). Cualquier botón la enciende 10 s y además hace su acción; empezar a reproducir también la enciende.

## Web agent (control desde el navegador)

`src/web-agent` (Python, solo stdlib) sirve una página con los 6 botones y el estado actual en `http://mpi3-player.local:8080` (puerto `web.port` de `player.json`). Cada botón envía el mismo `button.pressed` que el botón físico. Una barra de progreso muestra la posición de la pista (`m:ss / m:ss`) y avanza sola; arrastrarla y soltarla salta a esa posición (`player.seek`). La pestaña **Biblioteca** recorre las carpetas de la música, busca por texto y reproduce una pista; con "+" agrega una pista o una carpeta entera a una lista. La pestaña **Listas** maneja las playlists guardadas de MPD (las mismas que `mpc lsplaylists`): crear, renombrar, borrar, reordenar con ↑/↓, quitar y reproducir. Reproducir una pista o una lista **reemplaza la cola actual** sin aviso. Borrar una lista solo borra su `.m3u`, nunca la música. El panel **Cola** (a la derecha en pantallas anchas; debajo de los controles en el móvil) muestra la cola actual de MPD con el origen de cada canción (la lista o "Biblioteca"), la pista actual resaltada con barras animadas (quietas en pausa) y salta a una pista al tocarla. Cada fila de la cola tiene ↑/↓ para reordenar y ✕ para quitarla; "Limpiar" vacía la cola (pide confirmación y detiene la reproducción). Editar la cola no cambia la lista guardada. En la Biblioteca, "+" abre un menú con "Reproducir siguiente" (después de la actual; varias seguidas quedan en orden inverso), "Agregar a la cola" (al final) y "Agregar a una lista ›"; vale para pistas y carpetas. "Guardar como lista" en el panel guarda la cola como una lista nueva (no sobrescribe una existente). La cola funciona como en Spotify: el Service activa el modo `consume` de MPD, así que cada canción terminada o saltada sale de la cola y la actual queda arriba (también afecta a `mpc`, que usa el mismo MPD). ⏮ en los primeros 3 s vuelve a la canción anterior: el Service recuerda las últimas 50 escuchadas y la pone arriba de la cola (la actual queda segunda); pasados 3 s, o sin historial, reinicia la canción actual. El historial se pierde al reiniciar el Service. El origen de cada canción se recuerda en memoria y se pierde al reiniciar el Service. Solo responde a la red local (rangos privados, `::1`, `fe80::/10`) y no pide contraseña; si el Service no está disponible, la página muestra "Sin conexión con el reproductor" y se recupera sola. La página se actualiza al instante (canción, play/pausa, volumen y cola, también si cambian desde `mpc` u otro navegador): el Service avisa cada cambio de MPD y el web agent lo reenvía por `GET /api/events` (SSE). Si ese stream se corta (móvil en segundo plano, reinicio del Service, más de 8 páginas abiertas), la página vuelve a consultar cada 2 s hasta que el navegador reconecta. Corre como unidad `openplayer-web`; contrato HTTP en [`docs/architecture.md`](docs/architecture.md) §5.

```bash
systemctl status openplayer-web
journalctl -u openplayer-web -b -f   # ready / button <nombre> / seek <N> / warnings
journalctl -u openplayer -b -f       # <request> ok / <request> failed: … (biblioteca, listas y cola)
```

Pruebas (Windows o Linux; HTTP real en puerto aleatorio, socket simulado). Correr cada carpeta por separado: ambos agentes tienen su propio `config.py`.

```bash
.venv/Scripts/python -m pytest tests/web-agent
```

Para correrlo en Windows: `python src/web-agent/main.py config/player.example.json` y abrir `http://localhost:8080` (sin `AF_UNIX`, los botones responden 503).

## Estructura

```text
OpenPlayer/
├── README.md
├── LICENSE
├── .gitignore
├── OpenPlayer.slnx
├── global.json
├── Directory.Build.props
├── deploy.ps1
├── specs/
├── docs/
│   ├── architecture.md
│   ├── gpio-map.md
│   ├── battery-design.md
│   └── assembly.md
├── config/
│   └── player.example.json
├── src/
│   ├── OpenPlayer.Core/
│   │   ├── Models/
│   │   ├── Commands/
│   │   └── Interfaces/
│   ├── OpenPlayer.Mpd/
│   ├── OpenPlayer.Service/
│   ├── hardware-agent/
│   └── web-agent/
├── deploy/
│   ├── openplayer.service
│   ├── openplayer-hardware.service
│   └── openplayer-web.service
└── tests/
    ├── OpenPlayer.Core.Tests/
    ├── OpenPlayer.Mpd.Tests/
    ├── OpenPlayer.Service.Tests/
    ├── hardware-agent/
    └── web-agent/
```

## Convenciones para un LLM que trabaje en el repositorio

Antes de implementar una función, leer `README.md` y los documentos relevantes de `docs/`. Respetar las decisiones de arquitectura, distinguir hechos validados de hipótesis, y no cambiar asignaciones de GPIO ni el protocolo IPC sin actualizar documentación y pruebas. Implementar en etapas pequeñas y explicar comandos que requieran privilegios de administrador.
