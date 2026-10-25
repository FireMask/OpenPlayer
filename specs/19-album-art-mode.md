# SPEC 19 — Modo carátula en la pantalla redonda

**Estado:** Implemented
**Depende de:** SPEC 16 (player.subscribe), SPEC 17 (pantalla GC9A01), SPEC 18 (modos de pantalla)
**Fecha:** 2026-10-24

**Objetivo:** Agregar a la pantalla redonda un tercer modo, `art`, que muestre la carátula de la pista actual (incrustada en el archivo o `cover.jpg` de la carpeta) recortada en círculo dentro del anillo de progreso, pedida al Service con un nuevo `player.get_cover`.

## Alcance

### Entra
- **Service, MPD:** `MpdClient` aprende a leer respuestas binarias (`binary: N` seguido de N bytes). Hay un método nuevo para la carátula de la pista actual:
  1. Pide `readpicture "<uri>" <offset>` en trozos hasta completar la imagen.
  2. Si no hay imagen incrustada, prueba `albumart "<uri>" <offset>` (`cover.jpg`/`.png` de la carpeta).
  3. Si tampoco hay, la pista no tiene carátula.
- **Service, IPC:** una petición nueva, `player.get_cover`, sin parámetros, para la pista actual.
  - Responde una línea `player.cover` con `songId`, `mime` y `data` en base64, o con `data: null` si no hay carátula.
  - Si la imagen pasa de 2 MB responde `error` con `cover too large`, y si MPD falla, el `error` de siempre.
- **Service, modos:** `displayMode` gana `"art"`, y `menu` alterna track → clock → art → track.
- **Agente:**
  - **Cuándo pide:** solo en modo `art`, al entrar a ese modo o cuando cambia el álbum o el artista. Usa una conexión corta aparte de la suscripción.
  - **Tratamiento de la imagen:**
    - la decodifica con Pillow, usando `draft` en los JPEG;
    - la escala a 228×228 y la recorta en círculo;
    - guarda en memoria solo la última.
  - **Dibujo:**
    - la carátula llena el círculo dentro del anillo de progreso, sin texto;
    - el indicador de volumen se dibuja encima;
    - el reloj automático y el ahorro de pantalla siguen igual.
  - **Placeholder:** un ícono ♪ con el título. Se ve mientras carga, sin carátula, si falla la petición o si la imagen no se puede decodificar.
  - **Reintento:** solo cuando cambia el álbum o el artista, o al volver a entrar al modo `art`.
- **Docs:** `architecture.md` §7 (petición, respuesta y modo nuevos), README y `assembly.md` §11.

### No entra
- La carátula en la página web (otra spec).
- Caché en disco, o más de una carátula en memoria.
- Redimensionar en el Service (sin librerías de imagen nuevas en .NET).
- Pedir la carátula fuera del modo `art`, o adelantar la de la pista siguiente.
- Texto sobre la carátula, desenfoque o fondos de color sacados de la imagen.
- Carátulas por URL o de servicios externos.
- Elegir entre varias imágenes incrustadas: se usa la que devuelve MPD.

## Modelo de datos

### IPC: `player.get_cover` (agente → Service)
```json
{"type":"player.get_cover"}
```
Respuestas, una línea cada una:
```json
{"type":"player.cover","songId":17,"mime":"image/jpeg","data":"/9j/4AAQ..."}
{"type":"player.cover","songId":17,"mime":null,"data":null}
{"type":"player.cover","songId":null,"mime":null,"data":null}
{"type":"error","request":"player.get_cover","message":"cover too large"}
{"type":"error","request":"player.get_cover","message":"MPD did not respond within 3000 ms"}
```
- Los casos son, en orden: hay carátula; la pista no tiene; no hay pista actual; la imagen pasa de 2 MB; MPD falla.
- `data` es la imagen original en base64, sin redimensionar. `mime` viene del campo `type` de MPD; puede ser `null` si MPD no lo informa, y el agente igual intenta decodificar.
- No usa la conexión de `player.subscribe`: el agente abre una conexión, pide, lee una línea y cierra.

### Core / Service (C#)
- `record Cover(int? SongId, string? Mime, byte[]? Data)` en `OpenPlayer.Core.Models`.
- `IPlayer.GetCoverAsync(CancellationToken)` → `Cover`. Con más de `Cover.MaxBytes = 2 * 1024 * 1024` lanza `CoverTooLargeException`, que el Service convierte en `error`.
- `CoverMessage.Serialize(Cover)` en `OpenPlayer.Core.Messages`.
- `MpdClient`:
  - lee respuestas binarias: la línea `binary: N`, después N bytes y un `\n`;
  - `MpdResponse` gana `byte[]? Binary`;
  - la sesión de la carátula envía primero `binarylimit 1048576`, así una imagen de 565 KB llega en un trozo en lugar de unos 70 de 8 KB.
- `MpdPlayer.GetCoverAsync`:
  1. Pide `currentsong` (uri e `Id`).
  2. Repite `readpicture "<uri>" <offset>` hasta juntar `size` bytes.
  3. Si la respuesta viene sin `binary`, prueba `albumart` igual; un `ACK [50]` (no existe) cuenta como sin carátula.
