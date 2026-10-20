# GPIO Map — OpenPlayer

**Estado:** asignación propuesta. Confirmar orientación del encabezado y cableado antes de energizar.

## 1. Reglas eléctricas

- Los GPIO de Raspberry Pi usan lógica de **3.3 V** y no son tolerantes a 5 V.
- Nunca conectar 5 V a un GPIO.
- Apagar y desconectar la Pi antes de modificar el cableado.
- Para botones, conectar un terminal a GPIO y el otro a GND; activar pull-up interno.
- No conectar salidas de módulos desconocidos hasta verificar tensión y pinout.
- La OLED es opcional en la fase 2. Verificar si el módulo admite 3.3 V tanto en alimentación como en lógica.
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
| OLED SDA | GPIO2 / SDA1 | 3 | SDA del módulo | Fase 2 |
| OLED SCL | GPIO3 / SCL1 | 5 | SCL del módulo | Fase 2 |
| OLED VCC | — | 1 | 3.3 V, solo si el módulo lo admite | Fase 2 |
| OLED GND | — | 6 | GND | Fase 2 |

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
- Una pulsación debe generar exactamente un evento `button.pressed`.
- Liberar el botón no genera una acción salvo que se implemente explícitamente un gesto.
- No implementar pulsación larga hasta que la pulsación corta sea estable.
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
| `menu` | Reservado para menú OLED; por ahora ignorar o registrar |

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
- Para OLED, activar I²C, detectar el dispositivo con una herramienta compatible y verificar dirección I²C antes de inicializar el display.

## 8. Reglas para LLMs

No cambiar el mapa GPIO por conveniencia sin revisar conflictos con I²C, SPI, UART u otras funciones. Nunca sugerir aplicar 5 V a GPIO. No afirmar que una OLED es compatible solo por tener cuatro pines; comprobar pinout, tensión y controlador. Mantener asignaciones de hardware configurables cuando sea razonable, pero documentar un valor predeterminado único.

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
