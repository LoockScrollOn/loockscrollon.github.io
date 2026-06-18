import time
import network
from machine import UART, Pin

from hal_hardware import (
    Pixy2, Pixy2Error,
    SistemaProximidad,
    LedRGB,
    SensorIR,
    ESTADO_CONECTANDO, ESTADO_OK,
    ESTADO_CONFIG_AP, ESTADO_ERROR,
    ESTADO_OSCURO,
    aplicar_estado_led,
    SIG_ROJO_1, SIG_ROJO_2,
    SIG_AMARILLO_1, SIG_AMARILLO_2,
    SIG_VERDE_1, SIG_VERDE_2
)
import wifi_manager
import firebase_client

PIXY_SCL_PIN     = 22
PIXY_SDA_PIN     = 21

US_IZQ_TRIGGER   = 5
US_IZQ_ECHO      = 18
US_DER_TRIGGER   = 19
US_DER_ECHO      = 23

BUZZER_IZQ_PIN   = 25
BUZZER_DER_PIN   = 26

UMBRAL_PROXIMIDAD_CM = 10

GPS_UART_ID      = 1
GPS_TX_PIN       = 17
GPS_RX_PIN       = 16

LED_R_PIN        = 2
LED_G_PIN        = 4
LED_B_PIN        = 15

IR_PIN           = 35

INTERVALO_IR_MS          = 200
INTERVALO_ULTRASONICO_MS = 80
INTERVALO_PIXY_MS        = 250
INTERVALO_TELEMETRIA_MS  = 5000
INTERVALO_GEOIP_MS       = 60000
INTERVALO_PRINT_MS       = 1000

BEEP_ON_MS           = 120
BEEP_OFF_MS          = 100
COLOR_CONFIRMACIONES = 3

DELAY_TELEMETRIA_INICIAL_MS = 3000
DELAY_GEOIP_INICIAL_MS      = 10000

SIG_TO_COLOR = {
    SIG_ROJO_1:     'rojo',
    SIG_ROJO_2:     'rojo',
    SIG_AMARILLO_1: 'amarillo',
    SIG_AMARILLO_2: 'amarillo',
    SIG_VERDE_1:    'verde',
    SIG_VERDE_2:    'verde',
}

ALL_TRAINED_SIGMAP = (SIG_ROJO_1 | SIG_ROJO_2 |
                       SIG_AMARILLO_1 | SIG_AMARILLO_2 |
                       SIG_VERDE_1 | SIG_VERDE_2)


def color_de_signatura(sig):
    bit = 1 << (sig - 1)
    return SIG_TO_COLOR.get(bit, 'desconocido')


class ColorDebounce:
    def __init__(self, confirmaciones=COLOR_CONFIRMACIONES):
        self.confirmaciones = confirmaciones
        self.candidato      = 'ninguno'
        self.contador       = 0
        self.confirmado     = 'ninguno'

    def actualizar(self, color_leido):
        if color_leido == self.candidato:
            self.contador += 1
        else:
            self.candidato = color_leido
            self.contador  = 1
        if self.contador >= self.confirmaciones:
            if self.confirmado != self.candidato:
                self.confirmado = self.candidato
                return True
        return False

    def reset(self):
        self.candidato  = 'ninguno'
        self.contador   = 0
        self.confirmado = 'ninguno'


class BeepManager:
    IDLE     = 0
    BEEP_ON  = 1
    BEEP_OFF = 2

    def __init__(self, buzzer_izq, buzzer_der):
        self.biz       = buzzer_izq
        self.bde       = buzzer_der
        self.state     = self.IDLE
        self.restantes = 0
        self.ts        = 0

    def disparar(self, repeticiones):
        if repeticiones <= 0:
            return
        self.restantes = repeticiones
        self._iniciar_beep()

    def _iniciar_beep(self):
        self.biz.on()
        self.bde.on()
        self.state = self.BEEP_ON
        self.ts    = time.ticks_ms()

    def _detener_beep(self):
        self.biz.off()
        self.bde.off()
        self.state = self.BEEP_OFF
        self.ts    = time.ticks_ms()

    def update(self):
        now = time.ticks_ms()
        if self.state == self.BEEP_ON:
            if time.ticks_diff(now, self.ts) >= BEEP_ON_MS:
                self.restantes -= 1
                self._detener_beep()
        elif self.state == self.BEEP_OFF:
            if time.ticks_diff(now, self.ts) >= BEEP_OFF_MS:
                if self.restantes > 0:
                    self._iniciar_beep()
                else:
                    self.state = self.IDLE

    @property
    def ocupado(self):
        return self.state != self.IDLE