- `IpcServer._displayMode` cicla `"track"` → `"clock"` → `"art"` → `"track"`.

### Agente (Python)
- `View` gana `cover: Image | None` (la imagen ya preparada, 228×228 y circular) y `mode` acepta `"art"`.
  - `View` sigue siendo frozen.
  - ponytail: las comparaciones de `View` comparan la imagen. Como es siempre el mismo objeto cacheado, la comparación por identidad (`is`) alcanza.
- `cover.py`:
  - `fetch_cover(connect) -> bytes | None`: una conexión corta y un límite de línea de 3 MB.
  - `prepare(data: bytes) -> Image | None`: `Image.open`, `draft("RGB", (228, 228))` en JPEG, `ImageOps.fit` a 228×228 y máscara circular. Devuelve `None` si no se puede decodificar.
- Estado en `Display`:
  - `_cover_key: tuple[artist, album] | None`: la clave de la última carátula pedida.
  - `_cover: Image | None`, y `_cover_state` (`"loading" | "ok" | "none"`).
  - La petición corre en un hilo corto aparte, para no frenar el dibujo ni la lectura de la suscripción.
- `screen.render`, modo `art`:
  - con `cover`, pega la imagen centrada dentro del anillo (radio 114);
  - sin `cover`, el placeholder: ♪ a 64 px y el título debajo.

## Plan de implementación

1. **`MpdClient`, respuestas binarias:**
   - `MpdResponse.Binary`.
   - El lector pasa a leer bytes, para manejar `binary: N`.
   - Pruebas con un servidor MPD falso: una respuesta con binario, una sin binario, y que el texto siga igual.
   - Al terminar: el resto del Service no cambia.
2. **`MpdPlayer.GetCoverAsync`:**
   - `binarylimit`, `readpicture` en trozos, `albumart` de respaldo, `ACK [50]` como sin carátula, y el tope de 2 MB.
   - `Cover`, `IPlayer.GetCoverAsync` y `CoverTooLargeException`.
   - Pruebas: incrustada en varios trozos, solo `cover.jpg`, ninguna, sin pista actual y demasiado grande.
3. **IPC `player.get_cover` y el modo `art`:**
   - `CoverMessage`, el caso nuevo en `IpcMessage` y `IpcServer`.
   - `menu` cicla los tres modos.
   - Pruebas de serialización, de respuesta y error, y del ciclo de `menu`.
   - Se actualiza `architecture.md` §7.
4. **Agente, `cover.py`:**
   - `fetch_cover` con el límite de 3 MB y `prepare` (draft, fit y máscara circular).
   - Pruebas: JPEG, PNG, datos corruptos → `None`, `data: null` → `None` y `error` → `None`.
5. **Agente, `screen.py`, modo `art`:**
   - La carátula dentro del anillo y el placeholder ♪ con el título.
   - El indicador de volumen encima.
   - Pruebas de render.
6. **Agente, `display.py`:**
   - `parse` acepta `"art"`.
   - En modo `art`, pide en un hilo aparte cuando cambia la clave (artista, álbum) o al entrar al modo.
   - Placeholder mientras carga o si falla.
   - No pide en los modos track y clock.
   - Pruebas con `FakeService` respondiendo `player.cover`.
7. **Docs y verificación en la Pi:**
   - README y `assembly.md` §11.
   - Medir cuánto tarda en aparecer la carátula de 565 KB (Bad Bunny) y el uso de CPU.
   - Recorrer los criterios en el hardware real.

## Criterios de aceptación

### Service
- [x] `player.get_cover` devuelve la imagen incrustada completa, igual byte a byte a la de `readpicture`, aunque MPD la mande en varios trozos.
- [x] Sin imagen incrustada pero con `cover.jpg`/`.png` en la carpeta, devuelve esa.
- [x] Sin ninguna de las dos devuelve `data: null`, y sin pista actual devuelve `songId: null`.
- [x] Una imagen de más de 2 MB responde `error` con `cover too large`, sin leerla entera.
- [x] Si MPD falla responde `error` y la conexión sigue viva; el resto de las peticiones funciona igual.
- [x] `menu` cicla track → clock → art → track y empuja cada cambio a los suscriptores.
- [x] Las pruebas .NET existentes y las de la web pasan sin cambios.

### Agente
- [x] En modo `art`, con carátula, la imagen llena el círculo dentro del anillo de progreso, sin texto y sin deformarse (recorte centrado).
- [x] Mientras carga, sin carátula, con un `error` o con datos que no se pueden decodificar, se ve el placeholder (♪ con el título); nada falla ni se corta la suscripción.
- [x] Con dos pistas seguidas del mismo álbum y artista, la carátula se pide una sola vez.
- [x] En los modos track y clock no se pide ninguna carátula.
- [x] El indicador de volumen, el reloj automático y el ahorro de pantalla funcionan en modo `art` igual que en los otros.
- [x] Todas las pruebas del hardware-agent pasan, también con las advertencias de obsolescencia tratadas como errores.

