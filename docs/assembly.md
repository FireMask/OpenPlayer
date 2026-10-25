# Assembly & Deployment — OpenPlayer

**Estado:** guía de montaje incremental. Los comandos pueden variar según la versión de Raspberry Pi OS y los paquetes disponibles.

## 1. Alcance

Este documento lleva desde una Raspberry Pi Zero 2 W recién preparada hasta un prototipo con reproducción por DAC USB, control por SSH, botones GPIO y pantalla redonda opcional (§11). Bluetooth y batería integrada se incorporan después.

## 2. Antes de empezar

Hardware:

- Raspberry Pi Zero 2 W y microSD.
- DAC USB y adaptador OTG compatible.
- Fuente USB estable para pruebas.
- Botones momentáneos, protoboard y cables.
- Multímetro recomendado.

Software:

- Raspberry Pi Imager.
- Cliente SSH desde el PC.
- Git.
- .NET SDK en el PC de desarrollo y runtime compatible en la Pi, o publicación autocontenida ARM64.

## 3. Instalar Raspberry Pi OS Lite

1. Usar Raspberry Pi Imager para escribir Raspberry Pi OS Lite de 64 bits.
2. Configurar nombre de host, usuario, Wi-Fi y SSH en las opciones de Imager.
3. Iniciar la Pi y conectarse por SSH.

```bash
ssh <usuario>@openplayer.local
```

Si mDNS no resuelve, encontrar la IP en el router y conectarse por IP. No documentar contraseñas en el repositorio.

Actualizar e instalar herramientas:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y git curl python3 python3-venv python3-pip \
  mpd mpc alsa-utils
```

Los paquetes de GPIO dependen de la distribución. Comprobar disponibilidad antes de instalarlos, por ejemplo `apt-cache policy python3-gpiozero python3-lgpio`.

## 4. Validar DAC USB y ALSA

Conectar el DAC al puerto USB de datos mediante OTG. Después:

```bash
lsusb
aplay -l
cat /proc/asound/cards
```

Reproducir un archivo WAV de prueba mediante ALSA una vez identificada la tarjeta y el dispositivo correctos. No copiar comandos con un índice de tarjeta asumido: los números dependen del hardware detectado. Si no aparece el DAC, comprobar adaptador OTG, cable, alimentación y compatibilidad.

El índice (`card 0`, `card 1`) cambia según el orden de detección; el **id** de la tarjeta no. Es la palabra entre corchetes en `/proc/asound/cards` (o la que sigue a `card N:` en `aplay -l`). Con el DAC C-Media validado:

```text
$ cat /proc/asound/cards
 0 [Device         ]: USB-Audio - USB Audio Device
                      C-Media Electronics Inc. USB Audio Device at usb-3f980000.usb-1, full speed
 1 [vc4hdmi        ]: vc4-hdmi - vc4-hdmi
                      vc4-hdmi
