from machine import SoftI2C, Pin, time_pulse_us
import time
import ustruct

SYNC_REQUEST     = bytes([0xae, 0xc1])
SYNC_RESPONSE_1  = 0xaf
SYNC_RESPONSE_2  = 0xc1

TYPE_REQUEST_VERSION  = 0x0e
TYPE_RESPONSE_VERSION = 0x0f
TYPE_REQUEST_BLOCKS   = 0x20
TYPE_RESPONSE_BLOCKS  = 0x21

SIG_ROJO_1     = 0x01
SIG_ROJO_2     = 0x02
SIG_AMARILLO_1 = 0x04
SIG_AMARILLO_2 = 0x08
SIG_VERDE_1    = 0x10
SIG_VERDE_2    = 0x20
SIG_ALL        = 0xFF


class Pixy2Error(Exception):
    pass


class Block:
    def __init__(self, sig, x, y, width, height, angle, index, age):
        self.sig            = sig
        self.x_center       = x
        self.y_center       = y
        self.width          = width
        self.height         = height
        self.angle          = angle
        self.tracking_index = index
        self.age            = age

    def __repr__(self):
        return ("Block(sig={}, x={}, y={}, w={}, h={})"
                .format(self.sig, self.x_center, self.y_center,
                        self.width, self.height))


class Pixy2:
    def __init__(self, scl_pin=22, sda_pin=21,
                 freq=50000, i2c_address=0x54):
        self.i2c_address = i2c_address
        self.i2c = SoftI2C(scl=Pin(scl_pin), sda=Pin(sda_pin), freq=freq)
        self._check_connection()

    def _check_connection(self):
        devices = self.i2c.scan()
        if self.i2c_address not in devices:
            raise Pixy2Error(
                "Pixy2 no detectada en 0x{:02x}. Encontrados: {}".format(
                    self.i2c_address, [hex(d) for d in devices])
            )

    def _send_packet(self, payload_type, payload=b''):
        packet = SYNC_REQUEST + bytes([payload_type, len(payload)]) + payload
        self.i2c.writeto(self.i2c_address, packet)

    def _find_sync(self, raw):
        for i in range(len(raw) - 1):
            if raw[i] == SYNC_RESPONSE_1 and raw[i + 1] == SYNC_RESPONSE_2:
                return i
        return None

    def _request_and_read(self, payload_type, expected_type,
                           payload=b'', tries=5, max_chunk=64,
                           retry_delay_ms=20):
        last_err = None
        for attempt in range(tries):
            self._send_packet(payload_type, payload)
            try:
                raw = self.i2c.readfrom(self.i2c_address, max_chunk)
            except OSError as e:
                last_err = e
                time.sleep_ms(retry_delay_ms)
                continue

            idx = self._find_sync(raw)
            if idx is None or idx + 6 > len(raw):
                time.sleep_ms(retry_delay_ms)
                continue

            ptype  = raw[idx + 2]
            length = raw[idx + 3]
            payload_start = idx + 6
            available     = len(raw) - payload_start

            if available >= length:
                data = raw[payload_start: payload_start + length]
            else:
                data   = raw[payload_start:]
                faltan = length - len(data)
                try:
                    extra = self.i2c.readfrom(self.i2c_address, faltan)
                    data += extra
                except OSError as e:
                    last_err = e
                    time.sleep_ms(retry_delay_ms)
                    continue

            if ptype == expected_type:
                return data

            time.sleep_ms(retry_delay_ms)

        msg = "Timeout esperando respuesta tipo 0x{:02x}".format(expected_type)
        if last_err:
            msg += " (ultimo error I2C: {})".format(last_err)
        raise Pixy2Error(msg)

    def get_version(self):
        data = self._request_and_read(
            TYPE_REQUEST_VERSION, TYPE_RESPONSE_VERSION)
        hw_ver, fw_major, fw_minor, fw_build = ustruct.unpack(
            '<HBBH', data[:6])
        return {
            'hardware': hw_ver,
            'firmware': '{}.{}'.format(fw_major, fw_minor),
            'build':    fw_build
        }

    def get_blocks(self, sigmap=SIG_ALL, max_blocks=10):
        payload = ustruct.pack('<BB', sigmap, max_blocks)
        data    = self._request_and_read(
            TYPE_REQUEST_BLOCKS, TYPE_RESPONSE_BLOCKS,
            payload=payload, max_chunk=128)

        blocks     = []
        block_size = 14
        nr_blocks  = len(data) // block_size

        for i in range(nr_blocks):
            offset = i * block_size
            chunk  = data[offset: offset + block_size]
            (sig, x, y, w, h, angle,
             index, age) = ustruct.unpack('<HHHHHhBB', chunk)
            blocks.append(Block(sig, x, y, w, h, angle, index, age))

        return blocks

    def get_blocks_by_color(self, sigmap, max_blocks=5):
        return self.get_blocks(sigmap=sigmap, max_blocks=max_blocks)


