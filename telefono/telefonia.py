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

from dueno import avisar
from hugin.guardado import avisos
from hugin.guardado import datos
from hugin.mente import memoria
from telefono import firmas
from hugin.mente import recepcion
from telefono import voz as voz_

RAIZ = Path(__file__).resolve().parent.parent
VOZ_POR_DEFECTO = "Polly.Lucia"      # castellano de España, en el proveedor
CABECERA_TWILIO = "X-Twilio-Signature"
CABECERA_TELNYX = "telnyx-signature-ed25519"
# SignalWire firma IGUAL que Twilio —el mismo HMAC sobre la URL y los campos,
# hasta el punto de que su propia libreria usa el validador de Twilio— pero
# manda la firma en su cabecera. Por eso aqui solo hay un nombre mas: no hay
# criptografia nueva que escribir, al contrario que con Telnyx.
CABECERA_SIGNALWIRE = "X-SignalWire-Signature"
CABECERA_MARCA_TELNYX = "telnyx-timestamp"
VENTANA_TELNYX = 300                 # 5 min, lo que recomienda Telnyx
IDIOMA = "es-ES"
_LOCK = threading.Lock()


def token_de_mentira(token: str) -> bool:
    """Un token que es el hueco del ejemplo sin rellenar, no un token.

    Pasa al copiar una linea de una guia con `<...>` dentro, o al dejarse el
    `pon-aqui-el-token`. Un token asi arranca el webhook igual, y luego cada
    llamada se cae con un 403 por firma no valida: el peor sitio para
    enterarse. Aqui se ve en un segundo.
    """
    sucio = token.strip()
    if not sucio:
        return False                                # eso es «no hay», no «de mentira»
    if "<" in sucio or ">" in sucio or " " in sucio:
        return True                                 # el `<...>` de una guia, pegado tal cual
    return sucio.lower() in {"xxx", "cambiame", "cambiar", "tu-token",
                             "tu_token", "pon-aqui-el-token", "pon_aqui_el_token"}


def configuracion() -> dict | None:
    """Con que se comprueban las llamadas, y con que voz se contesta.

    Vale una de las dos, o las dos:

    - `GJALLARHORN_TELEFONO_TOKEN`, el Auth Token de Twilio.
    - `GJALLARHORN_TELEFONO_CLAVE_PUBLICA`, la clave publica de Telnyx.

    None si no hay ninguna: entonces el webhook no arranca, que es lo que
    tiene que pasar. Un webhook sin con que comprobar la firma es un
    telefono que atiende a cualquiera que sepa la URL.
    """
    avisar._leer_env()
    token = os.environ.get("GJALLARHORN_TELEFONO_TOKEN", "").strip()
    clave = os.environ.get("GJALLARHORN_TELEFONO_CLAVE_PUBLICA", "").strip()
    # La de SignalWire cae en el token si no se pone aparte: es el mismo tipo
    # de secreto y casi nadie usa dos proveedores a la vez. Quien use los dos
    # los separa; quien use solo SignalWire pone su clave donde el token y
    # funciona sin enterarse de que existe otra variable.
    firma_sw = os.environ.get("GJALLARHORN_TELEFONO_CLAVE_SIGNALWIRE", "").strip() or token
    if not token and not clave:
        return None
    return {"token": token, "clave_publica": clave, "clave_signalwire": firma_sw,
            "voz": os.environ.get("GJALLARHORN_TELEFONO_VOZ", "").strip() or VOZ_POR_DEFECTO}


def proveedores(config: dict) -> list[str]:
    """Cuales estan configurados de verdad, sin contar los huecos sin rellenar."""
    puestos = []
    if config.get("token") and not token_de_mentira(config["token"]):
        puestos.append("twilio")
    sw = config.get("clave_signalwire") or ""
    if sw and not token_de_mentira(sw) and sw != config.get("token"):
        puestos.append("signalwire")
    clave = config.get("clave_publica") or ""
    # 32 bytes es lo que mide una clave Ed25519: si no, esta a medio pegar.
    if clave and not token_de_mentira(clave) and len(firmas.de_base64(clave)) == 32:
        puestos.append("telnyx")
    return puestos


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


