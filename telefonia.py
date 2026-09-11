"""La llamada de verdad: un numero de telefono que entra por un webhook.

## Como entra una llamada

Un proveedor de telefonia (Twilio, o cualquiera que hable TwiML, como Telnyx)
recibe la llamada en tu numero y hace un POST a este servidor. Se le
contesta con un XML que dice que hacer: decir algo, escuchar, colgar.

    POST /telefono/entrada   suena el telefono → saludo + escuchar
    POST /telefono/turno     lo que dijo el cliente (ya transcrito) → contestar + escuchar
    POST /telefono/fin       la llamada ha terminado → apuntar en que quedo

**Aqui no se usan Whisper ni Piper.** El proveedor transcribe (`Gather
input="speech"`) y sintetiza (`Say`) en su lado, y eso tiene dos
consecuencias que hay que decir enteras:

1. **Va rapido.** Medido en la maquina de casa, Whisper `small` tarda casi
   tres segundos en oir una frase; el proveedor tarda decimas. Para el
   telefono, donde un silencio de dos segundos ya es «¿hola?», es la
   diferencia entre servir y no servir.
2. **El audio pasa por el proveedor.** Pero eso pasa con cualquier numero de
   telefono: quien te da la linea oye la linea. Lo que se decide aqui no es
   si el audio sale de casa —sale en cuanto hay un numero— sino que la
   **conversacion, los precios y la agenda** siguen siendo de aqui. Ni una
   palabra de lo que se le dice al cliente la pone el proveedor.

## Cada llamada es su conversacion

Pueden entrar dos a la vez. Se llevan por el `CallSid` que manda el
proveedor, no como la pagina del navegador, que es una sola.

## Nadie que no sea el proveedor puede hablar con esto

El webhook tiene que ser publico para que el proveedor llegue, y publico
quiere decir que llega cualquiera. Cada peticion trae una firma HMAC hecha
con el token secreto del proveedor; se comprueba y lo que no la trae, o la
trae mal, se contesta con un 403 sin mirar nada mas. Sin token en `.env` el
webhook **no arranca**: antes que abierto, apagado.

## Como llega el proveedor hasta Madre

En el router no se abre nada (CONTEXT.md, decision 8). `tailscale funnel`
publica un puerto en internet por una conexion de salida:

    tailscale funnel --bg 8081
    → https://<maquina>.<tailnet>.ts.net/telefono/entrada

**El 8081, no el 8080.** El 8080 es la demo del navegador y no puede salir a
internet: `/hablar` arranca Whisper con el audio que le manden y `/colgar`
escribe en la agenda. El 8081 sirve solo `/telefono/*`, y por eso es el
unico que se publica. `make funnel` publica el que toca y se niega a hacerlo
si no hay token.
"""

import base64
import hashlib
import hmac
import os
import re
import threading
import time
from html import escape
from pathlib import Path
from urllib.parse import parse_qs

import almacen
import avisar
import avisos
import fechas
import recepcion
import voz as voz_

RAIZ = Path(__file__).resolve().parent
VOZ_POR_DEFECTO = "Polly.Lucia"      # castellano de España, en el proveedor
IDIOMA = "es-ES"
ESQUEMA_CLIENTES = 1
_LOCK = threading.Lock()


def configuracion() -> dict | None:
    """Token del proveedor y voz. None si no hay token: entonces no hay webhook."""
    avisar._leer_env()
    token = os.environ.get("GJALLARHORN_TELEFONO_TOKEN", "").strip()
    if not token:
        return None
    return {"token": token,
            "voz": os.environ.get("GJALLARHORN_TELEFONO_VOZ", "").strip() or VOZ_POR_DEFECTO}


# ---- la firma ------------------------------------------------------------

def firma_valida(token: str, url: str, campos: dict[str, str], firma: str | None) -> bool:
    """La firma del proveedor: HMAC-SHA1 de la URL + los campos ordenados.

    Es el esquema de Twilio (X-Twilio-Signature). Se compara en tiempo
    constante: comparar con `==` deja medir cuanto de la firma acerto.
    """
    if not firma:
        return False
    base = url + "".join(k + campos[k] for k in sorted(campos))
    esperada = base64.b64encode(
        hmac.new(token.encode("utf-8"), base.encode("utf-8"), hashlib.sha1).digest()
    ).decode("ascii")
    return hmac.compare_digest(esperada, firma)


# ---- los clientes que ya han llamado -----------------------------------

def _ruta_clientes() -> Path:
    valor = os.environ.get("GJALLARHORN_DATOS", "").strip()
    base = Path(valor).expanduser() if valor else RAIZ / "datos"
    return base / "clientes.json"


def cliente(numero: str) -> dict | None:
    """Lo que se sabe de quien llama desde ese numero, o None si es la primera vez."""
    return almacen.cargar(_ruta_clientes(), ESQUEMA_CLIENTES, vacio={}).get(numero)