```

Aquí el id es `Device`, y el dispositivo ALSA es `hw:CARD=Device,DEV=0`. Probar con `speaker-test -D hw:CARD=Device,DEV=0 -c 2 -t wav -l 1`. Este nombre es el que va a MPD (§5).

## 5. Configurar música y MPD

Crear el directorio de música y copiar algunos archivos:

```bash
mkdir -p ~/Music
```

Elegir conscientemente entre MPD del sistema y una instancia por usuario. En la instancia de sistema, revisar `/etc/mpd.conf`, permisos del directorio y usuario del servicio. El usuario de MPD debe poder recorrer todos los directorios y leer los archivos de música.

Como base de configuración, verificar:

```conf
music_directory "/home/<usuario>/Music"
playlist_directory "/home/<usuario>/Playlists"
bind_to_address "127.0.0.1"
port "6600"
```

No reemplazar ciegamente el archivo completo: conservar la configuración necesaria del paquete, configurar un `audio_output` que corresponda al DAC detectado y revisar los logs.

El `audio_output` usa el id de la tarjeta (§4), nunca el índice: con `hw:<índice>,0`, si el DAC cambia de número tras un reinicio, MPD abre otra tarjeta (p. ej. HDMI) o falla. Bloque de referencia (sustituir `<id>`; `Device` en el DAC validado):

```conf
audio_output {
	type		"alsa"
	name		"USB DAC"
	device		"hw:CARD=<id>,DEV=0"
	mixer_type	"software"
}
```

`mixer_type "software"` hace que MPD controle el volumen y lo reporte en `mpc volume` y en el snapshot. Tras editar: `sudo systemctl restart mpd` y comprobar con `mpc play` y `journalctl -u mpd -b`.

```bash
sudo systemctl enable --now mpd
mpc update
mpc listall
mpc status
```

Añadir una ruta que aparezca en `mpc listall` y probar:

```bash
mpc add "ruta/relativa/cancion.mp3"
mpc play
mpc pause
mpc next
```

Si `mpc` no conecta, verificar servicio, puerto, instancia de MPD y configuración de `mpc`. No abrir el puerto 6600 a la red como solución rápida.

### Importar música por Samba

Comparte `music_directory` en la red local para copiar música desde el Explorador de Windows; MPD la agrega sola a la biblioteca. Solo red local y con contraseña: no exponer el puerto 445 a Internet.

```bash
sudo apt install samba
sudo systemctl disable --now nmbd   # sin NetBIOS: se accede por ruta, no por "Red"
```

En `/etc/samba/smb.conf`, añadir dentro de la sección `[global]` existente:

```ini
   hosts allow = 127. 10. 172.16.0.0/12 192.168. ::1 fe80::/10
   hosts deny = ALL
   server min protocol = SMB2
```

Y al final del archivo:

```ini
[music]
   path = /home/andres/Music
   valid users = andres
   read only = no
   create mask = 0664
   directory mask = 0775