def firma_valida_telnyx(clave_publica: str, cuerpo: bytes, firma: str | None,
                        marca: str | None, ahora: float | None = None,
                        ventana: int = VENTANA_TELNYX) -> bool:
    """La firma de Telnyx: Ed25519 sobre «marca|cuerpo», con clave publica.

    Telnyx no firma como Twilio y no se parece en nada:

    - Twilio hace un HMAC-SHA1 con el **Auth Token**, que es un secreto
      compartido, sobre la URL mas los campos ordenados.
    - Telnyx firma con su clave **privada** y publica la **publica**. Lo
      que se pone en el `.env` no es ninguna clave de API: es la clave
      publica del portal (Keys & Credentials > Public Key). Poner ahi la
      API Key da 403 en todas las llamadas, y es un sitio malisimo para
      enterarse.

    El mensaje firmado es la marca de tiempo, una barra vertical y el
    **cuerpo crudo** —tal como llego, sin volver a montarlo desde los
    campos: cualquier reordenacion cambia los bytes y tira la firma—.

    La marca de tiempo no es decoracion. Sin mirarla, una peticion buena
    grabada vale para siempre: quien la capture puede repetirla y colar la
    misma llamada mil veces. Se aceptan `ventana` segundos a cada lado; a
    cada lado porque los relojes de dos maquinas no van iguales.
    """
    if not firma or not marca:
        return False
    try:
        cuando = float(marca)
    except (TypeError, ValueError):
        return False
    if abs((time.time() if ahora is None else ahora) - cuando) > ventana:
        return False
    clave = firmas.de_base64(clave_publica)
    bruta = firmas.de_base64(firma)
    if not clave or not bruta:
        return False
    try:
        return firmas.valida(clave, marca.encode("utf-8") + b"|" + cuerpo, bruta)
    except firmas.ClavePublicaMala:
        return False           # quien revisa lo dice con todas las letras


def quien_firma(cabeceras) -> str:
    """«twilio», «telnyx» o «» segun la cabecera que traiga la peticion.

    Se mira la peticion y no la configuracion a proposito: asi una maquina
    con las dos cosas puestas atiende a los dos, y sobre todo el que no
    corresponde no se valida «por si acaso».
    """
    if cabeceras.get(CABECERA_TWILIO):
        return "twilio"
    if cabeceras.get(CABECERA_SIGNALWIRE):
        return "signalwire"
    if cabeceras.get(CABECERA_TELNYX):
        return "telnyx"
    return ""


# ---- los clientes que ya han llamado -----------------------------------

def cliente(numero: str) -> "memoria.Ficha | None":
    """Lo que se sabe de quien llama desde ese numero, o None si es la primera vez.

    La ficha vive en `memoria.py`; aqui solo se sabe de que numero es. La
    frontera es esa a proposito: el numero lo maneja la centralita y lo que
    se puede guardar de alguien lo decide quien lleva la ficha.
    """
    return memoria.ficha(numero)


def recordar_cliente(numero: str, nombre: str | None) -> None:
    """Apunta una llamada mas y, si lo dio, el nombre.

    Sin nombre y sin ficha previa no hay nada que recordar: un numero que no
    ha dicho nada y del que no se sabe nada no es un cliente, es una llamada.
    El nombre de antes NO se pisa con un vacio; de eso se encarga `memoria`.
    """
    if not numero or (not nombre and memoria.ficha(numero) is None):
        return
    memoria.apuntar_llamada(numero, nombre)


def saludo_a(nombre: str, saludo: str) -> str:
    """El saludo del negocio, dirigido a alguien conocido, sin saludar dos veces.

    «Hola, Marta. Hola, ha llamado a…» es lo que salía al pegar el nombre
    delante de un saludo que ya empieza por «hola».
    """
    resto = re.sub(r"^\s*(?:hola|buenas|buenos\s+dias|buenos\s+días|buenas\s+tardes)"
                   r"[\s,.!¡]*", "", saludo, flags=re.IGNORECASE)
    if not resto:
        return f"Hola, {nombre}."
    return f"Hola, {nombre}. {resto[0].upper()}{resto[1:]}"


# ---- TwiML ---------------------------------------------------------------

def _twiml(*trozos: str) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(trozos) + "</Response>"


def _decir(texto: str, voz: str) -> str:
    # Lo que se lee en voz alta no es lo que se escribe: «45 €» → «45 euros».
    return (f'<Say voice="{escape(voz, quote=True)}" language="{IDIOMA}">'
            f'{escape(voz_.para_decir(texto))}</Say>')


# Lo que el proveedor tiene que esperar oír, ademas de los servicios de la
# tabla: le ayuda a transcribir «mechas» como «mechas» y no como «meses».
PISTAS_FIJAS = ["cita", "precio", "cuánto vale", "anular", "cambiar", "horario",
                "por la mañana", "por la tarde", "a las", "y media", "menos cuarto",
                "hoy", "mañana", "pasado mañana", "lunes", "martes", "miércoles",
                "jueves", "viernes", "sábado", "domingo", "tarjeta", "cuando podáis",
                "a nombre de", "me llamo", "sí", "no", "gracias", "adiós"]