def recordar_cliente(numero: str, nombre: str | None) -> None:
    """Apunta el nombre y una llamada mas. Solo si dio el nombre: sin el no hay nada que recordar."""
    if not numero or not nombre:
        return
    with _LOCK:
        todos = almacen.cargar(_ruta_clientes(), ESQUEMA_CLIENTES, vacio={})
        antes = todos.get(numero, {})
        todos[numero] = {"nombre": nombre, "llamadas": antes.get("llamadas", 0) + 1,
                         "ultima": fechas.hoy()}
        almacen.guardar(_ruta_clientes(), todos, ESQUEMA_CLIENTES)


# ---- TwiML ---------------------------------------------------------------

def _twiml(*trozos: str) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(trozos) + "</Response>"


def _decir(texto: str, voz: str) -> str:
    # Lo que se lee en voz alta no es lo que se escribe: «45 €» → «45 euros».
    return (f'<Say voice="{escape(voz, quote=True)}" language="{IDIOMA}">'
            f'{escape(voz_.para_decir(texto))}</Say>')


def _escuchar(texto: str, voz: str, accion: str) -> str:
    """Decir algo y quedarse escuchando; lo que se oiga llega a `accion`."""
    return (f'<Gather input="speech" language="{IDIOMA}" speechTimeout="auto" '
            f'action="{escape(accion, quote=True)}" method="POST">'
            f'{_decir(texto, voz)}</Gather>'
            # Si no dice nada, se le pregunta una vez mas y se cuelga.
            f'<Redirect method="POST">{escape(accion, quote=True)}?silencio=1</Redirect>')


def _colgar(texto: str, voz: str) -> str:
    return _decir(texto, voz) + "<Hangup/>"


# ---- las llamadas en curso ------------------------------------------------

class Centralita:
    """Las conversaciones abiertas, una por llamada, y lo que se contesta en cada paso."""

    # Una llamada de telefono no dura dos horas. Lo que siga vivo despues de
    # eso es una llamada que acabo y de la que nunca llego el aviso.
    CADUCA = 2 * 60 * 60

    def __init__(self, negocio, voz: str = VOZ_POR_DEFECTO, ahora=None):
        self.negocio = negocio
        self.voz = voz
        self._ahora = ahora
        self._llamadas: dict[str, recepcion.Conversacion] = {}
        self._numeros: dict[str, str] = {}
        self._empezadas: dict[str, float] = {}

    def ahora(self) -> float:
        return self._ahora() if self._ahora else time.monotonic()

    def _barrer(self) -> list[str]:
        """Cierra las llamadas que llevan demasiado abiertas. Cuáles ha cerrado.

        `/telefono/fin` es lo que limpia una llamada, y **nada garantiza que
        llegue**: lo tiene que llamar el proveedor, y solo lo hace si alguien
        lo configuró. Sin esto, cada llamada que se cae deja su conversación
        en memoria para siempre y su cita a medias sin apuntar, que es
        justamente lo que no puede pasar aquí.
        """
        limite = self.ahora() - self.CADUCA
        viejas = [sid for sid, cuando in self._empezadas.items() if cuando < limite]
        for sid in viejas:
            self.fin({"CallSid": sid})
        return viejas

    def entrada(self, campos: dict[str, str], ruta_turno: str) -> str:
        """Suena el telefono: saludo y a escuchar."""
        self._barrer()
        sid, numero = campos.get("CallSid", ""), campos.get("From", "")
        with _LOCK:
            self._llamadas[sid] = recepcion.conversacion_de(self.negocio)
            self._numeros[sid] = numero
            self._empezadas[sid] = self.ahora()
        saludo = self.negocio.saludo
        if (conocido := cliente(numero)) is not None:
            # Se le saluda por su nombre y la conversacion ya lo sabe: no se
            # le vuelve a preguntar «¿a nombre de quien?».
            self._llamadas[sid].nombre = conocido["nombre"]
            saludo = f"Hola, {conocido['nombre']}. {saludo}"
        avisos.registrar("llamada", f"Llamada de {numero or 'número oculto'}"
                         + (f" ({conocido['nombre']})" if conocido else ""))
        return _twiml(_escuchar(saludo, self.voz, ruta_turno))

    def turno(self, campos: dict[str, str], ruta_turno: str, silencio: bool = False) -> str:
        """Lo que dijo el cliente, ya transcrito por el proveedor. Se contesta y se sigue."""
        sid = campos.get("CallSid", "")
        llamada = self._llamadas.get(sid)
        if llamada is None:
            # Un turno de una llamada que no empezo por /entrada (reinicio del
            # servidor a mitad): se abre sobre la marcha en vez de colgar.
            llamada = self._llamadas[sid] = recepcion.conversacion_de(self.negocio)
            self._numeros[sid] = campos.get("From", "")
            self._empezadas[sid] = self.ahora()

        dicho = (campos.get("SpeechResult") or "").strip()
        if not dicho:
            if silencio:
                return _twiml(_colgar(self.negocio.despedida, self.voz))
            return _twiml(_escuchar(llamada.frases.decir("no_le_oigo"), self.voz, ruta_turno))

        respuesta = llamada.atender(dicho)
        if respuesta.aviso:
            avisos.registrar(respuesta.tipo_aviso, respuesta.aviso)
            avisar.en_segundo_plano()
        print(f"☎️  {dicho}\n  → {respuesta.texto}", flush=True)

        if llamada.frases.reconoce("colgar", recepcion._sin_tildes(dicho)) \
                or respuesta.texto == llamada.frases.decir("despedida"):
            return _twiml(_colgar(respuesta.texto, self.voz))
        return _twiml(_escuchar(respuesta.texto, self.voz, ruta_turno))

    def fin(self, campos: dict[str, str]) -> str | None:
        """La llamada ha terminado: apuntar en que quedo y recordar al cliente."""
        sid = campos.get("CallSid", "")
        with _LOCK:
            llamada = self._llamadas.pop(sid, None)
            numero = self._numeros.pop(sid, "")
            self._empezadas.pop(sid, None)
        if llamada is None:
            return None
        recordar_cliente(numero, llamada.nombre)
        quedo = llamada.colgar()
        if quedo:
            avisar.en_segundo_plano()
        return quedo


