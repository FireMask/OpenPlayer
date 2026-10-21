# SPEC 07 — Carpeta compartida Samba para importar música

> **Status:** Implemented
> **Depends on:** SPEC 06
> **Date:** 2026-10-20
> **Objective:** Documentar cómo compartir `/home/andres/Music` por Samba (`\\mpi3-player.local\music`, usuario `andres`, solo redes privadas) con `auto_update` de MPD, para que copiar archivos desde el Explorador de Windows los agregue a la biblioteca sin SSH.

## Scope

**In:**

- `docs/assembly.md`, nueva sección "Importar música por Samba":
  - `sudo apt install samba` (sin `wsdd`) y `sudo systemctl disable --now nmbd`.
  - Bloque `[music]` en `/etc/samba/smb.conf`: `path = /home/andres/Music`, `valid users = andres`, `read only = no`, `create mask = 0664`, `directory mask = 0775` (legibles por `mpd`).
  - En `[global]`: `hosts allow = 127. 10. 172.16.0.0/12 192.168. ::1 fe80::/10`, `hosts deny = ALL`, `server min protocol = SMB2`.
  - `sudo smbpasswd -a andres` (contraseña propia de Samba).
  - `auto_update "yes"` en `/etc/mpd.conf`.
  - `mkdir ~/Playlists` (corrige el error de MPD; no se comparte).
  - Uso desde Windows: abrir `\\mpi3-player.local\music` y, opcional, conectar como unidad.
- `docs/assembly.md` §14: problemas típicos (credenciales, archivo copiado que no aparece en `mpc listall`).
- README: una línea que apunte a la sección.
- Validación en la Pi (`mpi3-player`) desde Windows.

**Out of scope (for future specs):**

- Script de instalación o cambios en `install.sh`.
- `wsdd`/`wsdd2` (visible en "Red" de Windows).
- Compartir `~/Playlists`; biblioteca y playlists (fase 5).
- Mover la biblioteca a otra ruta o a un USB.
- Acceso fuera de la red local.

## Data model

No aplica: solo documentación y configuración del sistema en la Pi (`/etc/samba/smb.conf`, `/etc/mpd.conf`).

## Implementation plan

1. `docs/assembly.md`, nueva sección "Importar música por Samba": instalación, `nmbd` deshabilitado, bloques `[global]`/`[music]`, `smbpasswd`, `auto_update`, `~/Playlists` y uso desde Windows. README: una línea que apunte a ella.
2. `docs/assembly.md` §14: problemas de credenciales y de archivo copiado que no aparece en la biblioteca.
3. Validación en la Pi siguiendo la sección: instalar y configurar; `testparm -s` sin errores; desde Windows copiar un archivo a `\\mpi3-player.local\music` y verlo en `mpc listall` sin `mpc update`; reproducirlo; borrarlo desde Windows y verlo desaparecer; `sudo reboot` y el recurso sigue accesible. La contraseña Samba la elige el usuario y no se guarda en el repo.

## Acceptance criteria

**Documentación:**

- [x] `assembly.md` tiene la sección "Importar música por Samba" con: `apt install samba`, bloques `[global]` y `[music]` exactos, `smbpasswd -a andres`, `auto_update "yes"`, `mkdir ~/Playlists` y la ruta `\\mpi3-player.local\music`.
- [x] `assembly.md` §14 cubre credenciales rechazadas y archivo que no aparece en `mpc listall`.
- [x] README apunta a la sección.

**Raspberry Pi:**

- [x] `testparm -s` termina sin errores y muestra `[music]` con `valid users = andres`.
- [x] `systemctl is-active smbd` → `active`; `nmbd` y `wsdd` no están activos.
- [x] Desde Windows, sin credenciales no se puede abrir el recurso; con `andres` y la contraseña Samba sí.
- [x] Un archivo copiado desde Windows aparece en `mpc listall` en 10 s o menos, sin `mpc update`, y `mpc play` lo reproduce.
- [x] El archivo copiado queda con permisos `-rw-rw-r--` y una carpeta copiada con `drwxrwxr-x`.
- [x] Borrarlo desde Windows lo quita de `mpc listall` en 10 s o menos.
- [x] `~/Playlists` existe y `journalctl -u mpd -b` no tiene `Failed to access /home/andres/Playlists`.
- [x] Tras `sudo reboot`, `\\mpi3-player.local\music` sigue accesible y `auto_update` sigue funcionando.
- [x] `dotnet test` y `pytest tests/hardware-agent` siguen pasando (sin cambios de código).

## Decisions

**Tomadas:**

- **Solo documentación, sin script.** Igual que SPEC 06: configuración única del SO por Pi; `smbpasswd` es interactivo.
- **Compartir `/home/andres/Music` tal cual.** Ya es el `music_directory` de MPD y `mpd` lo lee; mover la biblioteca no aporta.
- **Usuario `andres` con contraseña Samba propia, sin invitado.** Escritura en la biblioteca solo con credenciales.
- **`hosts allow` por rangos privados + `server min protocol = SMB2`.** No depende de la subred del router de hoy; bloquea SMB1 y cualquier IP pública. Incluye `::1` y `fe80::/10` (IPv6 link-local, no enrutable): Windows resuelve `mpi3-player.local` primero a la dirección `fe80::` y sin ella Samba corta la conexión (error 64; hallado al validar).
- **`create mask 0664` / `directory mask 0775`.** Lo que se copia queda legible para `mpd` sin tocar permisos a mano.
- **`auto_update "yes"`.** MPD vigila la carpeta con inotify; lo copiado aparece sin SSH.
- **Acceso por ruta (`\\mpi3-player.local\music`), `nmbd` deshabilitado y sin `wsdd`.** Windows resuelve `.local` por mDNS; menos servicios en la Zero.
- **`~/Playlists` se crea pero no se comparte.** Corrige el error de MPD; las playlists son de la fase 5.

**Descartadas:**

- **Acceso de invitado.** Cualquiera en la red podría borrar la biblioteca.
- **Script `deploy/setup-samba.sh` o pasos en `install.sh`.** Ver arriba.
- **WinSCP / script scp.** Funcionan sin servicio nuevo, pero arrastrar en el Explorador es más cómodo para uso diario.
- **Syncthing.** Pesado para 512 MB de RAM.

## Risks

- **inotify en tarjeta SD.** `auto_update` falla si se supera `fs.inotify.max_user_watches` (una por carpeta). Con el valor por defecto de Debian (decenas de miles) sobra para una biblioteca personal; si MPD registra `inotify` errors, subirlo con `sysctl`.
- **Copia parcial.** MPD puede indexar un archivo grande antes de que termine de copiarse; al terminar, inotify dispara otra actualización. Si queda mal indexado, `mpc update` lo corrige.
- **Escritura en la SD.** Copias frecuentes desgastan la tarjeta; aceptable para una biblioteca que cambia poco.
- **Contraseña Samba débil.** Cualquiera en la red local podría borrar música. Mitigación: contraseña propia y solo rangos privados.
- **Memoria.** `smbd` usa ~20 MB en reposo y más durante copias; con ~245 MB libres alcanza, pero no copiar mientras se compila o se depura en la Pi.