def _nmea_to_decimal(valor, hemisferio):
    if not valor:
        return None
    punto   = valor.find('.')
    grados  = int(valor[:punto - 2])
    minutos = float(valor[punto - 2:])
    decimal = grados + minutos / 60
    if hemisferio in ('S', 'W'):
        decimal = -decimal
    return decimal


def leer_gps_nb(uart):
    while uart.any():
        try:
            linea = uart.readline()
            if linea is None:
                break
            linea = linea.decode('ascii', 'ignore').strip()
        except Exception:
            break
        if linea.startswith('$GPGGA') or linea.startswith('$GNGGA'):
            campos = linea.split(',')
            if (len(campos) > 6
                    and campos[2]
                    and campos[4]
                    and campos[6] != '0'):
                lat = _nmea_to_decimal(campos[2], campos[3])
                lng = _nmea_to_decimal(campos[4], campos[5])
                if lat is not None and lng is not None:
                    return lat, lng
    return None


def inicializar_led():
    return LedRGB(pin_rojo=LED_R_PIN, pin_verde=LED_G_PIN, pin_azul=LED_B_PIN)


def inicializar_pixy():
    try:
        pixy = Pixy2(scl_pin=PIXY_SCL_PIN, sda_pin=PIXY_SDA_PIN)
        return pixy
    except Pixy2Error:
        return None


def inicializar_proximidad():
    return SistemaProximidad(
        trigger_izq=US_IZQ_TRIGGER,
        echo_izq=US_IZQ_ECHO,
        buzzer_izq_pin=BUZZER_IZQ_PIN,
        trigger_der=US_DER_TRIGGER,
        echo_der=US_DER_ECHO,
        buzzer_der_pin=BUZZER_DER_PIN,
        umbral_cm=UMBRAL_PROXIMIDAD_CM
    )


def inicializar_gps():
    return UART(GPS_UART_ID, baudrate=9600, tx=GPS_TX_PIN, rx=GPS_RX_PIN)


def inicializar_ir():
    return SensorIR(pin=IR_PIN, invertido=True)


def obtener_ip_local():
    try:
        sta = network.WLAN(network.STA_IF)
        if sta.isconnected():
            return sta.ifconfig()[0]
    except Exception:
        pass
    return '0.0.0.0'