### En la Pi Zero 2 W
- [x] Al pasar a `art` con la carátula de 565 KB (Bad Bunny), la imagen aparece en menos de 1,5 s. Medido (2026-10-24): MPD 0,07 s + decodificar 0,26 s (551 KB).
- [x] El modo `art` en reproducción, sin desplazamiento de título, usa menos del 10 % de un núcleo. Medido: 8 %.
- [x] Los álbumes de la biblioteca se ven con su carátula, y las 5 pistas de Adele sin carátula muestran el placeholder.

### General
- [x] La documentación (README, `architecture.md` §7 y `assembly.md` §11) describe la petición y el modo nuevos.

## Decisiones tomadas y descartadas

| Decisión | Alternativa descartada | Por qué |
|---|---|---|
| `readpicture` (incrustada) con respaldo de `albumart` (archivo de la carpeta) | Solo `readpicture` | La biblioteca actual tiene la carátula incrustada; el respaldo cuesta unas líneas y cubre carpetas futuras con `cover.jpg`. |
| Una petición IPC nueva (`player.get_cover`) con la imagen en base64 en una línea JSON | Que el Service escriba la imagen en `/run/openplayer` y responda la ruta | Mantiene el contrato JSON Lines y no suma permisos de archivos; 565 KB pasan a ~750 KB, aceptable para una petición puntual. |
| Una conexión corta aparte para la carátula | Reusar la conexión de `player.subscribe` | La suscripción ignora peticiones (SPEC 16), y una línea grande frenaría los snapshots. |
| `binarylimit 1048576` antes de pedir la imagen | Los trozos de 8 KB por defecto | Una carátula de 565 KB llega en 1 trozo en lugar de ~70 idas y vueltas. |
| El agente redimensiona con Pillow (`draft` en JPEG) | Redimensionar en el Service | Pillow ya está en la Pi; en .NET haría falta una librería de imagen nueva. `draft` decodifica a tamaño reducido y es mucho más rápido en la Pi Zero. |
| Se pide solo en modo `art` | Pedir en cada cambio de pista | No gasta CPU ni MPD mientras se usan los modos pista o reloj. |
| La caché es la última carátula, por (artista, álbum) | Por archivo, o una caché más grande o en disco | Las pistas de un mismo álbum no la vuelven a pedir; YAGNI para más. En la biblioteca actual cada álbum tiene o no tiene carátula entera (Adele *21* sin, *25* con). |
| Tope de 2 MB | Sin tope | Evita que una imagen gigante sature la memoria de la Pi Zero; la más grande de la biblioteca pesa 565 KB. |
| Carátula sin texto, dentro del anillo de progreso | Título encima, o la carátula atenuada con el texto | Lo eligió el usuario; los modos pista y reloj ya muestran el texto. |
| Placeholder ♪ con el título cuando no hay carátula | Caer al modo pista | Lo eligió el usuario: el modo `art` se reconoce siempre y no salta a otro diseño. |
| `menu` cicla los tres modos (track → clock → art) | Un botón aparte o una pulsación larga | No suma hardware ni gestos nuevos, y sigue lo hecho en SPEC 18. |
| La carátula en la web queda para otra spec | Hacerla ahora | Fuera de alcance; la petición IPC nueva ya la deja preparada. |

## Riesgos identificados

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Pasar `MpdClient` de `StreamReader` a lectura de bytes rompe el parseo de texto que ya existe (acentos UTF-8, líneas largas) | Toda la comunicación con MPD falla | Paso 1 aislado. Pruebas con acentos y respuestas grandes antes de tocar nada más; las 100 pruebas Mpd existentes tienen que pasar sin cambios. |
| La versión de MPD de la Pi no soporta `binarylimit` | La carátula no carga | `binarylimit` existe desde MPD 0.22.4 y la Pi tiene 0.24.4. Si responde `ACK`, se ignora y se sigue con trozos de 8 KB (más lento pero funciona). |
| Decodificar un PNG grande (333 KB, Imagine Dragons) es lento en la Pi Zero, porque `draft` solo ayuda con JPEG | Más de 1,5 s para aparecer | Se decodifica una vez por álbum y en un hilo aparte (se ve el placeholder mientras tanto). Se mide en la Pi; si no se cumple, queda una nota `ponytail:` para cachear la imagen ya preparada en disco. |
| La pista cambia mientras se pide la carátula | Se muestra la carátula del álbum anterior | La respuesta trae `songId`, y el agente la descarta si la clave (artista, álbum) ya cambió. |
| Pistas sin etiquetas de artista ni álbum: la clave es `(None, None)` | Todas comparten una carátula | Con la clave en `(None, None)` se usa el título como desempate. Las pistas sin etiquetas son raras en la biblioteca actual. |
| Una línea de ~2,7 MB en el socket | Memoria y tiempo en la Pi | Tope de 2 MB en el Service (~2,7 MB en base64) y de 3 MB en el agente. La conexión es corta y se cierra al terminar. |
| Pillow 11 (trixie) deprecia o cambia APIs (`draft`, `ImageOps.fit`) | Advertencias o fallos | Las pruebas corren con las advertencias de obsolescencia tratadas como errores, como en SPEC 17 y 18. |
