import network
import socket
import json
import time
import machine

CONFIG_FILE = 'wifi_networks.json'

AP_SSID     = 'LazarusGlass-Config'
AP_PASSWORD = '12345678'
AP_IP       = '1.1.1.100'
AP_SUBNET   = '255.255.255.0'
AP_GATEWAY  = '1.1.1.100'
AP_DNS      = '1.1.1.100'


def _cargar_redes():
    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (OSError, ValueError):
        return []


def _guardar_redes(redes):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(redes, f)


def agregar_red(ssid, password):
    redes = _cargar_redes()
    for red in redes:
        if red['ssid'] == ssid:
            red['password'] = password
            _guardar_redes(redes)
            return
    redes.append({'ssid': ssid, 'password': password})
    _guardar_redes(redes)


def eliminar_red(ssid):
    redes = _cargar_redes()
    redes = [r for r in redes if r['ssid'] != ssid]
    _guardar_redes(redes)


def conectar_wifi(timeout_por_red_s=10):
    redes = _cargar_redes()
    if not redes:
        return None

    try:
        ap = network.WLAN(network.AP_IF)
        ap.active(False)
    except Exception:
        pass

    try:
        sta = network.WLAN(network.STA_IF)
        sta.active(False)
    except Exception:
        pass

    time.sleep_ms(500)

    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    time.sleep_ms(200)

    if sta.isconnected():
        return sta

    for red in redes:
        ssid     = red['ssid']
        password = red['password']

        try:
            sta.connect(ssid, password)
        except Exception:
            continue

        start = time.time()
        while not sta.isconnected():
            if time.time() - start > timeout_por_red_s:
                try:
                    sta.disconnect()
                except Exception:
                    pass
                break
            time.sleep(0.5)
        else:
            return sta

    try:
        sta.active(False)
    except Exception:
        pass
    return None


