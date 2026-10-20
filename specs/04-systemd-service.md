# SPEC 04 — Servicio systemd para OpenPlayer

> **Status:** Approved
> **Depends on:** SPEC 03
> **Date:** 2026-10-20
> **Objective:** Instalar `OpenPlayer.Service` como unidad systemd en `/opt/openplayer` con el usuario de sistema `openplayer`, desplegada con un solo comando desde Windows (`deploy.ps1`), para que arranque sola con la Pi y el socket exista siempre.

## Scope

**In:**

- `deploy/install.sh` (bash, idempotente, corre con sudo en la Pi):
  - crea el grupo y el usuario de sistema `openplayer` si faltan (sin shell ni home) y añade al usuario que despliega al grupo `openplayer`;
  - extrae el publish en `/opt/openplayer` y conserva el `player.json` existente;
  - deja los archivos con dueño `root` y legibles por `openplayer`;
  - instala `deploy/openplayer.service` en `/etc/systemd/system/`, y luego hace `daemon-reload`, `enable` y `restart`;
  - muestra `systemctl is-active` y termina con código distinto de 0 si la unidad no queda activa.
- `deploy/openplayer.service`:
  - `Requires=` pasa a `Wants=mpd.service`, manteniendo `After=`;
  - se quita `/var/lib/openplayer` de `ReadWritePaths`;
  - `RuntimeDirectoryMode=0770`;
  - límite de reinicios con `StartLimitIntervalSec=60` y `StartLimitBurst=5`.
- `deploy.ps1`:
  - compila y copia a `/tmp` de la Pi el `.tgz`, `install.sh` y `openplayer.service`;
  - corre `sudo bash install.sh`: con `-Password` usa `sudo -S`; sin él, `ssh -t` para que sudo pida la contraseña;
  - deja de instalar en `~/openplayer`.
- Documentación:
  - README: desplegar, `systemctl` y `journalctl`, y detener la unidad antes de ejecutar a mano;
  - `assembly.md` §7 y §9: instalación con systemd, y nota de que `~/openplayer` y el `mkdir /run/openplayer` manual ya no se usan;
  - `architecture.md`: §7 (quién crea `/run/openplayer`) y §13 (fase de systemd hecha).
- Verificación en la Pi, incluido un reinicio.

**Out of scope (para futuras specs):**

- `openplayer-hardware.service` y el agente Python (no se toca ni se instala).
- Aplicar `initialVolume` y `resumePlaybackOnBoot` al arrancar.
- Mover la config a `/etc/openplayer`.
- `/var/lib/openplayer` y cualquier estado persistente.
- Desinstalación automática (`uninstall.sh`).
- Borrar `~/openplayer`; se documenta como paso manual.
- Notificación de systemd (`Type=notify`, `UseSystemd()`) y watchdog.
- Rotación o límites de logs más allá de lo que hace journald.

## Data model

Esta spec no añade estructuras de código. Define la disposición de archivos, la unidad y la interfaz de los scripts.

Archivos:

```text
deploy/
  install.sh            // nuevo: instala en la Pi (sudo, idempotente)
  openplayer.service    // modificado
deploy.ps1              // modificado: copia a /tmp e invoca install.sh
```

En la Pi, después de instalar:

```text
/opt/openplayer/                 root:root 0755, publish completo
/opt/openplayer/player.json      root:root 0644, se conserva entre deploys
/opt/openplayer/OpenPlayer.Service   0755
/etc/systemd/system/openplayer.service
/run/openplayer/                 openplayer:openplayer 0770 (lo crea systemd)
/run/openplayer/hardware.sock    0660 (lo crea el Service)
usuario openplayer               sistema, sin login, grupo openplayer
grupo openplayer                 miembros: <usuario que despliega>
```

`deploy/openplayer.service`:

```ini
[Unit]
Description=OpenPlayer Control Service
After=network.target mpd.service
Wants=mpd.service
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=openplayer
Group=openplayer
WorkingDirectory=/opt/openplayer
RuntimeDirectory=openplayer
RuntimeDirectoryMode=0770
ExecStart=/opt/openplayer/OpenPlayer.Service
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/run/openplayer

[Install]
WantedBy=multi-user.target
```

Interfaz de `install.sh`:

```text
sudo bash install.sh <ruta.tgz> <unit.service> <usuario-que-despliega>
```

- Exit 0 si la unidad queda `active`; si no, exit distinto de 0 e imprime las últimas líneas de `journalctl -u openplayer`.
- Correrlo dos veces seguidas da el mismo resultado: sin errores ni usuarios o grupos duplicados.

Flujo de `deploy.ps1` (mismos parámetros que hoy: `-Device`, `-User`, `-Password`):

```text
1. dotnet publish → publish/linux-arm64
2. tar → %TEMP%\openplayer.tgz
3. scp openplayer.tgz, deploy/install.sh, deploy/openplayer.service → /tmp/openplayer-deploy/
4. ssh: sudo bash /tmp/openplayer-deploy/install.sh … ; rm -r /tmp/openplayer-deploy
   con -Password: la contraseña va por stdin a sudo -S
   sin -Password: ssh -t, sudo la pide en la terminal
```

