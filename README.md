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
- Preparar soporte futuro para OLED, salida Bluetooth A2DP y alimentación portátil.

## Documentación de diseño

- [`docs/architecture.md`](docs/architecture.md): arquitectura, contratos, IPC, software, estados y plan de implementación.
- [`docs/gpio-map.md`](docs/gpio-map.md): asignación GPIO, cableado, seguridad eléctrica y pruebas.
- [`docs/battery-design.md`](docs/battery-design.md): requisitos y opciones para la alimentación portátil.
- [`docs/assembly.md`](docs/assembly.md): montaje, instalación, despliegue, pruebas y solución de problemas.

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

`install.sh` es idempotente: crea el usuario y grupo `openplayer` si faltan, añade `<usuario>` al grupo, instala en `/opt/openplayer` (sin sobrescribir un `player.json` existente), instala `deploy/openplayer.service`, la habilita y la reinicia. Termina con error y muestra `journalctl` si la unidad no queda escuchando.

`-Password` sirve para ssh y sudo, pero queda en el historial de PowerShell; sin él, ssh usa tu clave (`ssh-copy-id`) y sudo pide la contraseña en la terminal.

Sin PowerShell, el equivalente manual:

```bash
dotnet publish src/OpenPlayer.Service -c Release -r linux-arm64 --self-contained true -o publish/linux-arm64
tar -czf openplayer.tgz -C publish/linux-arm64 .
scp openplayer.tgz deploy/install.sh deploy/openplayer.service <usuario>@openplayer.local:/tmp/
ssh -t <usuario>@openplayer.local 'sudo bash /tmp/install.sh /tmp/openplayer.tgz /tmp/openplayer.service $USER'
```

La instalación anterior en `~/openplayer` (SPEC 02/03) ya no se usa; se puede borrar con `rm -r ~/openplayer`.

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
│   └── hardware-agent/
├── deploy/
│   ├── openplayer.service
│   └── openplayer-hardware.service
└── tests/
    ├── OpenPlayer.Core.Tests/
    ├── OpenPlayer.Mpd.Tests/
    ├── OpenPlayer.Service.Tests/
    └── hardware-agent/
```

## Convenciones para un LLM que trabaje en el repositorio

Antes de implementar una función, leer `README.md` y los documentos relevantes de `docs/`. Respetar las decisiones de arquitectura, distinguir hechos validados de hipótesis, y no cambiar asignaciones de GPIO ni el protocolo IPC sin actualizar documentación y pruebas. Implementar en etapas pequeñas y explicar comandos que requieran privilegios de administrador.