PAGINA_PRINCIPAL = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Configuracion WiFi - Lazarus Glass</title>
  <style>
    body {{ font-family: Arial, sans-serif; background:#f4f4f4; margin:0; padding:20px; }}
    .card {{ background:#fff; max-width:450px; margin:20px auto; padding:24px;
             border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.1); }}
    h1 {{ font-size:1.4em; color:#333; }}
    h2 {{ font-size:1.1em; color:#333; margin-top:24px;
          border-top:1px solid #eee; padding-top:16px; }}
    label {{ display:block; margin-top:12px; font-weight:bold; color:#555; }}
    input {{ width:100%; padding:8px; margin-top:4px; box-sizing:border-box;
             border:1px solid #ccc; border-radius:4px; }}
    button {{ margin-top:16px; width:100%; padding:10px; background:#2e7d32;
              color:#fff; border:none; border-radius:4px;
              font-size:1em; cursor:pointer; }}
    button:hover {{ background:#256428; }}
    .msg {{ margin-top:16px; padding:10px; border-radius:4px; }}
    .ok  {{ background:#e8f5e9; color:#256428; }}
    .err {{ background:#fdecea; color:#b3261e; }}
    table {{ width:100%; border-collapse:collapse; margin-top:8px; }}
    th, td {{ text-align:left; padding:8px;
              border-bottom:1px solid #eee; font-size:0.9em; }}
    .pw-cell {{ font-family:monospace; }}
    .ver-btn {{ background:#1565c0; color:#fff; border:none;
                border-radius:4px; padding:4px 10px;
                font-size:0.85em; cursor:pointer; }}
    .ver-btn:hover {{ background:#0d47a1; }}
    .del-btn {{ background:#b3261e; color:#fff; border:none;
                border-radius:4px; padding:4px 10px;
                font-size:0.85em; cursor:pointer; margin-left:4px; }}
    .del-btn:hover {{ background:#8c1c17; }}
    .vacio {{ color:#888; font-size:0.9em; margin-top:8px; }}
  </style>
  <script>
    function togglePassword(idx) {{
      var celda  = document.getElementById('pw-' + idx);
      var oculto = celda.getAttribute('data-hidden');
      var real   = celda.getAttribute('data-pw');
      var btn    = document.getElementById('btn-' + idx);
      if (oculto === '1') {{
        celda.textContent = real;
        celda.setAttribute('data-hidden', '0');
        btn.textContent = 'Ocultar';
      }} else {{
        celda.textContent = '********';
        celda.setAttribute('data-hidden', '1');
        btn.textContent = 'Ver';
      }}
    }}
  </script>
</head>
<body>
  <div class="card">
    <h1>Configuracion WiFi - Lazarus Glass</h1>
    {mensaje}
    <h2>Redes guardadas</h2>
    {tabla_redes}
    <h2>Agregar nueva red</h2>
    <form method="POST" action="/guardar">
      <label for="ssid">Nombre de red (SSID)</label>
      <input type="text" id="ssid" name="ssid" required>
      <label for="password">Contrasena</label>
      <input type="text" id="password" name="password">
      <button type="submit">Guardar y reiniciar</button>
    </form>
  </div>
</body>
</html>
"""

FILA_RED = """
    <tr>
      <td>{ssid}</td>
      <td class="pw-cell" id="pw-{idx}"
          data-pw="{password}" data-hidden="1">********</td>
      <td>
        <button class="ver-btn" id="btn-{idx}"
                onclick="togglePassword({idx})">Ver</button>
        <form method="POST" action="/eliminar" style="display:inline;">
          <input type="hidden" name="ssid" value="{ssid}">
          <button class="del-btn" type="submit">Eliminar</button>
        </form>
      </td>
    </tr>
"""


def _generar_tabla_redes():
    redes = _cargar_redes()
    if not redes:
        return '<p class="vacio">No hay redes guardadas todavia.</p>'
    filas = ''
    for idx, red in enumerate(redes):
        filas += FILA_RED.format(
            idx=idx,
            ssid=_html_escape(red['ssid']),
            password=_html_escape(red['password'])
        )
    return ('<table>'
            '<tr><th>SSID</th><th>Contrasena</th><th>Acciones</th></tr>'
            + filas + '</table>')


def _html_escape(s):
    return (s.replace('&', '&amp;')
             .replace('<', '&lt;')
             .replace('>', '&gt;')
             .replace('"', '&quot;'))


def _parse_form(body):
    datos = {}
    for par in body.split('&'):
        if '=' in par:
            clave, valor = par.split('=', 1)
            valor = valor.replace('+', ' ')
            valor = _url_decode(valor)
            clave = _url_decode(clave)
            datos[clave] = valor
    return datos


def _url_decode(s):
    resultado = ''
    i = 0
    while i < len(s):
        if s[i] == '%' and i + 2 < len(s):
            try:
                resultado += chr(int(s[i+1:i+3], 16))
                i += 3
                continue
            except ValueError:
                pass
        resultado += s[i]
        i += 1
    return resultado


def iniciar_access_point():
    try:
        sta = network.WLAN(network.STA_IF)
        sta.active(False)
    except Exception:
        pass
    time.sleep_ms(300)

    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.ifconfig((AP_IP, AP_SUBNET, AP_GATEWAY, AP_DNS))
    ap.config(essid=AP_SSID, password=AP_PASSWORD, authmode=3)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', 80))
    s.listen(2)

    while True:
        conn, addr = s.accept()
        try:
            _manejar_request(conn)
        except Exception:
            pass
        finally:
            conn.close()


def _manejar_request(conn):
    req = b''
    conn.settimeout(3)
    try:
        while True:
            chunk = conn.recv(1024)
            if not chunk:
                break
            req += chunk
            if len(chunk) < 1024:
                break
    except OSError:
        pass

    req = req.decode('utf-8', 'ignore')
    if not req:
        return

    primera_linea = req.split('\r\n', 1)[0]
    try:
        metodo, ruta, _ = primera_linea.split(' ')
    except ValueError:
        return

    if metodo == 'GET':
        _responder_pagina_principal(conn, mensaje='')

    elif metodo == 'POST' and ruta == '/guardar':
        partes = req.split('\r\n\r\n', 1)
        body   = partes[1] if len(partes) > 1 else ''
        datos  = _parse_form(body)
        ssid     = datos.get('ssid', '').strip()
        password = datos.get('password', '').strip()

        if ssid:
            agregar_red(ssid, password)
            mensaje = ('<div class="msg ok">Red "{}" guardada. '
                       'El dispositivo se reiniciara en 3 segundos...</div>'
                       ).format(_html_escape(ssid))
            _responder_pagina_principal(conn, mensaje=mensaje)
            time.sleep(3)
            machine.reset()
        else:
            mensaje = '<div class="msg err">SSID invalido. Intenta de nuevo.</div>'
            _responder_pagina_principal(conn, mensaje=mensaje)

    elif metodo == 'POST' and ruta == '/eliminar':
        partes = req.split('\r\n\r\n', 1)
        body   = partes[1] if len(partes) > 1 else ''
        datos  = _parse_form(body)
        ssid   = datos.get('ssid', '').strip()

        if ssid:
            eliminar_red(ssid)
            mensaje = ('<div class="msg ok">Red "{}" eliminada.</div>'
                       ).format(_html_escape(ssid))
        else:
            mensaje = '<div class="msg err">No se pudo eliminar.</div>'

        _responder_pagina_principal(conn, mensaje=mensaje)

    else:
        _responder_html(conn, '<h1>404 - No encontrado</h1>', status='404 Not Found')


def _responder_pagina_principal(conn, mensaje):
    html = PAGINA_PRINCIPAL.format(
        mensaje=mensaje,
        tabla_redes=_generar_tabla_redes()
    )
    _responder_html(conn, html)


def _responder_html(conn, html, status='200 OK'):
    respuesta = (
        'HTTP/1.1 {}\r\n'
        'Content-Type: text/html; charset=utf-8\r\n'
        'Content-Length: {}\r\n'
        'Connection: close\r\n\r\n{}'
    ).format(status, len(html), html)
    conn.send(respuesta.encode('utf-8'))
