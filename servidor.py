"""Háblale al recepcionista desde el navegador. El MVP, sin teléfono.

    python3 servidor.py --negocio peluqueria
    → http://localhost:8080

Es el producto entero funcionando salvo la última pata: entra voz, sale voz, y
queda el aviso registrado. Lo único que no hay es una línea telefónica, que es
la parte **conocida** y la única que cuesta dinero.

## Por qué esto es el MVP y no el spike de telefonía

Se puede enseñar. Una peluquería no entiende «tengo el pipeline montado»;
entiende que le hables al móvil y que una voz le diga el precio y le tome la
cita. Esto es eso, y no cuesta un euro.

Y mide lo que importa en condiciones reales: **cuánto tarda en contestar**. Con
el teléfono solo se le suma la red del proveedor, que es lo previsible.

## Sin modelos instalados también funciona

`--sin-voz` deja la página en modo texto: escribes y contesta escribiendo. Sirve
para probar el recepcionista **hoy**, antes de instalar nada. Instalar Whisper y
Piper lo convierte en voz sin tocar una línea.

## Desde el móvil

El navegador **no da micrófono sin HTTPS** salvo en `localhost`. Así que desde
el móvil por IP no va a funcionar, y no es un fallo: es la política del
navegador.

La salida limpia es `tailscale serve`, que pone HTTPS de verdad sobre la red
Tailscale **sin abrir nada en el router** —es una conexión de salida, no un
puerto expuesto a internet—:

    tailscale serve --bg 8080

## Lo que esto NO es

Un servidor de producción. `http.server` es de la librería estándar y atiende
de uno en uno. Para una demo y para medir sobra; para atender llamadas de
verdad, no. Se cambia cuando exista la telefonía, que es cuando importará.
"""

import argparse
import base64
import errno
import json
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import avisos
import negocio as negocios
import recepcion
import voz

# Cada navegador graba en lo suyo: Chrome y Firefox en webm, **Safari en iOS
# en mp4**. Antes esto se escribia siempre como `.webm`, asi que una llamada
# desde el movil llegaba como un mp4 con nombre de webm. El decodificador
# suele olfatear el contenido y salir del paso, pero no siempre, y cuando no
# lo hace el sintoma es «no le he oido» sin ninguna pista de por que.
EXTENSIONES = {"audio/webm": ".webm", "audio/mp4": ".m4a", "audio/mpeg": ".mp3",
               "audio/ogg": ".ogg", "audio/wav": ".wav", "audio/x-wav": ".wav",
               "audio/aac": ".aac", "audio/flac": ".flac"}


def _extension(tipo: str) -> str:
    """La extension que le toca a un Content-Type. `.webm` si no se reconoce."""
    return EXTENSIONES.get(tipo.split(";")[0].strip().lower(), ".webm")

RAIZ = Path(__file__).resolve().parent
PAGINA = RAIZ / "web" / "index.html"

# Tope de subida: unos segundos de voz no pasan de aquí. Sin tope, cualquiera
# tumba el proceso mandando un fichero de un giga.
TOPE_AUDIO = 10 * 1024 * 1024
# Hasta cuánto se traga para poder contestar 413 en condiciones. Rechazar sin
# vaciar el cuerpo deja al cliente con la conexión rota en vez de con un error
# que entienda —y eso se ve como «el servidor no responde», que es lo peor que
# puede parecer—. Pasado esto se cierra: no vale la pena tragarse un giga solo
# por ser educado.
TOPE_VACIADO = 4 * TOPE_AUDIO