```

Las máscaras dejan lo copiado legible para el usuario `mpd`. Aplicar y crear la contraseña Samba (distinta de la de SSH; se pide en la terminal):

```bash
testparm -s                      # sin errores; muestra [music]
sudo systemctl restart smbd
sudo smbpasswd -a andres
```

En `/etc/mpd.conf`, para que MPD vigile la carpeta (inotify) y no haga falta `mpc update`; crear también `playlist_directory`, que MPD registra como error si falta:

```conf
auto_update "yes"
```

```bash
mkdir -p ~/Playlists
# MPD corre como usuario mpd: necesita escribir aquí para guardar listas (SPEC 10, mpc save).
# setgid: los .m3u nuevos quedan con grupo andres.
sudo chown mpd:andres ~/Playlists
sudo chmod 2775 ~/Playlists
sudo systemctl restart mpd
```

Sin el `chown`, crear o editar una lista desde la web falla con `Failed to append to …/Playlists/<lista>.m3u: Permission denied`.

Desde Windows: abrir `\\mpi3-player.local\music` en el Explorador e iniciar sesión con `andres` y la contraseña Samba. Opcional, como unidad fija: clic derecho en "Este equipo" → "Conectar a unidad de red". Lo copiado aparece en `mpc listall` en segundos; lo borrado desaparece.

## 6. Controles iniciales por SSH

Comandos de diagnóstico útiles:

```bash
systemctl status mpd
journalctl -u mpd -b --no-pager
aplay -l
mpc status
mpc current
```

El MVP debe funcionar desde SSH antes de integrar GPIO. No desarrollar la interfaz de botones mientras la ruta de audio todavía sea inestable.

## 7. Preparar el repo y .NET

Desde el PC de desarrollo, crear la solución con la estructura del README. La implementación debe empezar por Core y pruebas, no por GPIO.

Ejemplo de comandos para iniciar la solución:

```bash
dotnet new sln -n OpenPlayer
dotnet new classlib -n OpenPlayer.Core -o src/OpenPlayer.Core
dotnet new console -n OpenPlayer.Service -o src/OpenPlayer.Service
dotnet sln add src/OpenPlayer.Core/OpenPlayer.Core.csproj
dotnet sln add src/OpenPlayer.Service/OpenPlayer.Service.csproj
dotnet add src/OpenPlayer.Service/OpenPlayer.Service.csproj reference src/OpenPlayer.Core/OpenPlayer.Core.csproj
```

Publicar e instalar en la Pi (ARM64), autocontenido (SPEC 02: no requiere el runtime de .NET en la Pi) y como unidad systemd (SPEC 04). Confirmar la arquitectura con `uname -m` (`aarch64`). Desde Windows:

```powershell
.\deploy.ps1 -Device openplayer.local -User <usuario> [-Password <contraseña>]
```

`deploy.ps1` compila, copia a `/tmp/openplayer-deploy` y ejecuta `deploy/install.sh` con sudo. Explicación de lo que hace `install.sh` (idempotente, se puede repetir en cada deploy):

- Crea el grupo y el usuario de sistema `openplayer` (sin login ni home) si faltan, y añade `<usuario>` al grupo para poder usar el socket con `socat`.
- Extrae el publish en `/opt/openplayer` (dueño `root`, legible por todos). `player.json` solo se copia si no existe: los ajustes hechos en la Pi se conservan.
- Instala `deploy/openplayer.service` en `/etc/systemd/system/`, la habilita para el arranque y la reinicia.

`/opt/openplayer/player.json` es copia de `config/player.example.json`; editarlo con `sudo` si MPD no está en `127.0.0.1:6600` y luego `sudo systemctl restart openplayer`. El equivalente sin PowerShell está en `README.md`.

Prueba manual por SSH (abrir una sesión nueva tras el primer deploy, para que aplique el grupo `openplayer`):

```bash
sudo apt install -y socat
systemctl status openplayer
echo '{"type":"player.get_snapshot"}' | socat - UNIX-CONNECT:/run/openplayer/hardware.sock
```

Comparar el `player.snapshot` con `mpc current`; más mensajes en `README.md`. Si `volume` sale `null`, el `audio_output` de MPD no tiene mixer: añadir `mixer_type "software"` si se quiere controlar volumen.

La instalación manual de SPEC 02/03 (`~/openplayer` y `mkdir /run/openplayer` a mano) ya no se usa: borrar `~/openplayer` y detener cualquier `OpenPlayer.Service` lanzado a mano antes del primer deploy, porque compite por el socket.

## 8. Agente Python y GPIO

El agente (SPEC 05, `src/hardware-agent`) usa los paquetes del sistema, ya presentes en Raspberry Pi OS. Comprobarlos (y, si faltan, instalarlos; `install.sh` solo los verifica):

```bash
apt-cache policy python3-gpiozero python3-lgpio python3-pil python3-spidev fonts-dejavu-core
sudo apt install python3-gpiozero python3-lgpio python3-pil python3-spidev fonts-dejavu-core
```

El mismo `deploy.ps1` de §7 lo instala en `/opt/openplayer/hardware-agent` con la unidad `openplayer-hardware` (usuario `openplayer` en los grupos `gpio`, que da acceso a `/dev/gpiochip0`, y `spi`, para la pantalla). Lee pines y debounce de `/opt/openplayer/player.json`. Usar los GPIO BCM de `gpio-map.md` con pull-up interno; el esquema es GPIO ↔ botón ↔ GND, nunca a 3.3 V ni 5 V.

```bash
systemctl status openplayer-hardware
journalctl -u openplayer-hardware -b -f
```

Sin botones, probar con un cable de puente siguiendo `gpio-map.md` §9. La pantalla se monta en §11.

### Apagado con ▶︎ (SPEC 20)

Mantener ▶︎ 3 s (`hardware.shutdownHoldSeconds`) apaga la Pi: el Service ejecuta `systemctl poweroff` como `openplayer`. Las unidades corren con `NoNewPrivileges` (sudo no sirve); el permiso lo da la regla polkit `/etc/polkit-1/rules.d/50-openplayer-poweroff.rules`, que instala `install.sh` y solo permite `org.freedesktop.login1.power-off`. Necesita `polkitd` (`install.sh` avisa si falta: `sudo apt install polkitd`).

```bash
sudo -u openplayer systemctl poweroff --dry-run   # sin contraseña ni "Access denied"
journalctl -u openplayer -b -f                    # Power off requested (button) / Power off failed: …
journalctl -b -1 | tail                           # en el arranque siguiente: Reached target poweroff / System Power Off
```

Si falla, el Service registra `Power off failed: …` y sigue funcionando. Después del apagado la Pi Zero sigue entregando 3,3 V mientras tenga alimentación: el panel queda negro (`DISPOFF`) pero con la luz encendida y consumiendo. Cortar con el interruptor de alimentación (ver `battery-design.md` §7).

### Control desde el navegador (web agent)

El mismo `deploy.ps1` instala el web agent (SPEC 08) en `/opt/openplayer/web-agent` con la unidad `openplayer-web` (usuario `openplayer`). No necesita paquetes extra: solo Python 3 de la imagen. Escucha en el puerto `web.port` de `/opt/openplayer/player.json` (8080; `install.sh` agrega la sección si un `player.json` anterior no la tiene).

Abrir `http://mpi3-player.local:8080` desde un navegador de la misma red (PC o móvil). Si `.local` no resuelve en el móvil, usar la IP (`hostname -I`). Solo responde a direcciones privadas; no abrir el puerto 8080 en el router.

