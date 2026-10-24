# Battery Design — OpenPlayer

**Estado:** requisitos y plan de selección. No es todavía un esquema eléctrico de fabricación. No construir ni conectar una batería hasta validar los módulos elegidos.

## 1. Objetivo

Hacer que OpenPlayer sea portátil y funcione de forma estable con Raspberry Pi Zero 2 W, DAC USB y, más adelante, Bluetooth. La alimentación debe tolerar picos de consumo, mantener 5 V regulados, proteger la batería y permitir un apagado seguro.

## 2. Estrategia por etapas

### Etapa A — Desarrollo

Usar una fuente USB de 5 V de buena calidad. Verificar estabilidad con la Pi, Wi-Fi y DAC conectados.

### Etapa B — Prueba portátil

Usar un power bank de calidad con salida regulada de 5 V. Comprobar si mantiene la salida con la carga real y si se apaga automáticamente con consumos bajos. No asumir que cualquier power bank sirve.

### Etapa C — Integración

Solo después de medir consumo y autonomía, seleccionar batería, cargador, protección y regulador. Un módulo UPS compatible puede simplificar el diseño, pero debe verificarse el soporte de la placa y la corriente continua/pico.

## 3. Requisitos eléctricos

El diseño final debe documentar:

- Química y configuración de la batería (por ejemplo, una celda Li-ion/LiPo protegida; valor exacto pendiente).
- Capacidad nominal en Wh y mAh, y voltaje nominal.
- Protección contra sobrecarga, sobredescarga, sobrecorriente y cortocircuito.
- Cargador apropiado para la química y número de celdas.
- Salida regulada de 5 V con corriente continua y transitoria suficiente para la Pi y periféricos.
- Protección térmica y comportamiento durante la carga mientras el dispositivo está encendido.
- Indicador o medición del estado de carga, si se desea.
- Interruptor, conector de carga, fusible/protección y cableado adecuados.
- Estrategia de apagado y recuperación después de agotarse la batería.

**Nunca** conectar una celda Li-ion/LiPo directamente al pin de 5 V de la Raspberry Pi. No usar un cargador genérico sin conocer su compatibilidad. No asumir que el circuito de protección de una celda reemplaza al cargador o al regulador.

## 4. Medir consumo antes de dimensionar

Medir con un medidor USB o instrumento apropiado al menos estos escenarios:

1. Arranque de la Pi.
2. Inactividad con Wi-Fi conectado.
3. Reproducción por DAC USB.
4. Reproducción por Bluetooth A2DP.
5. Uso de botones/pantalla cuando estén montados.
6. Máxima carga prevista (actividad de CPU, Wi-Fi y audio simultáneos).

Registrar tensión, corriente y duración. Medir en el punto de alimentación del sistema, no estimar únicamente a partir del consumo típico de la placa.

## 5. Estimación de autonomía

Usar Wh para comparar fuentes con distintos voltajes:

```text
E_batería_Wh = capacidad_Ah × voltaje_nominal_V
E_util_Wh = E_batería_Wh × eficiencia_total
autonomía_h ≈ E_util_Wh / potencia_promedio_W
```

Ejemplo meramente ilustrativo: 10 Wh, eficiencia total de 0.85 y carga media de 2 W darían aproximadamente 4.25 h. No representa una medición de OpenPlayer.

La capacidad indicada en mAh de un power bank suele referirse a la tensión interna de sus celdas; no comparar mAh sin considerar tensión y pérdidas de conversión.

## 6. Selección de power bank o módulo UPS

Evaluar:

- Salida regulada de 5 V y corriente continua suficiente, con margen sobre el consumo medido.
- Corriente pico durante arranque y conexión del DAC.
- Si la salida permanece activa a baja carga.
- Si permite cargar mientras alimenta la Pi (passthrough) y cómo gestiona esa condición.
- Protecciones eléctricas y térmicas documentadas.
- Tamaño, masa, disipación y ubicación de antenas.
- Facilidad de reemplazar la batería sin dañar la carcasa.
- Compatibilidad física con el montaje 3D.

No elegir un componente únicamente por la capacidad en mAh o por la palabra “UPS”. Leer la documentación y validar el circuito completo.

## 7. Apagado seguro

La batería no debe cortar la alimentación sin aviso cuando sea posible evitarlo. Plan previsto:

1. Obtener nivel bajo de batería mediante un indicador/medidor compatible.
2. Cuando alcance el umbral definido por el módulo y validado experimentalmente, avisar al servicio.
3. El servicio detiene nuevas operaciones, guarda preferencias necesarias y solicita apagado ordenado del sistema.
4. Esperar confirmación o un margen de seguridad antes de cortar la alimentación.

Si el power bank no ofrece señal de batería baja, el software no puede conocer con precisión el estado de carga sin hardware adicional. Documentar esa limitación.

Una pulsación larga del botón de encendido puede iniciar `sudo systemctl poweroff` a través de un mecanismo controlado y con privilegios mínimos. No dar permisos generales de `sudo` al agente Python.

## 8. Seguridad mecánica y térmica

- No perforar, aplastar ni doblar una celda pouch.
- No dejar celdas sueltas contra pines o tornillos.
- Aislar contactos y fijar la batería para evitar movimiento.
- No encerrar una batería que se caliente durante carga/descarga sin evaluación térmica.
- Separar la batería de bordes afilados y tornillos de la carcasa.
- No imprimir la carcasa final antes de conocer dimensiones reales de batería, módulo de carga y conectores.
- Facilitar inspección y reemplazo de la batería.

## 9. Tabla de decisiones pendientes

| Decisión | Estado | Cómo resolver |
|---|---|---|
| Autonomía objetivo | Pendiente | Elegir horas objetivo por carga |
| Consumo promedio/pico | Pendiente | Medir prototipo completo |
| Power bank de prueba | Pendiente | Elegir unidad con 5 V estable y salida persistente |
| Batería integrada | Pendiente | Comparar módulo UPS documentado y solución discreta |
| Indicador de batería | Pendiente | Determinar si el módulo ofrece telemetría o requiere ADC/medidor |
| Carga mientras reproduce | Pendiente | Verificar explícitamente en documentación y pruebas |
| Método de apagado | Diseñar en software; validar en hardware | Definir señal/umbral y comportamiento de corte |

## 10. Criterios de aceptación

- Tensión dentro de especificación durante arranque y carga máxima prevista.
- Sin reinicios o desconexiones de DAC durante pruebas prolongadas.
- Temperaturas dentro de límites de los fabricantes.
- Autonomía medida y documentada, no solo calculada.
- Carga, descarga y protección verificadas de acuerdo con la documentación del módulo.
- Apagado ordenado probado y recuperación posterior comprobada.

## 11. Instrucciones para LLMs

No recomendar un esquema de batería definitivo sin modelo exacto de celda, cargador y regulador. No dar por hecho que un módulo soporta passthrough o power-path. Solicitar o buscar hojas de datos del componente seleccionado, calcular corriente con margen y distinguir claramente entre estimaciones y medidas. Priorizar módulos documentados y seguros frente a circuitos improvisados.
