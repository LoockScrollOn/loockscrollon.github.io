# Lazarus Glass

> Sistema de asistencia visual inteligente para personas con discapacidad visual, basado en ESP32 y MicroPython.

[![MicroPython](https://img.shields.io/badge/MicroPython-v1.20+-blue)](https://micropython.org/)
[![Firebase](https://img.shields.io/badge/Firebase-Realtime%20Database-orange)](https://firebase.google.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-ESP32-red)](https://www.espressif.com/)

---

## Descripción

Lazarus Glass es un prototipo de lentes inteligentes que integra visión por computadora, detección de obstáculos, alertas sonoras y conectividad en tiempo real. El dispositivo detecta colores de semáforos mediante una cámara Pixy2, alerta al usuario sobre obstáculos cercanos con buzzers laterales, y transmite telemetría a Firebase para que familiares o cuidadores puedan monitorear al usuario desde un panel web.

### Características principales

- **Detección de colores** — Pixy2 entrenada para rojo, amarillo y verde (signaturas 1–6)
- **Alertas sonoras** — 3 beeps para rojo, 2 para amarillo, non-blocking
- **Detección de obstáculos** — sensores HC-SR04 izquierdo y derecho con umbral configurable
- **Sensor de luz** — LED RGB cambia a blanco cuando el ambiente es oscuro
- **Indicador LED RGB** — 5 estados visuales del sistema
- **WiFi multi-red** — portal de configuración vía Access Point si no conecta
- **Telemetría en tiempo real** — Firebase Realtime Database vía REST API
- **Geolocalización por IP** — ubicación aproximada cuando el GPS no está disponible
- **Panel web** — dashboard con mapa, sensores y estado del dispositivo

---

## Estructura del repositorio

```
lazarus-glass/
│
├── firmware/                  # Código MicroPython para el ESP32
│   ├── main.py                # Loop principal no bloqueante
│   ├── hal_hardware.py        # HAL: Pixy2, HC-SR04, buzzers, LED RGB, sensor IR
│   ├── wifi_manager.py        # Gestión WiFi y portal de configuración AP
│   └── firebase_client.py     # Cliente REST para Firebase
│
├── web/
│   └── index.html             # Panel de monitoreo en tiempo real
│
├── requirements.txt           # Dependencias del entorno de desarrollo
└── README.md
```

---

## Hardware requerido

| Componente | Cantidad | GPIO(s) |
|---|---|---|
| ESP32 DevKit (30 pines) | 1 | — |
| Cámara Pixy2 | 1 | SDA: 21, SCL: 22 |
| Sensor ultrasónico HC-SR04 | 2 | Izq: TRIG 5 / ECHO 18 — Der: TRIG 19 / ECHO 23 |
| Buzzer activo 5V | 2 | Izq: 25 — Der: 26 |
| LED RGB (cátodo común) | 1 | R: 2 — G: 4 — B: 15 |
| Sensor IR digital | 1 | 35 |
| Módulo GPS NEO-6M | 1 | TX: 16, RX: 17 (en desarrollo) |
| Resistencias 220Ω / 100Ω | 3 | LED RGB |
| Divisor de voltaje 1kΩ/2kΩ | 2 | Pines ECHO (5V → 3.3V) |
| Power bank 5V | 1 | VIN |

> **GPIO2 y GPIO15** son pines de strapping del ESP32. Si el dispositivo no arranca correctamente con el LED conectado, muévelos a GPIO13/GPIO27.

---

## Instalación y configuración

### 1. Requisitos del entorno de desarrollo

```bash
pip install -r requirements.txt
```

`requirements.txt`:
```
esptool==4.7.0
mpremote==1.22.0
adafruit-ampy==1.1.0
```

> También se puede usar **Thonny IDE** (recomendado para principiantes) o **VS Code** con la extensión [MicroPico](https://marketplace.visualstudio.com/items?itemName=paulober.pico-w-go).

### 2. Flashear MicroPython en el ESP32

Descarga el firmware desde [micropython.org/download/esp32](https://micropython.org/download/esp32/).

```bash
# Borrar flash
esptool.py --chip esp32 --port /dev/ttyUSB0 erase_flash

# Flashear MicroPython
esptool.py --chip esp32 --port /dev/ttyUSB0 --baud 460800 \
  write_flash -z 0x1000 esp32-20240602-v1.23.0.bin
```

> En Windows reemplaza `/dev/ttyUSB0` por `COM3` (o el puerto que corresponda).

### 3. Configurar Firebase

1. Crear un proyecto en [Firebase Console](https://console.firebase.google.com/).
2. Activar **Realtime Database** en modo de prueba.
3. En **Reglas**, pegar:

```json
{
  "rules": {
    ".read": true,
    ".write": true
  }
}
```

4. Copiar la URL de la base de datos (ej: `https://tu-proyecto-default-rtdb.firebaseio.com`).
5. Editar `firmware/firebase_client.py` y reemplazar:

```python
FIREBASE_URL = "https://tu-proyecto-default-rtdb.firebaseio.com"
DEVICE_PATH  = "dispositivos/lazarus_glass_01"
```

### 4. Entrenar la Pixy2

1. Conectar la Pixy2 al PC y abrir **PixyMon**.
2. En **Configure → Interface**, establecer `Data out port: I2C` y `I2C address: 0x54`.
3. Entrenar las signaturas:
   - Signaturas **1 y 2** → color **rojo**
   - Signaturas **3 y 4** → color **amarillo**
   - Signaturas **5 y 6** → color **verde**
4. Guardar y desconectar.

### 5. Subir el firmware al ESP32

Con `mpremote`:

```bash
mpremote connect /dev/ttyUSB0 cp firmware/hal_hardware.py  :hal_hardware.py
mpremote connect /dev/ttyUSB0 cp firmware/wifi_manager.py  :wifi_manager.py
mpremote connect /dev/ttyUSB0 cp firmware/firebase_client.py :firebase_client.py
mpremote connect /dev/ttyUSB0 cp firmware/main.py          :main.py
```

Con `ampy`:

```bash
ampy --port /dev/ttyUSB0 put firmware/hal_hardware.py
ampy --port /dev/ttyUSB0 put firmware/wifi_manager.py
ampy --port /dev/ttyUSB0 put firmware/firebase_client.py
ampy --port /dev/ttyUSB0 put firmware/main.py
```

### 6. Configurar la red WiFi

Al primer arranque (o si no hay redes guardadas), el ESP32 abre automáticamente un **Access Point de configuración**:

1. Conectar el teléfono o PC a la red Wi-Fi: `LazarusGlass-Config`
2. Contraseña: `12345678`
3. Abrir el navegador y navegar a: `http://1.1.1.100`
4. Agregar la red WiFi deseada y guardar.
5. El ESP32 se reinicia y se conecta automáticamente.

---

## Panel web

El archivo `web/index.html` es una página estática que puede abrirse directamente en el navegador o desplegarse en GitHub Pages.

Antes de usarlo, reemplazar el objeto `firebaseConfig` con los datos reales del proyecto Firebase:

```javascript
const firebaseConfig = {
  apiKey:            "TU_API_KEY",
  authDomain:        "tu-proyecto.firebaseapp.com",
  databaseURL:       "https://tu-proyecto-default-rtdb.firebaseio.com",
  projectId:         "tu-proyecto",
  storageBucket:     "tu-proyecto.appspot.com",
  messagingSenderId: "TU_SENDER_ID",
  appId:             "TU_APP_ID"
};
```

El panel muestra en tiempo real:

- Estado de conexión WiFi e IP del dispositivo
- Color detectado por la Pixy2
- Distancias de ambos sensores ultrasónicos con alerta visual
- Diagrama SVG interactivo de los lentes visto desde arriba
- Mapa de ubicación aproximada por IP (OpenStreetMap)

---

## Flujo de arranque

```
Encendido
    │
    ▼
Reset limpio de interfaces WiFi
    │
    ▼
¿Hay redes guardadas en wifi_networks.json?
    │
    ├── NO ──► Abrir Access Point → Portal web http://1.1.1.100
    │
    └── SÍ ──► Intentar conectar a cada red (10s por red)
                    │
                    ├── FALLO ──► Abrir Access Point
                    │
                    └── ÉXITO ──► Inicializar Pixy2
                                      │
                                      └── Loop principal no bloqueante
                                            ├── Sensor IR    (200ms)
                                            ├── Ultrasónicos  (80ms)
                                            ├── Pixy2        (250ms)
                                            ├── Telemetría  (5000ms)
                                            └── GeoIP      (60000ms)
```

---

## Estados del LED RGB

| Color | Estado | Descripción |
|---|---|---|
| Azul | Conectando | Durante la conexión WiFi al arrancar |
| Verde | Sistema OK | WiFi conectado y Pixy2 funcionando |
| Amarillo | Modo AP | Access Point activo para configuración |
| Rojo | Error | Pixy2 no detectada o fallo crítico |
| Blanco | Oscuro | Sensor IR detecta ausencia de luz |

---

## Estructura de datos en Firebase

```json
{
  "dispositivos": {
    "lazarus_glass_01": {
      "telemetria": {
        "estado_wifi": "conectado",
        "ultimo_color_detectado": "rojo",
        "sensor_izq_alerta": false,
        "sensor_der_alerta": true,
        "dist_izq_cm": 45.2,
        "dist_der_cm": 7.5,
        "ip_address": "192.168.1.100",
        "timestamp": 1718304351
      },
      "ubicacion_geoip": {
        "lat": 21.1253,
        "lng": -101.6197,
        "ciudad": "Leon",
        "region": "Guanajuato",
        "pais": "Mexico",
        "ip_publica": "200.x.x.x",
        "timestamp": 1718304351
      }
    }
  }
}
```

---

## Equipo

| Integrante | Rol |
|---|---|
| Victor | Arquitecto de firmware — HAL, loop no bloqueante, protocolo Pixy2 I2C |
| Alfredo de Jesús Mata Ramírez | Hardware y sensores — HC-SR04, sensor IR, cableado |
| Israel Sotelo Núñez | Conectividad y nube — WiFi manager, Firebase, panel web |

---

## Referencias

- [Pixy2 Serial Protocol](https://docs.pixycam.com/wiki/doku.php?id=wiki:v2:porting_guide)
- [MicroPython ESP32 Docs](https://docs.micropython.org/en/latest/esp32/quickref.html)
- [Firebase REST API](https://firebase.google.com/docs/reference/rest/database)
- [ip-api.com Geolocation](https://ip-api.com/docs)
- [HC-SR04 Datasheet](https://www.electronicoscaldas.com/datasheet/HC-SR04.pdf)

---

## Licencia

MIT — Instituto Tecnológico de León, Sistemas Programables, 2026.
