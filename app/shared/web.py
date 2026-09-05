"""Small non-blocking HTTP server for changing settings while the display runs.

The panel refreshes itself in hardware, so serving a page never disturbs the
image. The listening socket is polled from the main loop; a request is then
handled in one go with a short socket timeout, which costs a few milliseconds
of loop time and only while somebody is actually using the page.

Routes:
  GET  /          status and the settings form
  POST /          save the form (app/shared/config.py validates)
  GET/POST /on /off /toggle   switch the panel dark or bright (webhooks for a
                  HomeAssistant rest_command); the state is persisted
  GET  /status    the same state as JSON, for a HomeAssistant REST sensor
  POST /restart   reboot the board
  POST /reset     forget all overrides and reboot

There is no authentication: everybody on the network can change colours and
reboot the display. Credentials are not part of the editable options and are
never shown. Set WEB_ENABLED = False to switch the server off.
"""

import json
import select
import socket
import time

from app import settings
from app.shared import config

REQUEST_TIMEOUT_S = 1          # bounds how long one request can stall the main loop
LISTEN_RETRY_MS = 5000         # after a failed bind (e.g. port still in use)
MAX_BODY = 4096
REASONS = {"200": "OK", "303": "See Other", "404": "Not Found"}

STYLE = (
    "body{background:#111;color:#eee;font:15px system-ui,sans-serif;margin:0;padding:16px}"
    "h1{font-size:18px;margin:0 0 4px}"
    "h2{font-size:12px;color:#7ab;margin:20px 0 6px;letter-spacing:.08em;text-transform:uppercase}"
    "table{width:100%;border-collapse:collapse;max-width:520px}"
    "td{padding:5px 0;vertical-align:middle}td.l{color:#aaa;padding-right:10px}"
    "input,select{background:#222;color:#eee;border:1px solid #444;border-radius:5px;padding:7px;width:100%;box-sizing:border-box}"
    "input[type=checkbox]{width:auto}"
    "label{display:inline-block;margin:0 14px 4px 0;color:#ddd}"
    "button{background:#2a6496;color:#fff;border:0;border-radius:5px;padding:11px 16px;font-size:15px;margin:16px 8px 0 0}"
    "button.w{background:#8a3b3b}"
    "small{color:#888}"
    ".v{color:#9d9;font-variant-numeric:tabular-nums}"
)


def unquote(text):
    """Decode application/x-www-form-urlencoded text."""
    text = text.replace("+", " ")
    if "%" not in text:
        return text
    out = ""
    index = 0
    while index < len(text):
        char = text[index]
        if char == "%" and index + 2 < len(text):
            try:
                out += chr(int(text[index + 1:index + 3], 16))
                index += 3
                continue
            except ValueError:
                pass
        out += char
        index += 1
    return out


def parse_form(body):
    """Form body -> {key: value or [values]} (repeated keys become a list)."""
    values = {}
    for pair in body.split("&"):
        if not pair:
            continue
        key, _, raw = pair.partition("=")
        key = unquote(key)
        raw = unquote(raw)
        if key in values:
            if not isinstance(values[key], list):
                values[key] = [values[key]]
            values[key].append(raw)
        else:
            values[key] = raw
    return values