def loop_principal(led, pixy):
    proximidad  = inicializar_proximidad()
    gps_uart    = inicializar_gps()
    sensor_ir   = inicializar_ir()
    beep_mgr    = BeepManager(proximidad.buzzer_izq, proximidad.buzzer_der)
    color_db    = ColorDebounce(confirmaciones=COLOR_CONFIRMACIONES)

    ultimo_color    = 'ninguno'
    ip_local        = obtener_ip_local()
    oscuro_anterior = False
    estado_sistema  = ESTADO_ERROR if pixy is None else ESTADO_OK

    ahora_ms = time.ticks_ms()
    ts_ir          = ahora_ms
    ts_ultrasonico = ahora_ms
    ts_pixy        = ahora_ms
    ts_print       = ahora_ms
    ts_telemetria  = time.ticks_add(ahora_ms, -INTERVALO_TELEMETRIA_MS
                                     + DELAY_TELEMETRIA_INICIAL_MS)
    ts_geoip       = time.ticks_add(ahora_ms, -INTERVALO_GEOIP_MS
                                     + DELAY_GEOIP_INICIAL_MS)

    dist_cache = {'izquierda': None, 'derecha': None}

    pixy_errores_consecutivos = 0
    MAX_ERRORES_PIXY          = 10

    aplicar_estado_led(led, estado_sistema)

    while True:
        now_ms = time.ticks_ms()

        beep_mgr.update()

        if time.ticks_diff(now_ms, ts_ir) >= INTERVALO_IR_MS:
            oscuro_actual = sensor_ir.oscuro()
            if oscuro_actual != oscuro_anterior:
                oscuro_anterior = oscuro_actual
            if oscuro_actual:
                aplicar_estado_led(led, ESTADO_OSCURO)
            else:
                aplicar_estado_led(led, estado_sistema)
            ts_ir = now_ms

        if (time.ticks_diff(now_ms, ts_ultrasonico) >= INTERVALO_ULTRASONICO_MS
                and not beep_mgr.ocupado):
            dist_cache     = proximidad.actualizar()
            ts_ultrasonico = now_ms

        if (pixy is not None
                and time.ticks_diff(now_ms, ts_pixy) >= INTERVALO_PIXY_MS):
            try:
                blocks = pixy.get_blocks(
                    sigmap=ALL_TRAINED_SIGMAP, max_blocks=5)

                pixy_errores_consecutivos = 0

                color_leido = 'ninguno'
                if blocks:
                    color_leido = color_de_signatura(blocks[0].sig)

                cambio = color_db.actualizar(color_leido)
                ultimo_color = color_db.confirmado

                if cambio and ultimo_color != 'ninguno':
                    if ultimo_color == 'rojo':
                        beep_mgr.disparar(3)
                    elif ultimo_color == 'amarillo':
                        beep_mgr.disparar(2)

                estado_sistema = ESTADO_OK

            except Exception:
                pixy_errores_consecutivos += 1
                estado_sistema = ESTADO_ERROR

                if pixy_errores_consecutivos >= MAX_ERRORES_PIXY:
                    pixy = inicializar_pixy()
                    pixy_errores_consecutivos = 0
                    color_db.reset()
                    ultimo_color   = 'ninguno'
                    estado_sistema = ESTADO_ERROR if pixy is None else ESTADO_OK

            ts_pixy = now_ms

        if time.ticks_diff(now_ms, ts_telemetria) >= INTERVALO_TELEMETRIA_MS:
            try:
                firebase_client.enviar_telemetria(
                    estado_wifi='conectado',
                    ultimo_color=ultimo_color,
                    dist_izq=dist_cache['izquierda'],
                    dist_der=dist_cache['derecha'],
                    ip_local=ip_local,
                    timestamp=int(time.time())
                )
            except Exception:
                pass
            ts_telemetria = now_ms

        if time.ticks_diff(now_ms, ts_geoip) >= INTERVALO_GEOIP_MS:
            try:
                geo = firebase_client.obtener_ip_publica()
                if geo and geo.get('status') == 'success':
                    geo['timestamp'] = int(time.time())
                    firebase_client.enviar_geoip(geo)
            except Exception:
                pass
            ts_geoip = now_ms

        if time.ticks_diff(now_ms, ts_print) >= INTERVALO_PRINT_MS:
            izq_str = "{:.1f}".format(dist_cache['izquierda']) \
                if dist_cache['izquierda'] is not None else "---"
            der_str = "{:.1f}".format(dist_cache['derecha']) \
                if dist_cache['derecha'] is not None else "---"
            print("[LG] color={} | izq={} cm | der={} cm | luz={} | beep={}".format(
                ultimo_color, izq_str, der_str,
                "SI" if not oscuro_anterior else "NO",
                "SI" if beep_mgr.ocupado else "no"
            ))
            ts_print = now_ms


def main():
    try:
        network.WLAN(network.AP_IF).active(False)
        network.WLAN(network.STA_IF).active(False)
    except Exception:
        pass
    time.sleep_ms(800)

    led = inicializar_led()
    aplicar_estado_led(led, ESTADO_CONECTANDO)

    sta = wifi_manager.conectar_wifi(timeout_por_red_s=10)

    if sta is None:
        aplicar_estado_led(led, ESTADO_CONFIG_AP)
        wifi_manager.iniciar_access_point()
    else:
        pixy = inicializar_pixy()
        aplicar_estado_led(led, ESTADO_ERROR if pixy is None else ESTADO_OK)
        loop_principal(led, pixy)


if __name__ == '__main__':
    main()
