# Assembly & Deployment — OpenPlayer

**Estado:** guía de montaje incremental. Los comandos pueden variar según la versión de Raspberry Pi OS y los paquetes disponibles.

## 1. Alcance

Este documento lleva desde una Raspberry Pi Zero 2 W recién preparada hasta un prototipo con reproducción por DAC USB, control por SSH y botones GPIO. OLED, Bluetooth y batería integrada se incorporan después.

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

Publicar para la Pi (ARM64), autocontenido (decisión de SPEC 02: no requiere instalar el runtime de .NET en la Pi):

```bash
dotnet publish src/OpenPlayer.Service -c Release -r linux-arm64 --self-contained true -o publish/linux-arm64
scp -r publish/linux-arm64 <usuario>@openplayer.local:~/openplayer
```

La carpeta incluye `player.json` (copia de `config/player.example.json`); editarla en la Pi si MPD no está en `127.0.0.1:6600`. Confirmar la arquitectura con `uname -m` (`aarch64`) antes de desplegar. Si se prefiere un runtime compartido, `--self-contained false` requiere instalar .NET 10 en la Pi.

Desde Windows, `.\deploy.ps1 -Device <host> -User <usuario>` hace publish, copia e instalación en un paso.

Prueba manual por SSH. El Service escucha en `/run/openplayer/hardware.sock`; hasta tener la unidad systemd (`RuntimeDirectory`), crear el directorio a mano. Explicación: `mkdir` en `/run` requiere `sudo`, y `chown` deja al usuario actual como dueño para que el Service corra sin root. `/run` es tmpfs: el directorio desaparece al reiniciar y hay que repetirlo.

```bash
sudo apt install -y socat
sudo mkdir -p /run/openplayer && sudo chown $USER /run/openplayer
~/openplayer/OpenPlayer.Service
# en otra sesión SSH:
echo '{"type":"player.get_snapshot"}' | socat - UNIX-CONNECT:/run/openplayer/hardware.sock
```

Comparar el `player.snapshot` con `mpc current`; más mensajes en `README.md`. Si `volume` sale `null`, el `audio_output` de MPD no tiene mixer: añadir `mixer_type "software"` si se quiere controlar volumen.

## 8. Agente Python y GPIO

Instalar/configurar la biblioteca GPIO compatible con el sistema. Probar un botón a la vez con un script mínimo. Usar los GPIO BCM documentados en `gpio-map.md` y pull-up interno. No conectar botones a 3.3 V; el esquema previsto es GPIO ↔ botón ↔ GND.

Implementar el agente en este orden:

1. Lectura GPIO y debounce.
2. Conversión a nombres de evento.
3. Cliente Unix socket con mensajes JSON Lines.
4. Reintentos y logs.
5. Integración con el servicio C#.
6. Más adelante, OLED y visualización de snapshots.

## 9. Socket Unix y systemd

El socket `/run/openplayer/hardware.sock` requiere que el servicio cree un listener. Configurar `RuntimeDirectory=openplayer` en la unidad systemd, con usuario/grupo y permisos mínimos. Ambos procesos deben compartir un grupo dedicado para la comunicación. No dar acceso global al socket.

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

## 11. OLED (fase posterior)

1. Verificar el módulo SSD1306 exacto, tensión y pinout.
2. Habilitar I²C.
3. Conectar SDA a GPIO2/pin físico 3 y SCL a GPIO3/pin físico 5.
4. Verificar la dirección I²C detectada.
5. Implementar `oled.py` como adaptador independiente.
6. La pantalla muestra datos recibidos del servicio; no mantiene un estado de reproducción paralelo.

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
- [ ] El servicio se recupera tras reiniciar MPD.
- [ ] El agente reconecta después de reiniciar C#.
- [ ] Los logs son accesibles por journalctl.
- [ ] Bluetooth funciona sin romper DAC USB.
- [ ] La alimentación portátil supera prueba de carga y autonomía.
- [ ] Apagado ordenado probado antes de usar batería integrada.

## 14. Solución de problemas

### No se oye audio

- Ejecutar `aplay -l` y confirmar que el DAC aparece.
- Revisar `journalctl -u mpd -b`.
- Verificar el bloque `audio_output` de MPD y permisos.
- Confirmar que el volumen no está en cero y que el DAC/auriculares funcionan en otro equipo.

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