def esc(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


class WebServer:
    def __init__(self, widget_names, status_fn, state_fn):
        self.widget_names = tuple(widget_names)
        self.status_fn = status_fn      # (label, value) pairs for the page
        self.state_fn = state_fn        # dict for /status
        self.url = None
        self._socket = None
        self._poller = None
        self._next_listen = 0
        self._notice = ""

    # ------------------------------------------------------------------
    def service(self, now_ticks, ctx):
        if not settings.WEB_ENABLED:
            return
        if self._socket is None:
            if ctx.net.connected and time.ticks_diff(now_ticks, self._next_listen) >= 0:
                self._listen(ctx, now_ticks)
            return
        if not ctx.net.connected:
            self._close()
            return
        if self._poller.poll(0):
            self._handle()

    def _listen(self, ctx, now_ticks):
        self._next_listen = time.ticks_add(now_ticks, LISTEN_RETRY_MS)
        try:
            sock = socket.socket()
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", settings.WEB_PORT))
            sock.listen(1)
            sock.setblocking(False)
        except OSError as exc:
            print("web: cannot listen on port", settings.WEB_PORT, exc)
            return
        self._socket = sock
        self._poller = select.poll()
        self._poller.register(sock, select.POLLIN)
        port = "" if settings.WEB_PORT == 80 else ":%d" % settings.WEB_PORT
        self.url = "http://%s%s/" % (ctx.net.address or "?", port)
        print("web:", self.url)

    def _close(self):
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
        self._socket = None
        self._poller = None
        self.url = None

    # ------------------------------------------------------------------
    def _handle(self):
        try:
            conn, _ = self._socket.accept()
        except OSError:
            return
        try:
            conn.settimeout(REQUEST_TIMEOUT_S)
            method, path, body = self._read_request(conn)
            if method is None:
                return
            if path in ("/on", "/off", "/toggle"):
                state = True if path == "/on" else False if path == "/off" else not settings.DISPLAY_ON
                config.update({"DISPLAY_ON": state}, self.widget_names)
                print("web: display", "on" if state else "off")
                self._send(conn, "200", "on" if state else "off", content_type="text/plain")
                return
            if method == "GET" and path == "/status":
                self._send(conn, "200", json.dumps(self.state_fn()), content_type="application/json")
                return
            if method == "POST":
                # Only the known paths act; anything else must not be mistaken
                # for a form submission.
                if path == "/":
                    self._save(parse_form(body))
                    self._send(conn, "303", "", location="/")
                elif path == "/restart":
                    self._send(conn, "303", "", location="/")
                    self._reboot(conn)
                elif path == "/reset":
                    if not config.clear():
                        print("web: no overrides to remove")
                    self._send(conn, "303", "", location="/")
                    self._reboot(conn)
                else:
                    self._send(conn, "404", "<h1>404</h1>")
                return
            if path != "/":
                self._send(conn, "404", "<h1>404</h1>")
                return
            self._send_page(conn)
        except OSError as exc:
            print("web: request failed", exc)
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _read_request(self, conn):
        line = conn.readline()
        if not line:
            return None, None, ""
        parts = line.decode().split(" ")
        if len(parts) < 2:
            return None, None, ""
        method, path = parts[0], parts[1]
        path = path.split("?")[0]
        while path.startswith("//"):        # tolerate http://host//path
            path = path[1:]
        length = 0
        while True:
            header = conn.readline()
            if not header or header == b"\r\n":
                break
            text = header.decode().lower()
            if text.startswith("content-length:"):
                try:
                    length = int(text.split(":", 1)[1].strip())
                except ValueError:
                    length = 0
        if length > MAX_BODY:
            return None, None, ""
        body = b""
        while len(body) < length:
            chunk = conn.read(length - len(body))
            if not chunk:
                break
            body += chunk
        return method, path, body.decode()

    def _save(self, values):
        # An unchecked checkbox sends nothing, so absent booleans mean False.
        # Options outside the form (the power state) are never touched here.
        for option in config.OPTIONS:
            if option.form and option.kind == "bool" and option.key not in values:
                values[option.key] = False
        if "WIDGETS_ENABLED" not in values:
            values["WIDGETS_ENABLED"] = []
        changed, restart = config.update(values, self.widget_names)
        if not changed:
            self._notice = "Keine Aenderung."
        elif restart:
            self._notice = "%d Aenderung(en) gespeichert, fuer %s ist ein Neustart noetig." % (len(changed), ", ".join(restart))
        else:
            self._notice = "%d Aenderung(en) uebernommen." % len(changed)
        print("web: saved", changed)

    def _reboot(self, conn):
        import time

        import machine
        try:
            conn.close()
        except OSError:
            pass
        print("web: reboot requested")
        time.sleep_ms(200)
        machine.reset()

    # ------------------------------------------------------------------
    def _send(self, conn, status, body, location=None, content_type="text/html; charset=utf-8"):
        text = "HTTP/1.0 %s %s\r\nConnection: close\r\n" % (status, REASONS.get(status, "OK"))
        if location:
            text += "Location: %s\r\n" % location
        text += "Content-Type: %s\r\n\r\n" % content_type
        conn.write(text.encode())
        if body:
            conn.write(body.encode())

    def _send_page(self, conn):
        self._send(conn, "200", "")
        write = lambda text: conn.write(text.encode())
        write("<!DOCTYPE html><html lang=de><head><meta charset=utf-8>"
              "<meta name=viewport content='width=device-width,initial-scale=1'>"
              "<title>LED Display</title><style>%s</style></head><body>" % STYLE)
        write("<h1>LED Display</h1>")
        if self._notice:
            write("<small>%s</small>" % esc(self._notice))
            self._notice = ""

        write("<h2>Status</h2><table>")
        for label, value in self.status_fn():
            write("<tr><td class=l>%s</td><td class=v>%s</td></tr>" % (esc(label), esc(value)))
        write("</table>")

        write("<form method=post>")
        group = None
        for option in config.OPTIONS:
            if not option.form:
                continue
            if option.group != group:
                if group is not None:
                    write("</table>")
                group = option.group
                write("<h2>%s</h2><table>" % esc(group))
            write("<tr><td class=l>%s%s</td><td>%s</td></tr>"
                  % (esc(option.label), "" if option.live else " <small>(Neustart)</small>", self._field(option)))
        write("</table>")
        write("<button type=submit>Speichern</button></form>")
        if settings.DISPLAY_ON:
            write("<form method=post action=/off><button class=w>Display aus</button></form>")
        else:
            write("<form method=post action=/on><button>Display ein</button></form>")
        write("<form method=post action=/restart><button class=w>Neustart</button></form>")
        write("<form method=post action=/reset><button class=w>Werkseinstellungen</button></form>")
        write("</body></html>")

    def _field(self, option):
        value = getattr(settings, option.key, None)
        key = esc(option.key)
        if option.kind == "bool":
            return "<input type=checkbox name=%s%s>" % (key, " checked" if value else "")
        if option.kind == "color":
            parts = ["<select name=%s>" % key]
            for index, name in enumerate(config.COLOR_NAMES):
                parts.append("<option value=%d%s>%s</option>" % (index, " selected" if index == value else "", name))
            parts.append("</select>")
            return "".join(parts)
        if option.kind == "choice":
            parts = ["<select name=%s>" % key]
            for name in option.choices:
                parts.append("<option%s>%s</option>" % (" selected" if name == value else "", esc(name)))
            parts.append("</select>")
            return "".join(parts)
        if option.kind == "widgets":
            active = tuple(value or ())
            parts = []
            for name in self.widget_names:
                checked = " checked" if not active or name in active else ""
                parts.append("<label><input type=checkbox name=WIDGETS_ENABLED value=%s%s> %s</label>"
                             % (esc(name), checked, esc(name)))
            return "".join(parts)
        if option.kind == "float":
            return "<input type=number step=0.05 min=%s max=%s name=%s value=%s>" % (option.low, option.high, key, esc(value))
        if option.kind == "int":
            return "<input type=number step=1 min=%s max=%s name=%s value=%s>" % (option.low, option.high, key, esc(value))
        return "<input type=text name=%s value='%s'>" % (key, esc(value))