```bash
systemctl status openplayer-web
journalctl -u openplayer-web -b -f
```

Para cambiar el puerto: editar `web.port` (1024–65535) y `sudo systemctl restart openplayer-web`.

## 9. Socket Unix y systemd

Implementado en `deploy/openplayer.service` (SPEC 04):

- `User=openplayer`, `Group=openplayer`. `RuntimeDirectory=openplayer` con `RuntimeDirectoryMode=0770`: systemd crea `/run/openplayer` en cada arranque (y lo borra al detener); el Service crea el socket con `0660`. El agente comparte el grupo `openplayer`. No dar acceso global al socket.
- `Wants=mpd.service` y `After=mpd.service`: reiniciar MPD no reinicia el Service, que sobrevive solo a una caída de MPD.
- `Restart=on-failure` cada 3 s, con `StartLimitIntervalSec=60` y `StartLimitBurst=5`: un `player.json` inválido deja la unidad en `failed` tras 5 intentos en lugar de reintentar sin fin. Corregir el archivo y `sudo systemctl restart openplayer`.
- `ProtectSystem=strict`, `ProtectHome=true`, `NoNewPrivileges=true`; solo `/run/openplayer` es escribible.

Orden recomendado:

- Arrancar MPD.
- Arrancar OpenPlayer.Service.
- Arrancar OpenPlayer Hardware Agent.

El agente debe poder arrancar aunque el servicio no esté disponible y reintentar sin bloquear el loop de GPIO. El servicio C# debe sobrevivir a una desconexión de MPD.

Consultar logs con:

```bash
systemctl status openplayer
journalctl -u openplayer -b --no-pager
journalctl -u openplayer-hardware -b --no-pager
```

Los nombres definitivos de unidades deben coincidir con los archivos en `deploy/`.

## 10. Bluetooth A2DP (fase posterior)

No implementar Bluetooth hasta que la salida DAC USB sea estable.

1. Comprobar que Bluetooth está habilitado y que los auriculares admiten A2DP.
2. Elegir y configurar el stack de audio compatible con la versión de Raspberry Pi OS (por ejemplo PipeWire/WirePlumber si está soportado).
3. Emparejar y conectar los auriculares.
4. Confirmar que la salida aparece en el servidor de audio.
5. Configurar MPD para usar la salida adecuada.
6. Probar cambio de salida, reconexión tras desconexión y volumen.

Los paquetes y comandos de emparejamiento pueden variar por versión. No copiar una receta de otra versión sin comprobar servicios y logs. No exponer servicios de audio a redes no confiables.

## 11. Pantalla redonda GC9A01 (SPEC 17)

Módulo de 1,28" 240x240 ("1.28 TFT ver 1.0", 7 pines, sin BL). La dibuja el hardware agent con el estado de `player.subscribe`; no mantiene un estado de reproducción paralelo ni habla con MPD.

