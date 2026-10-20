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

## Estructura

```text
OpenPlayer/
├── README.md
├── LICENSE
├── .gitignore
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
    └── hardware-agent/
```

## Convenciones para un LLM que trabaje en el repositorio

Antes de implementar una función, leer `README.md` y los documentos relevantes de `docs/`. Respetar las decisiones de arquitectura, distinguir hechos validados de hipótesis, y no cambiar asignaciones de GPIO ni el protocolo IPC sin actualizar documentación y pruebas. Implementar en etapas pequeñas y explicar comandos que requieran privilegios de administrador.
