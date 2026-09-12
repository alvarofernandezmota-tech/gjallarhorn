"""Que las citas y los recados lleguen al movil. Sin esto, se quedan en un JSON.

    GJALLARHORN_TELEGRAM_TOKEN=123:abc     el bot, de @BotFather
    GJALLARHORN_TELEGRAM_CHAT=987654       tu chat, de @userinfobot
    GJALLARHORN_TELEGRAM_TIPOS=cita,fallo  opcional; por defecto cita, llamada y fallo

Van en un `.env` en la raiz del repo (esta en el .gitignore) o en el entorno.
**Nunca en el codigo ni en negocio.toml**: el repo es publico.

## Cuando se manda

Cada vez que el servidor registra un aviso de uno de esos tipos, en un hilo
aparte para no sumarle la red de Telegram al tiempo de respuesta de la
llamada. Las tarifas no se mandan por defecto: veinte «preguntó el precio
del corte» al dia son ruido, y el ruido es lo que hace que se deje de mirar.

## Lo que no hace, a proposito

- No marca un aviso como visto hasta que Telegram confirma que lo tiene. Si
  la red falla, el aviso sigue «sin ver» y sale en el siguiente envio.
- No registra el fallo de envio como aviso: un aviso de «no pude avisar»
  dispararia otro envio, y otro fallo, y otro aviso.
- Sin token no hace nada y lo dice una vez al arrancar. No es un error:
  es que no esta configurado.
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from hugin.guardado import avisos
from hugin.guardado import ajustes
from hugin.guardado import datos

RAIZ = Path(__file__).resolve().parent.parent
TIPOS_POR_DEFECTO = ("cita", "llamada", "fallo")
_LOCK = threading.Lock()


def configuracion() -> dict | None:
    """Token, chat y tipos. None si no esta configurado."""
    ajustes.leer()
    token = os.environ.get("GJALLARHORN_TELEGRAM_TOKEN", "").strip()
    chat = os.environ.get("GJALLARHORN_TELEGRAM_CHAT", "").strip()
    if not token or not chat:
        return None
    tipos = os.environ.get("GJALLARHORN_TELEGRAM_TIPOS", "").strip()
    return {"token": token, "chat": chat,
            "tipos": tuple(t.strip() for t in tipos.split(",") if t.strip()) or TIPOS_POR_DEFECTO}


def _mandar_telegram(token: str, chat: str, texto: str, markdown: bool) -> None:
    datos = {"chat_id": chat, "text": texto}
    if markdown:
        datos["parse_mode"] = "Markdown"
    peticion = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=urllib.parse.urlencode(datos).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(peticion, timeout=15) as respuesta:
        cuerpo = json.loads(respuesta.read().decode("utf-8"))
    if not cuerpo.get("ok"):
        raise RuntimeError(f"Telegram dijo que no: {cuerpo}")


def enviar(texto: str, mandar=None, config: dict | None = None) -> bool:
    """Manda un texto al chat. True si Telegram lo confirmo.

    Primero en Markdown, que es como `avisos.formato` pone las fechas en
    negrita. Si Telegram lo rechaza —un `_` o un `*` en lo que dijo un
    cliente—, se reenvia en texto plano antes que perder el aviso.
    """
    config = config or configuracion()
    if config is None:
        return False
    mandar = mandar or _mandar_telegram
    try:
        mandar(config["token"], config["chat"], texto, True)
        return True
    except (urllib.error.HTTPError, RuntimeError):
        try:
            mandar(config["token"], config["chat"], texto, False)
            return True
        except (urllib.error.URLError, RuntimeError, OSError) as error:
            print(f"⚠️  no se pudo avisar por Telegram: {error}", file=sys.stderr)
            return False
    except (urllib.error.URLError, OSError) as error:
        print(f"⚠️  no se pudo avisar por Telegram: {error}", file=sys.stderr)
        return False


def avisar_nuevos(mandar=None, config: dict | None = None,
                  ruta: Path | None = None) -> int:
    """Manda los avisos sin ver de los tipos configurados. Cuantos se han mandado.

    Se marcan como vistos **despues** de que Telegram confirme, nunca antes.
    """
    config = config or configuracion()
    if config is None:
        return 0
    mandados = 0
    with _LOCK:
        # En tantos mensajes como hagan falta. Solo se marca como visto lo que
        # ha cabido en el mensaje que Telegram ha confirmado: antes se marcaba
        # todo lo pendiente aunque `formato` lo hubiera recortado, y lo
        # recortado no se volvia a ver nunca.
        while True:
            pendientes = [a for a in avisos.listar(solo_nuevos=True, ruta=ruta)
                          if a["tipo"] in config["tipos"]]
            if not pendientes:
                return mandados
            cabe = avisos.encajar(pendientes)
            if not enviar(avisos.formato(cabe), mandar=mandar, config=config):
                return mandados
            avisos.marcar_vistos([a["id"] for a in cabe], ruta=ruta)
            mandados += len(cabe)


def en_segundo_plano() -> None:
    """Para el servidor: avisar sin sumarle la red al tiempo de la llamada."""
    if configuracion() is None:
        return
    threading.Thread(target=avisar_nuevos, daemon=True).start()


def main() -> int:
    """`python3 avisar.py` manda lo pendiente; `--prueba` manda un hola."""
    import argparse

    parser = argparse.ArgumentParser(description="Avisos al movil por Telegram")
    parser.add_argument("--prueba", action="store_true",
                        help="mandar un mensaje de prueba para ver que llega")
    parser.add_argument("--negocio", default="peluqueria",
                        help="de qué negocio son los avisos que se mandan")
    args = parser.parse_args()

    # Los avisos son de un negocio, así que hay que decir de cuál: sin esto
    # se leería la carpeta de datos a secas, que es donde no hay nada.
    datos.usar(args.negocio)

    if configuracion() is None:
        print("Telegram no esta configurado. Hacen falta dos variables, en un .env "
              "en la raiz del repo o en el entorno:")
        print("   GJALLARHORN_TELEGRAM_TOKEN=...   (el bot, de @BotFather)")
        print("   GJALLARHORN_TELEGRAM_CHAT=...    (tu chat, de @userinfobot)")
        return 1
    if args.prueba:
        ok = enviar("gjallarhorn: los avisos llegan por aqui. ✅")
        print("✅ mandado, mira el movil" if ok else "❌ no ha llegado")
        return 0 if ok else 1
    n = avisar_nuevos()
    print(f"{n} aviso(s) mandado(s)" if n else "Nada pendiente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