1. Con la Pi apagada, cablear según `gpio-map.md` §10 (VCC a 3.3 V, pin 17; nunca a 5 V). Verificar el pinout serigrafiado del módulo.
2. Encender y activar SPI: `sudo raspi-config nonint do_spi 0`. Comprobar: `ls /dev/spidev0.0`.
3. Paquetes: `python3-pil`, `python3-spidev` y `fonts-dejavu-core` (§8; `install.sh` los verifica).
4. En `/opt/openplayer/player.json`, poner `hardware.display.enabled` en `true` (el resto de la sección trae los valores del cableado de §10).
5. `sudo systemctl restart openplayer-hardware` y `journalctl -u openplayer-hardware -b -f`: debe aparecer `display ready (spi0.0, 40000000 Hz)`.
6. Prueba: con música, la pantalla muestra ícono de estado, título, artista, álbum, `m:ss / -m:ss`, `n / total` y anillo de progreso. `mpc next`, `mpc volume 40` (anillo azul y número 2 s) y play/pausa se reflejan en menos de 1 s. `sudo systemctl stop openplayer` → "Sin conexión"; al volver, la pista.
7. Modos (SPEC 18, 19): `menu` cicla pista → reloj → carátula en menos de 1 s; la carátula aparece en menos de 1,5 s (antes, ♪ y el título). En pausa 60 s (`idleClockSeconds`) aparece el reloj solo. Para probar el ahorro, poner `nightStart`/`nightEnd` alrededor de la hora actual o `offAfterStoppedMinutes: 1` con `mpc stop`: el panel queda negro y un botón lo enciende 10 s.

La Pi no tiene RTC: sin red, la hora del reloj (y el horario nocturno) es incorrecta hasta que NTP sincroniza. Se corrige sola, sin reiniciar el agente. Comprobar con `timedatectl` (`System clock synchronized: yes`).

Si falla, el log muestra `display init failed: <motivo>` y los botones siguen funcionando:

| Síntoma | Causa probable |
|---|---|
| `No such file or directory` en el init | SPI apagado (paso 2) |
| `Permission denied` | La unidad no tiene el grupo `spi`; volver a desplegar |
| `No module named 'spidev'` o `'PIL'` | Falta un paquete (paso 3) |
| `cannot open resource` | Falta `fonts-dejavu-core` |
| Pantalla negra sin error | Revisar cableado de DC, RST, CS y VCC; medir continuidad entre pines vecinos del header (un corto RST–GND la deja en reset) |
| Imagen que se desvanece a blanco | Alimentación o RST inestable: contacto flojo o corto en VCC, GND o RST |
| Modo carátula siempre con ♪ | La pista no tiene imagen incrustada ni `cover.jpg`; ver `cover:` en `journalctl -u openplayer-hardware` (`cover too large` = más de 2 MB) |
| Basura o parpadeo | Bajar `spiHz` (p. ej. 20000000) |
| Imagen girada | Ajustar `rotation` (0, 90, 180, 270) |
| Colores invertidos o espejados | Ajustar `MADCTL` (0x36) o `INVON` en `gc9a01.py` y documentarlo |
| Reloj con hora equivocada | Sin NTP todavía (ver arriba) o zona horaria: `sudo timedatectl set-timezone <Zona>` |
| No vuelve a encenderse tras el ahorro | El módulo no responde a `DISPON` solo: rehacer `init()` en `wake_display()` (`gc9a01.py`) |
| Mucha CPU con títulos largos | El desplazamiento dibuja 5 fps (~14 % de un núcleo en la Pi Zero 2 W); subir `SCROLL_TICK` en `display.py` para menos |

## 12. Integración de batería y carcasa

Seguir `battery-design.md`. No imprimir la carcasa definitiva antes de medir DAC, conectores, batería y módulo de alimentación. En prototipo, fijar cables y evitar que la placa o batería se muevan. La carcasa debe permitir acceso a microSD, carga, interruptor y conectores; no comprimir ni perforar la batería.

## 13. Plan de pruebas de aceptación

- [ ] Arranque desde microSD sin monitor.
- [ ] SSH funciona después de reiniciar.
- [ ] DAC aparece en ALSA.
- [ ] MP3 reproduce y pausa correctamente.
- [ ] FLAC reproduce correctamente.
- [ ] Biblioteca MPD se actualiza y lista archivos.
- [ ] Servicio C# se conecta a MPD y devuelve snapshot.
- [ ] Los botones generan un solo evento por pulsación.
- [ ] La pantalla (si está montada) muestra la pista actual y "Sin conexión" con el Service detenido.
- [ ] `menu` alterna pista ↔ reloj; el ahorro nocturno o por inactividad apaga y un botón enciende (si se configuró).
- [ ] El servicio se recupera tras reiniciar MPD.
- [ ] El agente reconecta después de reiniciar C#.
- [ ] Los logs son accesibles por journalctl.
- [ ] Bluetooth funciona sin romper DAC USB.
- [ ] La alimentación portátil supera prueba de carga y autonomía.
- [ ] Apagado ordenado probado antes de usar batería integrada (▶︎ 3 s; `journalctl -b -1` termina en `Reached target poweroff`).

