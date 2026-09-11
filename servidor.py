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

## Dos puertos, y la diferencia es de seguridad

    8080  la demo: la página, /hablar, /colgar   → tailscale serve (solo tu tailnet)
    8081  solo /telefono/*                        → tailscale funnel (internet)

El webhook del proveedor tiene que ser alcanzable desde internet. La demo
**no puede serlo**: `/hablar` arranca Whisper con el audio que le manden y
`/colgar` escribe en la agenda de un negocio real. Publicar un solo puerto
con las dos cosas dentro abre lo segundo para conseguir lo primero.

Por eso son dos servidores con **dos tablas de rutas distintas**. Que la demo
no salga a internet no depende de mirar una cabecera ni de confiar en
Tailscale: depende de que el puerto que se publica no sabe servirla.

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
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import avisar
import avisos
import frases
import negocio as negocios
import recepcion
import telefonia
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


class Comun(BaseHTTPRequestHandler):
    """Lo que comparten los dos puertos. No se sirve por si solo."""

    negocio = None
    transcriptor = None
    locutor = None
    conversacion = None   # la llamada en curso; se reinicia en /colgar
    centralita = None     # telefonia.Centralita si hay token; si no, sin webhook
    config_telefono = None

    @classmethod
    def charla(cls) -> "recepcion.Conversacion":
        """La llamada en curso. Se crea sola si hace falta."""
        if cls.conversacion is None:
            cls.conversacion = recepcion.conversacion_de(cls.negocio)
        return cls.conversacion

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
        try:
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
        except (BrokenPipeError, ConnectionResetError):
            # Quien llamaba ya no esta: Safari cierra la conexion al colgar o
            # al recargar antes de leer la respuesta. No es un fallo nuestro
            # y un traceback de veinte lineas por cada colgado tapa los de
            # verdad.
            self.close_connection = True

    def _telefono(self) -> None:
        """El webhook del proveedor de telefonia. Firmado o nada."""
        if self.centralita is None:
            return self._responder(404, b"sin telefonia configurada", "text/plain; charset=utf-8")
        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(min(largo, TOPE_AUDIO))
        campos = telefonia.campos_de(cuerpo)

        # La URL que firmo el proveedor es la publica, con esquema y host.
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host", "")
        esquema = self.headers.get("X-Forwarded-Proto", "https")
        url = f"{esquema}://{host}{self.path}"
        if not telefonia.firma_valida(self.config_telefono["token"], url, campos,
                                      self.headers.get("X-Twilio-Signature")):
            avisos.registrar("fallo", f"Petición al webhook de teléfono con firma mala desde {self.client_address[0]}")
            return self._responder(403, b"firma no valida", "text/plain; charset=utf-8")

        ruta, _, consulta = self.path.partition("?")
        ruta_turno = f"{esquema}://{host}/telefono/turno"
        if ruta.endswith("/entrada"):
            xml = self.centralita.entrada(campos, ruta_turno)
        elif ruta.endswith("/turno"):
            xml = self.centralita.turno(campos, ruta_turno, silencio="silencio=1" in consulta)
        else:
            self.centralita.fin(campos)
            xml = telefonia._twiml()
        self._responder(200, xml.encode("utf-8"), "text/xml; charset=utf-8")

    def _es_de_internet(self) -> bool:
        """¿Ha entrado por Funnel, o sea desde fuera del tailnet?

        Tailscale marca asi lo que llega de internet. **No es de lo que
        depende la separacion** —para eso estan los dos puertos— pero si
        alguien publica el puerto de la demo por error, esto lo para igual.
        """
        return bool(self.headers.get("Tailscale-Funnel-Request"))


class Telefono(Comun):
    """El puerto publico: **solo** el webhook del proveedor. Nada mas.

    Este es el unico que se publica en internet (`tailscale funnel`). Que la
    demo no sea alcanzable desde fuera no depende de mirar una cabecera ni de
    confiar en Tailscale: depende de que en la tabla de rutas de este puerto
    **no existen** `/`, `/hablar` ni `/colgar`. Un puerto no puede servir lo
    que no sabe servir.

    Y aun asi, lo que entra por aqui va firmado con el token del proveedor.
    Dos cerraduras distintas para la misma puerta, a proposito.
    """

    def do_GET(self):
        # Ni siquiera la pagina: por aqui solo habla una maquina.
        self._responder(404, b"no hay nada aqui", "text/plain; charset=utf-8")

    def do_POST(self):
        if not telefonia.RUTAS.match(self.path):
            return self._responder(404, b"no hay nada aqui", "text/plain; charset=utf-8")
        self._telefono()


class Recepcion(Comun):
    """El puerto de la demo: la pagina y el navegador. **Nunca se publica.**

    Va detras de `tailscale serve`, que solo lo ve tu tailnet. Aqui hay cosas
    que no pueden estar abiertas a internet: `/hablar` arranca Whisper con el
    audio que le manden y `/colgar` reserva en la agenda.
    """

    def do_GET(self):
        if self._es_de_internet():
            return self._responder(404, b"no hay nada aqui", "text/plain; charset=utf-8")
        if self.path in ("/", "/index.html"):
            pagina = PAGINA.read_text(encoding="utf-8")
            pagina = pagina.replace("{{NEGOCIO}}", self.negocio.nombre)
            pagina = pagina.replace("{{SALUDO_JSON}}", json.dumps(self.negocio.saludo, ensure_ascii=False))
            pagina = pagina.replace("{{MODO}}", "texto" if self.transcriptor is None else "voz")
            return self._responder(200, pagina.encode("utf-8"), "text/html; charset=utf-8")
        self._responder(404, b"no hay nada aqui", "text/plain; charset=utf-8")

    def do_POST(self):
        if self._es_de_internet():
            return self._responder(404, b"no hay nada aqui", "text/plain; charset=utf-8")
        if self.path == "/colgar":
            # Colgar apunta en que quedo la llamada y empieza otra de cero.
            # Sin esto, la segunda prueba hereda la cita a medias de la
            # primera y contesta cosas que no vienen a cuento.
            quedo = self.charla().colgar()
            Comun.conversacion = recepcion.conversacion_de(self.negocio)
            if quedo:
                avisar.en_segundo_plano()
            return self._responder(
                200, json.dumps({"colgado": quedo}, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8")
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

        # La misma conversación mientras dure la llamada: es lo que hace que
        # «el jueves» y «a las cinco» signifiquen algo dos turnos despues.
        respuesta = self.charla().atender(oido)
        if respuesta.aviso:
            avisos.registrar(respuesta.tipo_aviso, respuesta.aviso)
            avisar.en_segundo_plano()
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


def _abrir(puerto: int, handler, que: str, bandera: str) -> "HTTPServer | None":
    """Un servidor en un puerto, o None diciendo por que no se pudo."""
    try:
        return HTTPServer(("0.0.0.0", puerto), handler)
    except OSError as error:
        if error.errno != errno.EADDRINUSE:
            raise
        # Casi siempre es un servidor.py anterior que se quedo vivo. El
        # traceback de socketserver no lo dice, y es lo unico que hace falta.
        print(f"❌ El puerto {puerto} ({que}) ya esta ocupado.")
        print("   Casi siempre es otro servidor.py que se quedo corriendo.")
        print(f"   Quien lo tiene:  ss -ltnp | grep :{puerto}")
        print("   Matarlo:         pkill -f servidor.py")
        print(f"   U otro puerto:   python3 servidor.py {bandera} {puerto + 1}")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="El recepcionista, en el navegador")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--puerto", type=int, default=8080,
                        help="la demo del navegador. NO se publica: tailscale serve")
    parser.add_argument("--puerto-telefono", type=int, default=8081,
                        help="solo el webhook del proveedor. Es el que se publica")
    parser.add_argument("--sin-voz", action="store_true",
                        help="modo texto: sin Whisper ni Piper, para probar sin instalar nada")
    parser.add_argument("--sin-telefono", action="store_true",
                        help="no levantar el puerto del teléfono aunque haya token")
    args = parser.parse_args()

    try:
        Comun.negocio = negocios.cargar(args.negocio)
    except (FileNotFoundError, ValueError) as error:
        print(f"❌ {error}")
        return 1
    Comun.conversacion = recepcion.conversacion_de(Comun.negocio)
    if Comun.negocio.horario is None:
        print("⚠️  sin [horario] en negocio.toml: se toma nota, no se reserva")

    faltan = __import__("conocimiento").que_falta(Comun.negocio.conocimiento)
    if faltan:
        print(f"⚠️  {Comun.negocio.nombre}: sin rellenar {', '.join(faltan)}")
    for problema in frases.problemas(Comun.negocio.conocimiento):
        print(f"⚠️  frases.toml: {problema}")
    if avisar.configuracion() is None:
        print("ℹ️  sin Telegram: las citas y recados se quedan en avisos.json "
              "(python3 avisar.py explica cómo configurarlo)")

    Comun.config_telefono = None if args.sin_telefono else telefonia.configuracion()
    if Comun.config_telefono is not None:
        Comun.centralita = telefonia.Centralita(Comun.negocio,
                                                Comun.config_telefono["voz"])

    if not args.sin_voz:
        Comun.transcriptor, Comun.locutor = voz.Whisper(), voz.Piper()

    demo = _abrir(args.puerto, Recepcion, "la demo", "--puerto")
    if demo is None:
        return 1
    telefono = None
    if Comun.config_telefono is not None:
        telefono = _abrir(args.puerto_telefono, Telefono, "el teléfono", "--puerto-telefono")
        if telefono is None:
            demo.server_close()
            return 1

    modo = "TEXTO (sin modelos)" if args.sin_voz else "VOZ"
    print(f"{Comun.negocio.nombre} · modo {modo}")
    print(f"→ http://localhost:{args.puerto}   (la demo)")
    if not args.sin_voz:
        print(f"   Desde el móvil: tailscale serve --bg {args.puerto}   ← solo tu tailnet")
    if telefono is not None:
        print(f"☎️  webhook en :{args.puerto_telefono}/telefono/entrada")
        print(f"   Para que lo alcance el proveedor: tailscale funnel --bg {args.puerto_telefono}")
        print("   Se publica ESTE puerto y no el de la demo, a propósito.")
    else:
        print("ℹ️  sin teléfono: no hay webhook "
              "(GJALLARHORN_TELEFONO_TOKEN en .env lo enciende)")
    print("   Ctrl+C para parar.\n")

    if telefono is not None:
        threading.Thread(target=telefono.serve_forever, daemon=True).start()
    try:
        demo.serve_forever()
    except KeyboardInterrupt:
        print("\nHasta luego.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