class Recepcion(BaseHTTPRequestHandler):
    negocio = None
    transcriptor = None
    locutor = None

    def log_message(self, formato, *args):
        # El log por defecto ensucia la medición de tiempos con una línea por
        # petición de icono. Solo se dice lo que importa, desde atender().
        pass

    def _vaciar(self, cuantos: int) -> None:
        """Se traga el cuerpo a trozos para poder contestar antes de cerrar."""
        while cuantos > 0:
            trozo = self.rfile.read(min(cuantos, 64 * 1024))
            if not trozo:
                return
            cuantos -= len(trozo)

    def _responder(self, codigo: int, cuerpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            pagina = PAGINA.read_text(encoding="utf-8")
            pagina = pagina.replace("{{NEGOCIO}}", self.negocio.nombre)
            pagina = pagina.replace("{{SALUDO_JSON}}", json.dumps(self.negocio.saludo, ensure_ascii=False))
            pagina = pagina.replace("{{MODO}}", "texto" if self.transcriptor is None else "voz")
            return self._responder(200, pagina.encode("utf-8"), "text/html; charset=utf-8")
        self._responder(404, b"no hay nada aqui", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path != "/hablar":
            return self._responder(404, b"no hay nada aqui", "text/plain; charset=utf-8")

        largo = int(self.headers.get("Content-Length") or 0)
        if largo > TOPE_AUDIO:
            self._vaciar(min(largo, TOPE_VACIADO))
            self.close_connection = True
            return self._responder(413, b'{"error":"audio demasiado grande"}',
                                   "application/json; charset=utf-8")
        cuerpo = self.rfile.read(largo)

        try:
            resultado = self._atender(cuerpo)
        except Exception as error:  # noqa: BLE001 — aquí abajo hay modelos y disco
            # Un fallo NO deja la llamada sin rastro: es la regla de avisos.py.
            avisos.registrar("fallo", f"El servidor no pudo atender: {error}")
            resultado = {"oido": "", "dicho": "Ha habido un problema. Inténtelo otra vez.",
                         "audio": None, "error": str(error)}
        self._responder(200, json.dumps(resultado, ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8")

    def _atender(self, cuerpo: bytes) -> dict:
        tipo = self.headers.get("Content-Type", "")
        if tipo.startswith("application/json"):
            oido = json.loads(cuerpo or b"{}").get("texto", "").strip()
        else:
            if self.transcriptor is None:
                raise RuntimeError("el servidor está en modo texto: arráncalo sin --sin-voz")
            with tempfile.NamedTemporaryFile(suffix=_extension(tipo), delete=False) as entrada:
                entrada.write(cuerpo)
                ruta = Path(entrada.name)
            try:
                oido = voz.escuchar(ruta, self.transcriptor)
            finally:
                ruta.unlink(missing_ok=True)

        if not oido:
            return {"oido": "", "dicho": "No le he oído. ¿Me lo repite?", "audio": None}

        respuesta = recepcion.atender(oido, self.negocio.conocimiento)
        if respuesta.aviso:
            avisos.registrar(respuesta.tipo_aviso, respuesta.aviso)
        print(f"🎙️  {oido}\n  → {respuesta.texto}", flush=True)

        audio = None
        if self.locutor is not None:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as salida:
                ruta = Path(salida.name)
            try:
                if voz.hablar(respuesta.texto, ruta, self.locutor):
                    audio = base64.b64encode(ruta.read_bytes()).decode("ascii")
            except Exception as error:  # noqa: BLE001 — el motor de voz es de fuera
                avisos.registrar("fallo", f"No se pudo sintetizar: {error}")
            finally:
                ruta.unlink(missing_ok=True)
        return {"oido": oido, "dicho": respuesta.texto, "audio": audio}


def main() -> int:
    parser = argparse.ArgumentParser(description="El recepcionista, en el navegador")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--puerto", type=int, default=8080)
    parser.add_argument("--sin-voz", action="store_true",
                        help="modo texto: sin Whisper ni Piper, para probar sin instalar nada")
    args = parser.parse_args()

    try:
        Recepcion.negocio = negocios.cargar(args.negocio)
    except FileNotFoundError as error:
        print(f"❌ {error}")
        return 1

    faltan = __import__("conocimiento").que_falta(Recepcion.negocio.conocimiento)
    if faltan:
        print(f"⚠️  {Recepcion.negocio.nombre}: sin rellenar {', '.join(faltan)}")

    if not args.sin_voz:
        Recepcion.transcriptor, Recepcion.locutor = voz.Whisper(), voz.Piper()

    try:
        servidor = HTTPServer(("0.0.0.0", args.puerto), Recepcion)
    except OSError as error:
        if error.errno != errno.EADDRINUSE:
            raise
        # Casi siempre es un servidor.py anterior que se quedo vivo. El
        # traceback de socketserver no lo dice, y es lo unico que hace falta.
        print(f"❌ El puerto {args.puerto} ya esta ocupado.")
        print("   Casi siempre es otro servidor.py que se quedo corriendo.")
        print(f"   Quien lo tiene:  ss -ltnp | grep :{args.puerto}")
        print("   Matarlo:         pkill -f servidor.py")
        print(f"   U otro puerto:   python3 servidor.py --puerto {args.puerto + 1}")
        return 1

    modo = "TEXTO (sin modelos)" if args.sin_voz else "VOZ"
    print(f"{Recepcion.negocio.nombre} · modo {modo}")
    print(f"→ http://localhost:{args.puerto}")
    if not args.sin_voz:
        print("   Desde el móvil hace falta HTTPS: tailscale serve --bg "
              f"{args.puerto}")
    print("   Ctrl+C para parar.\n")

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nHasta luego.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