## 14. Solución de problemas

### No se oye audio

- Ejecutar `aplay -l` y confirmar que el DAC aparece.
- Revisar `journalctl -u mpd -b`.
- Verificar el bloque `audio_output` de MPD y permisos.
- Confirmar que el volumen no está en cero y que el DAC/auriculares funcionan en otro equipo.

### MPD: `Failed to open ALSA device "hw:N,0"`

Aparece en `mpc status` o `journalctl -u mpd -b`, y los botones registran `Button Next failed: … Not playing`. Causa: el `device` de `audio_output` usa un índice y el DAC cambió de número (p. ej. pasó a `card 0` y `hw:1,0` ahora es HDMI). Solución: usar el id de la tarjeta, `hw:CARD=<id>,DEV=0` (§4–5), y `sudo systemctl restart mpd`.

### Samba rechaza las credenciales

- El usuario es `andres` y la contraseña es la de `smbpasswd`, no la de SSH. Rehacerla con `sudo smbpasswd -a andres`.
- Windows reutiliza una sesión previa con otras credenciales: `net use \\mpi3-player.local\music /delete` en `cmd` y volver a abrir la ruta.
- `Acceso denegado` o `System error 64` sin pedir contraseña: la IP del equipo no está en `hosts allow` (`sudo journalctl -u smbd -b`). Windows suele conectar por IPv6 link-local (`fe80::…`) al usar `.local`; por eso `fe80::/10` va en la lista.
- La ruta no se encuentra: probar `\\<IP de la Pi>\music` (`hostname -I`); si funciona, el problema es la resolución mDNS de `.local`.

### Archivo copiado por Samba que no aparece en `mpc listall`

- Confirmar `auto_update "yes"` en `/etc/mpd.conf` y que MPD se reinició después.
- Permisos: `ls -l ~/Music/...` debe mostrar lectura para otros (`-rw-rw-r--`, carpetas `drwxrwxr-x`); si no, revisar `create mask` y `directory mask` de `[music]`.
- Formato no soportado o archivo copiado a medias: `journalctl -u mpd -b` y forzar con `mpc update`.
- Errores `inotify` en el log de MPD: subir `fs.inotify.max_user_watches` con `sysctl`.

### Tras actualizar el paquete `mpd`

Si `apt` pregunta si reemplazar `/etc/mpd.conf`, conservar la versión local (opción por defecto `N`): la del paquete no trae el `audio_output` del DAC. Después de actualizar, revisar el bloque con `grep -A5 '^audio_output' /etc/mpd.conf`.

### MPD no puede leer música

- Confirmar la ruta exacta en `music_directory`.
- Verificar permisos de recorrido (`x`) en directorios y lectura (`r`) de archivos para el usuario de MPD.
- Revisar errores de actualización de biblioteca en logs.

### El botón no responde

- Confirmar GPIO BCM vs número físico.
- Revisar GND común, pull-up, debounce y biblioteca GPIO.
- Ejecutar un script aislado antes de depurar IPC.

### El socket no conecta

- Confirmar que el listener C# está activo.
- Revisar existencia/permisos de `/run/openplayer`.
- Confirmar usuario y grupo de ambos servicios.
- Comprobar que los mensajes terminan en newline y que el servidor procesa mensajes parciales.

### La Pi se reinicia al conectar el DAC

- Desconectar batería/carga experimental y volver a fuente estable.
- Comprobar fuente, cableado y adaptador OTG.
- Medir tensión bajo carga; no asumir que una fuente rotulada 5 V mantiene esa tensión en el dispositivo.

## 15. Reglas para LLMs

Ejecutar un cambio a la vez. Antes de recomendar comandos destructivos o que requieren `sudo`, explicar qué modifican. No sobrescribir configuraciones del sistema sin inspeccionarlas. No inventar el modelo de DAC, usuario Linux, IP, salida ALSA o módulo de batería. Solicitar la salida de comandos de diagnóstico cuando falte información. Actualizar los criterios de aceptación cuando se añadan funciones.