def pistas_de(negocio) -> str:
    """Las palabras que el proveedor debe esperar oír, para transcribir mejor."""
    from hugin.mente import conocimiento
    servicios = [s["servicio"] for s in conocimiento.tarifas(negocio.conocimiento)]
    vistas, pistas = set(), []
    for pista in servicios + PISTAS_FIJAS:
        if pista.lower() not in vistas:
            vistas.add(pista.lower())
            pistas.append(pista.replace(",", " "))
    return ", ".join(pistas)[:1000]


def _escuchar(texto: str, voz: str, accion: str, pistas: str = "") -> str:
    """Decir algo y quedarse escuchando; lo que se oiga llega a `accion`.

    `hints` y el modelo de llamada telefonica son cosa del proveedor: con
    ellos «tinte» se transcribe «tinte» y no «tiende». Sin pistas se omite.
    """
    ayuda = f' hints="{escape(pistas, quote=True)}"' if pistas else ""
    return (f'<Gather input="speech" language="{IDIOMA}" speechTimeout="auto" '
            f'speechModel="phone_call" enhanced="true"{ayuda} '
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
        self.pistas = pistas_de(negocio)
        self._ahora = ahora
        self._llamadas: dict[str, recepcion.Conversacion] = {}
        self._numeros: dict[str, str] = {}
        self._empezadas: dict[str, float] = {}
        self._conocidos: set[str] = set()     # llamadas de un numero ya visto
        self._cerradas: dict[str, str | None] = {}   # lo apuntado al colgar nosotros

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
        conocido = cliente(numero)
        if conocido is not None:
            # La conversacion se queda con la ficha entera: el nombre para no
            # volver a preguntarlo, y lo que suele pedir y a que hora para
            # ofrecerselo en vez de hacerle empezar de cero.
            self._llamadas[sid].recordar(conocido)
            if conocido.conocido:
                self._conocidos.add(sid)
                saludo = saludo_a(conocido.nombre, saludo)
        avisos.registrar("llamada", f"Llamada de {numero or 'número oculto'}"
                         + (f" ({conocido.nombre})" if conocido and conocido.conocido else ""))
        return _twiml(_escuchar(saludo, self.voz, ruta_turno, self.pistas))

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
                return self._colgar(campos, self.negocio.despedida)
            return _twiml(_escuchar(llamada.frases.decir("no_le_oigo"), self.voz, ruta_turno,
                                    self.pistas))

        respuesta = llamada.atender(dicho)
        if respuesta.aviso:
            avisos.registrar(respuesta.tipo_aviso, respuesta.aviso, respuesta.datos)
            avisar.en_segundo_plano()
        print(f"☎️  {dicho}\n  → {respuesta.texto}", flush=True)

        # Se cuelga cuando la RESPUESTA es la despedida, no cuando la frase
        # lleva «gracias»: «gracias, ¿y cuánto vale un tinte?» es una pregunta,
        # y «venga, apúntame el jueves» es una cita. Antes las dos colgaban
        # después de contestar.
        if respuesta.cuelga:
            return self._colgar(campos, respuesta.texto)
        return _twiml(_escuchar(respuesta.texto, self.voz, ruta_turno, self.pistas))

    def _colgar(self, campos: dict[str, str], texto: str) -> str:
        """Despedirse y colgar. Y cerrar la llamada YA, sin esperar al proveedor.

        `/telefono/fin` solo llega si alguien lo configuró. Si colgamos
        nosotros, ya sabemos que ha terminado: se apunta en qué quedó ahora,
        no dentro de dos horas cuando la barra el reloj.
        """
        xml = _twiml(_colgar(texto, self.voz))
        sid = campos.get("CallSid", "")
        quedo = self.fin(campos)
        with _LOCK:
            # Para que el /fin del proveedor, si llega, sepa que quedo. Acotado:
            # una llamada de cada cien mil no se cierra por aqui.
            self._cerradas[sid] = quedo
            while len(self._cerradas) > 100:
                self._cerradas.pop(next(iter(self._cerradas)))
        return xml

    def fin(self, campos: dict[str, str]) -> str | None:
        """La llamada ha terminado: apuntar en que quedo y recordar al cliente."""
        sid = campos.get("CallSid", "")
        with _LOCK:
            llamada = self._llamadas.pop(sid, None)
            numero = self._numeros.pop(sid, "")
            self._empezadas.pop(sid, None)
            conocido = sid in self._conocidos
            self._conocidos.discard(sid)
            if llamada is None:
                return self._cerradas.pop(sid, None)
        # De un numero ya visto solo se cambia el nombre si se ha presentado
        # («soy Marta»); un «a nombre de Lucia» es de la cita, no de quien llama.
        recordar_cliente(numero, llamada.presentado or (None if conocido else llamada.nombre))
        if numero:
            # Lo que ha pasado en la llamada, a la ficha: con qué se ha citado
            # y a qué hora, que es lo que luego se le ofrece sin preguntar.
            for reservada in llamada.reservadas:
                memoria.apuntar_cita(numero, reservada.get("servicio"), reservada.get("hora"))
            for _ in range(llamada.anulaciones):
                memoria.apuntar_anulacion(numero)
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

    from hugin.negocio import negocio as negocios

    parser = argparse.ArgumentParser(description="El telefono, sin telefono")
    parser.add_argument("--simular", action="store_true", help="una llamada por teclado")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--numero", default="+34600000000", help="desde que numero se llama")
    parser.add_argument("--puerto", type=int, default=8081)
    args = parser.parse_args()

    try:
        n = negocios.cargar(args.negocio)
    except (FileNotFoundError, ValueError) as error:
        print(f"❌ {error}")
        return 1
    datos.usar(n)
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

    _lo_del_webhook(config, args)
    return 0


def _lo_del_webhook(config: dict | None, args) -> None:
    """Como probar el webhook de verdad, segun el proveedor que haya puesto.

    Con Twilio se puede firmar aqui mismo: el Auth Token es un secreto
    compartido, o sea que con el se firma igual que comprueba. Con Telnyx
    **no se puede, y es a proposito**: firma con su clave privada y lo que
    tenemos es la publica. Poder fabricar una firma buena desde aqui seria
    justo el agujero que ese esquema evita. Asi que ahi se dice la verdad y
    se prueba lo que si se puede probar sin proveedor.
    """
    if not config:
        print("\nSin nada en .env con que comprobar la firma, el webhook no arranca:")
        print("  GJALLARHORN_TELEFONO_TOKEN=…          (el Auth Token de Twilio)")
        print("  GJALLARHORN_TELEFONO_CLAVE_PUBLICA=…  (la clave publica de Telnyx)")
        return

    puestos = proveedores(config)
    if not puestos:
        print("\nHay algo puesto en .env pero no sirve. «make revisar» dice que es.")
        return

    if "twilio" in puestos:
        campos = {"CallSid": "CAprueba", "From": args.numero}
        url = f"https://localhost:{args.puerto}/telefono/entrada"
        firma = base64.b64encode(hmac.new(
            config["token"].encode(),
            (url + "".join(k + campos[k] for k in sorted(campos))).encode(),
            hashlib.sha1).digest()).decode()
        formulario = "&".join(f"{k}={v}" for k, v in campos.items())
        print("\nCon el servidor arrancado (make arrancar), esto prueba el webhook real, firma incluida:")
        print(f"  curl -s -X POST http://127.0.0.1:{args.puerto}/telefono/entrada "
              f"-H 'Host: localhost:{args.puerto}' -H 'X-Forwarded-Proto: https' "
              f"-H '{CABECERA_TWILIO}: {firma}' -d '{formulario}'")
        print("  → tiene que devolver un <Response> con <Gather>. Sin la cabecera de firma, 403.")

    if "telnyx" in puestos:
        print("\nCon Telnyx no se puede firmar una prueba desde aqui, y eso es bueno:")
        print("  firma con su clave privada, que no sale de Telnyx; aqui solo esta la")
        print("  publica. Si desde aqui se pudiera fabricar una firma buena, cualquiera")
        print("  que leyera tu .env podria llamar a tu webhook haciendose pasar por ellos.")
        print("\n  Lo que si se puede comprobar sin gastar una llamada:")
        print(f"  curl -s -o /dev/null -w '%{{http_code}}\\n' -X POST "
              f"http://127.0.0.1:{args.puerto}/telefono/entrada -d 'CallSid=CAprueba'")
        print("  → tiene que decir 403. Eso es el servidor vivo y rechazando lo que no")
        print("    viene firmado, que es la mitad que depende de ti. La otra mitad la")
        print("    prueba la primera llamada de verdad; «make log» la enseña entrando.")
    return


if __name__ == "__main__":
    raise SystemExit(main())