class UltrasonicSensor:
    SOUND_SPEED_CM_US = 0.0343
    DIST_MIN_CM       = 2.0
    DIST_MAX_CM       = 300.0

    def __init__(self, trigger_pin, echo_pin, timeout_us=25000):
        self.trigger    = Pin(trigger_pin, Pin.OUT)
        self.echo       = Pin(echo_pin,    Pin.IN)
        self.timeout_us = timeout_us
        self.trigger.value(0)
        time.sleep_ms(30)

    def distancia_cm(self):
        self.trigger.value(0)
        time.sleep_us(5)
        self.trigger.value(1)
        time.sleep_us(10)
        self.trigger.value(0)

        try:
            duracion = time_pulse_us(self.echo, 1, self.timeout_us)
        except OSError:
            return None

        if duracion <= 0:
            return None

        distancia = (duracion * self.SOUND_SPEED_CM_US) / 2.0

        if distancia < self.DIST_MIN_CM or distancia > self.DIST_MAX_CM:
            return None

        return distancia


class Buzzer:
    def __init__(self, pin):
        self.pin = Pin(pin, Pin.OUT)
        self.pin.value(0)

    def on(self):
        self.pin.value(1)

    def off(self):
        self.pin.value(0)

    def beep(self, duration_ms=100):
        self.on()
        time.sleep_ms(duration_ms)
        self.off()


class SistemaProximidad:
    def __init__(self,
                 trigger_izq, echo_izq, buzzer_izq_pin,
                 trigger_der, echo_der, buzzer_der_pin,
                 umbral_cm=10):
        self.sensor_izq = UltrasonicSensor(trigger_izq, echo_izq)
        self.sensor_der = UltrasonicSensor(trigger_der, echo_der)
        self.buzzer_izq = Buzzer(buzzer_izq_pin)
        self.buzzer_der = Buzzer(buzzer_der_pin)
        self.umbral_cm  = umbral_cm

    def actualizar(self):
        dist_izq = self.sensor_izq.distancia_cm()
        dist_der = self.sensor_der.distancia_cm()

        if dist_izq is not None and dist_izq <= self.umbral_cm:
            self.buzzer_izq.on()
        else:
            self.buzzer_izq.off()

        if dist_der is not None and dist_der <= self.umbral_cm:
            self.buzzer_der.on()
        else:
            self.buzzer_der.off()

        return {'izquierda': dist_izq, 'derecha': dist_der}


class LedRGB:
    def __init__(self, pin_rojo=2, pin_verde=4, pin_azul=15,
                 catodo_comun=True):
        self.r            = Pin(pin_rojo,  Pin.OUT)
        self.g            = Pin(pin_verde, Pin.OUT)
        self.b            = Pin(pin_azul,  Pin.OUT)
        self.catodo_comun = catodo_comun
        self.apagar()

    def _set(self, r, g, b):
        if self.catodo_comun:
            self.r.value(1 if r else 0)
            self.g.value(1 if g else 0)
            self.b.value(1 if b else 0)
        else:
            self.r.value(0 if r else 1)
            self.g.value(0 if g else 1)
            self.b.value(0 if b else 1)

    def apagar(self):
        self._set(0, 0, 0)

    def rojo(self):
        self._set(1, 0, 0)

    def verde(self):
        self._set(0, 1, 0)

    def azul(self):
        self._set(0, 0, 1)

    def amarillo(self):
        self._set(1, 1, 0)

    def blanco(self):
        self._set(1, 1, 1)


ESTADO_CONECTANDO = 'conectando'
ESTADO_OK         = 'ok'
ESTADO_CONFIG_AP  = 'config_ap'
ESTADO_ERROR      = 'error'
ESTADO_OSCURO     = 'oscuro'


def aplicar_estado_led(led, estado):
    if estado == ESTADO_CONECTANDO:
        led.azul()
    elif estado == ESTADO_CONFIG_AP:
        led.amarillo()
    elif estado == ESTADO_OSCURO:
        led.blanco()
    elif estado == ESTADO_OK:
        led.verde()
    elif estado == ESTADO_ERROR:
        led.rojo()
    else:
        led.apagar()


class SensorIR:
    def __init__(self, pin, invertido=True):
        self.pin       = Pin(pin, Pin.IN)
        self.invertido = invertido

    def hay_luz(self):
        valor = self.pin.value()
        if self.invertido:
            return valor == 0
        return valor == 1

    def oscuro(self):
        return not self.hay_luz()
