import urequests
import ujson

FIREBASE_URL = "https://lazarus-glass-4194d-default-rtdb.firebaseio.com"
DEVICE_PATH  = "dispositivos/lazarus_glass_01"
GEO_IP_URL   = "http://ip-api.com/json"


def _url(path):
    return "{}/{}.json".format(FIREBASE_URL, path)


def _limpiar_ascii(texto):
    if not texto:
        return ''
    reemplazos = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ü': 'u', 'Ü': 'U', 'ñ': 'n', 'Ñ': 'N',
        '\xe1': 'a', '\xe9': 'e', '\xed': 'i',
        '\xf3': 'o', '\xfa': 'u', '\xf1': 'n',
        '\xc1': 'A', '\xc9': 'E', '\xcd': 'I',
        '\xd3': 'O', '\xda': 'U', '\xd1': 'N',
        '\xfc': 'u', '\xdc': 'U',
    }
    resultado = ''
    for c in texto:
        resultado += reemplazos.get(c, c if ord(c) < 128 else '?')
    return resultado


def _patch(path, data):
    url = _url(path)
    try:
        json_data = ujson.dumps(data)
        resp = urequests.patch(
            url,
            data=json_data,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        ok = resp.status_code in (200, 204)
        resp.close()
        return ok
    except Exception:
        return False


def obtener_ip_publica():
    try:
        resp = urequests.get(GEO_IP_URL, timeout=10)
        data = resp.json()
        resp.close()
        return data
    except Exception:
        return None


def enviar_telemetria(estado_wifi, ultimo_color,
                      dist_izq, dist_der,
                      ip_local, timestamp):
    UMBRAL_CM = 10.0
    data = {
        'estado_wifi':            estado_wifi,
        'ultimo_color_detectado': ultimo_color,
        'sensor_izq_alerta':      (dist_izq is not None
                                   and dist_izq <= UMBRAL_CM),
        'sensor_der_alerta':      (dist_der is not None
                                   and dist_der <= UMBRAL_CM),
        'dist_izq_cm':            round(dist_izq, 1) if dist_izq else None,
        'dist_der_cm':            round(dist_der, 1) if dist_der else None,
        'ip_address':             ip_local,
        'timestamp':              timestamp
    }
    return _patch('{}/telemetria'.format(DEVICE_PATH), data)


def enviar_geoip(geo_data):
    if not geo_data:
        return False
    data = {
        'lat':        geo_data.get('lat',        0),
        'lng':        geo_data.get('lon',        0),
        'ciudad':     _limpiar_ascii(geo_data.get('city',       '')),
        'region':     _limpiar_ascii(geo_data.get('regionName', '')),
        'pais':       _limpiar_ascii(geo_data.get('country',    '')),
        'ip_publica': geo_data.get('query',      ''),
        'timestamp':  geo_data.get('timestamp',  0)
    }
    return _patch('{}/ubicacion_geoip'.format(DEVICE_PATH), data)
