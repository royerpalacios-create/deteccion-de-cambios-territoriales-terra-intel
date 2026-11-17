"""Servidor HTTP local de teselas falsas, para probar el mapa sin internet.

Genera teselas PNG de 256×256 con su ``z/x/y`` dibujado y cuenta las peticiones.
Comportamientos de prueba: z == 0 -> 404; y == 7 -> «imagen» que en realidad es HTML.
"""
from __future__ import annotations

import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageDraw


def png_tesela(z: int, x: int, y: int) -> bytes:
    tono = 70 + (x * 37 + y * 53) % 120
    img = Image.new("RGB", (256, 256), (tono, 110 + (x * 11) % 90, 140 + (y * 17) % 90))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 255, 255], outline=(255, 255, 255))
    d.text((8, 8), f"{z}/{x}/{y}", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class ServidorTeselas:
    def __init__(self) -> None:
        self.peticiones: list[str] = []
        servidor = self

        class Manejador(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                servidor.peticiones.append(self.path)
                partes = self.path.strip("/").replace(".png", "").split("/")
                try:
                    z, x, y = (int(v) for v in partes)
                except ValueError:
                    self.send_error(400)
                    return
                if z == 0:
                    self.send_error(404)
                    return
                cuerpo = b"<html>error</html>" if y == 7 else png_tesela(z, x, y)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            def log_message(self, *args):
                pass

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self.url = f"http://127.0.0.1:{self._http.server_address[1]}/{{z}}/{{x}}/{{y}}.png"
        self._hilo = threading.Thread(target=self._http.serve_forever, daemon=True)

    def __enter__(self) -> "ServidorTeselas":
        self._hilo.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._http.shutdown()
        self._http.server_close()