## Implementation plan

1. Actualizar `deploy/openplayer.service`:
   - `Wants=` en lugar de `Requires=`;
   - `StartLimitIntervalSec=60` y `StartLimitBurst=5`;
   - `RuntimeDirectoryMode=0770`;
   - `ReadWritePaths` sin `/var/lib/openplayer`.

   Verificar en la Pi con `systemd-analyze verify` sobre una copia en `/tmp`: sin errores.
2. Crear `deploy/install.sh` (con `set -euo pipefail`). En orden:
   - validar los argumentos;
   - crear el grupo y el usuario `openplayer` si faltan (`useradd --system --no-create-home --shell /usr/sbin/nologin`);
   - añadir al usuario que despliega al grupo (`usermod -aG`);
   - extraer en `/opt/openplayer` sin pisar un `player.json` existente;
   - fijar dueño y permisos;
   - instalar la unidad, hacer `daemon-reload`, `enable` y `restart`;
   - esperar a que la unidad quede `active`; si no, mostrar `journalctl` y salir con error.

   Verificar en la Pi copiando a mano el `.tgz` actual: dos corridas seguidas terminan en `active`.
3. Actualizar `deploy.ps1`:
   - copiar los 3 archivos a `/tmp/openplayer-deploy/`;
   - invocar `install.sh` con `sudo -S` (con `-Password`) o con `ssh -t` (sin él);
   - limpiar `/tmp/openplayer-deploy`;
   - quitar la lógica de `~/openplayer`.

   Verificar desde Windows: `deploy.ps1 -Password …` termina con exit 0 y la unidad queda `active`.
4. Actualizar la documentación:
   - README "Publicar para la Raspberry Pi" y "Ejecutar el Service" (`systemctl`, `journalctl`, detener la unidad antes de ejecutar a mano, sin `mkdir` manual);
   - `assembly.md` §7 y §9;
   - `architecture.md` §7 (`/run/openplayer` lo crea systemd) y §13.
5. Verificar en la Pi (criterios manuales), incluido un reinicio.

Antes de la verificación de los pasos 2 y 3 hay que detener cualquier `~/openplayer/OpenPlayer.Service` que siga corriendo, para que no compita por el socket.

## Acceptance criteria

**Repositorio:**