# ---- lo que entra por HTTP ---------------------------------------------

def campos_de(cuerpo: bytes) -> dict[str, str]:
    """El formulario del proveedor (x-www-form-urlencoded) como dict de cadenas."""
    return {k: v[0] for k, v in parse_qs(cuerpo.decode("utf-8", "replace"),
                                         keep_blank_values=True).items()}


RUTAS = re.compile(r"^/telefono/(entrada|turno|fin)(\?.*)?$")


def _solo_texto(xml: str) -> str:
    """Lo que diria la voz, sacado del TwiML. Para leerlo en una terminal."""
    import html
    return " ".join(html.unescape(t) for t in re.findall(r"<Say[^>]*>(.*?)</Say>", xml, re.S))


def main() -> int:
    """`python3 telefonia.py --simular`: una llamada entera por la terminal.

    Sin proveedor ni numero: se hace de proveedor, mandando los formularios
    que mandaria Twilio y leyendo el TwiML que se le devuelve. Si hay token
    en .env, ademas imprime un `curl` firmado contra el servidor local para
    probar el webhook de verdad, firma incluida, antes de pagar por un numero.
    """
    import argparse
    import sys as _sys

    import negocio as negocios

    parser = argparse.ArgumentParser(description="El telefono, sin telefono")
    parser.add_argument("--simular", action="store_true", help="una llamada por teclado")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--numero", default="+34600000000", help="desde que numero se llama")
    parser.add_argument("--puerto", type=int, default=8081)
    args = parser.parse_args()

    n = negocios.cargar(args.negocio)
    config = configuracion()
    if not args.simular:
        parser.print_help()
        return 0

    centralita = Centralita(n, (config or {}).get("voz", VOZ_POR_DEFECTO))
    sid = "SIMULADA"
    turno = f"https://localhost:{args.puerto}/telefono/turno"
    print(f"☎️  Llamada simulada desde {args.numero}. Escribe lo que dirias; vacio = cuelgas.\n")
    print(f"  🔊 {_solo_texto(centralita.entrada({'CallSid': sid, 'From': args.numero}, turno))}")
    for linea in _sys.stdin:
        dicho = linea.strip()
        if not dicho:
            break
        xml = centralita.turno({"CallSid": sid, "From": args.numero, "SpeechResult": dicho}, turno)
        print(f"  🔊 {_solo_texto(xml)}")
        if "<Hangup/>" in xml:
            break
    quedo = centralita.fin({"CallSid": sid})
    print(f"\n📞 Colgado. {('Apuntado: ' + quedo) if quedo else 'Nada que apuntar.'}")

    if config:
        campos = {"CallSid": "CAprueba", "From": args.numero}
        url = f"https://localhost:{args.puerto}/telefono/entrada"
        firma = base64.b64encode(hmac.new(
            config["token"].encode(), (url + "".join(k + campos[k] for k in sorted(campos))).encode(),
            hashlib.sha1).digest()).decode()
        datos = "&".join(f"{k}={v}" for k, v in campos.items())
        print("\nCon el servidor arrancado (make arrancar), esto prueba el webhook real, firma incluida:")
        print(f"  curl -s -X POST http://127.0.0.1:{args.puerto}/telefono/entrada "
              f"-H 'Host: localhost:{args.puerto}' -H 'X-Forwarded-Proto: https' "
              f"-H 'X-Twilio-Signature: {firma}' -d '{datos}'")
        print("  → tiene que devolver un <Response> con <Gather>. Sin la cabecera de firma, 403.")
    else:
        print("\nSin GJALLARHORN_TELEFONO_TOKEN en .env: el webhook no arranca. Ponlo y repite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