- [ ] `deploy/openplayer.service` usa `Wants=mpd.service` (no `Requires=`), tiene `StartLimitIntervalSec=60`, `StartLimitBurst=5` y `RuntimeDirectoryMode=0770`, y no menciona `/var/lib/openplayer`.
- [ ] `systemd-analyze verify` sobre la unidad no reporta errores (se corre en la Pi).
- [ ] `deploy.ps1` ya no menciona `~/openplayer`.
- [ ] `dotnet build` y `dotnet test` siguen pasando (sin cambios de código C#).

**Raspberry Pi (manual):**

- [ ] `.\deploy.ps1 -Device mpi3-player.local -User andres -Password …` termina con exit 0 y la unidad queda `active`.
- [ ] Correr `deploy.ps1` dos veces seguidas termina con exit 0 ambas veces, sin duplicar el usuario ni el grupo.
- [ ] `id openplayer` muestra un usuario de sistema (uid < 1000) con shell `nologin`, y `andres` pertenece al grupo `openplayer`.
- [ ] `/opt/openplayer` es de `root`; si se edita `player.json` en la Pi, conserva el cambio tras otro deploy.
- [ ] `ps -o user= -C OpenPlayer.Service` muestra `openplayer`.
- [ ] `/run/openplayer` es `openplayer:openplayer` con permisos `drwxrwx---`, y el socket es `srw-rw----`.
- [ ] Desde una sesión nueva de `andres`, `echo '{"type":"player.get_snapshot"}' | socat - UNIX-CONNECT:/run/openplayer/hardware.sock` devuelve un `player.snapshot`.
- [ ] `journalctl -u openplayer -b` muestra `Listening on /run/openplayer/hardware.sock`.
- [ ] `sudo systemctl restart mpd` no reinicia el Service (el `MainPID` no cambia), y la siguiente consulta funciona.
- [ ] `sudo kill -9 <MainPID>` hace que systemd lo reinicie a los ~3 s.
- [ ] Con `maxMessageBytes: 10` en `/opt/openplayer/player.json`, la unidad termina en `failed` después de 5 intentos, sin reintentar indefinidamente. Se restaura el valor y se vuelve a arrancar.
- [ ] Después de `sudo reboot`, sin intervención manual, la unidad está `active` y `socat` responde.

**Documentación:**

- [ ] El README explica cómo desplegar, `systemctl status|restart|stop openplayer` y `journalctl -u openplayer`, y que hay que detener la unidad antes de ejecutarlo a mano.
- [ ] `assembly.md` §7 y §9 describen la instalación con systemd y que `~/openplayer` y el `mkdir` manual ya no se usan.
- [ ] `architecture.md` §7 indica que `/run/openplayer` lo crea systemd, y §13 marca la fase de systemd.

## Decisions

- **Sí:** usuario de sistema `openplayer` sin login ni home. Si el Service falla, no tiene acceso a archivos personales, y `ProtectHome=true` funciona.
- **No:** correr como `andres`. Es más simple, pero el Service tendría acceso a todo lo del usuario.
- **Sí:** binario y `player.json` juntos en `/opt/openplayer`. Sin cambios de código; `ProtectSystem=strict` lo deja de solo lectura para el Service, que solo lo lee.
- **No:** `/etc/openplayer/player.json`. Requiere un flag o variable para la ruta y lógica extra en el deploy; se reconsidera si aparece una pantalla de configuración que escriba.
- **Sí:** `deploy.ps1` invoca `install.sh` con sudo. Un solo comando compila, despliega y reinicia; el script idempotente sirve también para la primera instalación.
- **No:** instalación manual de una vez más un deploy que solo copia. Igual se necesita sudo para `/opt` y para el restart, y serían dos procedimientos que mantener.
- **Sí:** `install.sh` en bash y versionado en `deploy/`. La lógica de la Pi vive en la Pi; `deploy.ps1` solo transporta.
- **Sí:** con `-Password`, `sudo -S` por stdin; sin él, `ssh -t`. Funciona igual sin configurar sudo `NOPASSWD`.
- **Sí:** grupo `openplayer` con `RuntimeDirectoryMode=0770`, y el usuario que despliega en el grupo. El agente futuro corre como `openplayer`, y `socat` de diagnóstico funciona sin sudo.
- **Sí:** `Wants=mpd.service` en lugar de `Requires=`. Con `Requires=`, reiniciar MPD reinicia también el Service, que ya sobrevive solo a la caída de MPD (SPEC 02).
- **Sí:** `StartLimitIntervalSec=60` con `StartLimitBurst=5`. Un `player.json` inválido termina en `failed` en vez de reintentar cada 3 s para siempre.
- **No:** `RestartPreventExitStatus=1`. El exit 1 también cubre fallos del host que pueden ser transitorios.
- **Sí:** quitar `/var/lib/openplayer` de `ReadWritePaths`. Nada escribe ahí (YAGNI); además, systemd falla si la ruta no existe.
- **No:** `Type=notify` y `UseSystemd()`. Requiere el paquete NuGet `Microsoft.Extensions.Hosting.Systemd`; `Type=simple` basta mientras nada dependa de que el socket esté listo.
- **No:** instalar `openplayer-hardware.service`. El agente no existe; va en su spec.
- **No:** `initialVolume` al arrancar. MPD puede no estar listo en el boot y hacerlo bien requiere reintentos; va en otra spec.
- **Sí:** conservar `player.json` existente. Los ajustes hechos en la Pi sobreviven a los deploys.
- **No:** borrar `~/openplayer` automáticamente. El script no toca el home; se documenta como paso manual.

## Risks

| Riesgo | Mitigación |
|---|---|
| La contraseña de sudo pasa por `-Password` y queda en el historial de PowerShell. | Ya pasa con SSH; se documenta. Para evitarlo: `ssh-copy-id` y omitir `-Password` (sudo la pide por `ssh -t`). |
| `usermod -aG openplayer andres` no aplica a las sesiones SSH ya abiertas; `socat` da "Permission denied". | Se documenta: abrir una sesión nueva. El criterio usa explícitamente una sesión nueva. |
| Un `~/openplayer/OpenPlayer.Service` manual sigue corriendo y compite por el socket: el segundo borra el socket del primero. | Detenerlo antes de verificar. `install.sh` no lo mata (no toca procesos del usuario). |
| `ProtectSystem=strict` o `ProtectHome=true` impiden algo que .NET necesita (p. ej. escribir en `/tmp` o en `~/.dotnet`). | `ProtectSystem=strict` deja `/tmp` escribible. Si .NET falla, el `journalctl` del criterio lo muestra; se ajusta con `Environment=DOTNET_…` o `ReadWritePaths`, documentando la decisión. |
| `systemctl restart` durante un deploy corta la música si el Service estaba atendiendo un botón. | Aceptado: el deploy es una acción manual de desarrollo. MPD sigue reproduciendo; solo se cortan los botones unos segundos. |
| Una extracción a medias deja `/opt/openplayer` con archivos mezclados si el tar falla. | `set -euo pipefail` corta antes del restart; el siguiente deploy sobrescribe todo. Sin staging atómico (YAGNI). |
| Reiniciar la Pi corta la sesión y la verificación depende de que vuelva la red. | Esperar a que `mpi3-player.local` responda a ping antes de verificar; si no vuelve, revisar con monitor. |

## What is **not** in this spec

- `openplayer-hardware.service` y el agente Python.
- `initialVolume` / `resumePlaybackOnBoot` al arrancar.
- Config en `/etc/openplayer`.
- Estado persistente en `/var/lib/openplayer`.
- `uninstall.sh`.
- Borrar `~/openplayer` automáticamente.
- `Type=notify` y watchdog.
- Rotación de logs.

Cada uno de estos, si llega, va en su propia spec.
