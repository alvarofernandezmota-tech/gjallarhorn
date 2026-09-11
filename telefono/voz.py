"""La oreja y la boca: audio → texto → audio. Las dos **en local**.

Whisper oye y Piper habla, los dos sobre el hardware de casa. Por aquí pasa lo
que un cliente cuenta por teléfono y lo que se le contesta: mandarlo a una API
de terceros es justo lo que se quiere evitar.

Los dos motores están detrás de una interfaz de una sola función a propósito.
No es ceremonia: permite probar todo lo de encima —el recepcionista, el
servidor— sin descargar modelos de varios cientos de megas, y permite cambiar
de motor sin tocar nada más.

    from telefono.voz import Whisper, escuchar
    escuchar(Path("llamada.ogg"), Whisper())

En las pruebas se les pasa un `TranscriptorFalso` y un `LocutorFalso`, que
devuelven lo que se les diga. Lo que se prueba ahí no es Whisper —eso es de
Whisper—, es que la tubería de encima haga lo correcto con lo que oye.
"""

import sys
import tempfile
import time
from pathlib import Path
from typing import Protocol

# Español. Forzarlo evita que una frase corta —«hola», «cuánto vale»— se
# detecte como portugués o gallego, que es el fallo típico de estos modelos.
IDIOMA = "es"

# `small` es el equilibrio razonable en una máquina sin GPU. Se cronometra con
# `medir_voz.py` antes de darlo por bueno: la latencia se mide, no se supone.
MODELO_POR_DEFECTO = "small"


class Transcriptor(Protocol):
    """Cualquier cosa que convierta un fichero de audio en texto."""

    def transcribir(self, audio: Path) -> str:
        ...


class Whisper:
    """Whisper en local, por `faster-whisper`.

    El import va dentro y no arriba a propósito: `faster_whisper` arrastra
    `ctranslate2` y descarga el modelo la primera vez. Importarlo al cargar el
    módulo haría que las pruebas —y cualquiera que solo quiera el recepcionista
    por texto— pagaran eso sin usarlo.
    """

    def __init__(self, modelo: str = MODELO_POR_DEFECTO, idioma: str = IDIOMA):
        self.modelo = modelo
        self.idioma = idioma
        self._motor = None

    def _cargar(self):
        if self._motor is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as error:
                raise RuntimeError(
                    "falta faster-whisper para este Python. Instalalo con el "
                    "pip de ESTE interprete, que no tiene por que ser el que "
                    f"contesta a `pip`:\n      {sys.executable} -m pip install "
                    "faster-whisper"
                ) from error
            # int8 en CPU: es lo que hace que esto sea viable sin GPU.
            self._motor = WhisperModel(self.modelo, device="cpu", compute_type="int8")
        return self._motor

    def transcribir(self, audio: Path) -> str:
        if not audio.exists():
            raise FileNotFoundError(f"no existe el audio: {audio}")
        segmentos, _ = self._cargar().transcribe(str(audio), language=self.idioma)
        return " ".join(s.text.strip() for s in segmentos).strip()


class TranscriptorFalso:
    """Devuelve lo que se le diga. Para probar lo de encima de la oreja."""

    def __init__(self, *frases: str):
        self.frases = list(frases)
        self.oidos: list[Path] = []

    def transcribir(self, audio: Path) -> str:
        self.oidos.append(audio)
        return self.frases.pop(0) if self.frases else ""


def escuchar(audio: Path, transcriptor: Transcriptor) -> str:
    """El texto de un audio, limpio de espacios. Cadena vacía si no se oyó nada."""
    return (transcriptor.transcribir(Path(audio)) or "").strip()


# ---- la boca -----------------------------------------------------------
#
# Misma idea que la oreja: detrás de una interfaz de una función, para poder
# probar todo lo de encima sin descargar una voz de cientos de megas y para
# poder cambiar de motor sin tocar nada más.

VOZ_POR_DEFECTO = "es_ES-sharvard-medium"


class Locutor(Protocol):
    """Cualquier cosa que convierta texto en un fichero de audio."""

    def decir(self, texto: str, destino: Path) -> Path:
        ...


class Piper:
    """Piper en local: texto a voz sin mandar nada fuera.

    Local por lo mismo que Whisper: por aquí pasa lo que se le dice a un
    cliente y, del otro lado, lo que el cliente cuenta de su vida. El import
    va dentro porque descarga la voz la primera vez.

    ## La cabecera del WAV se escribe aquí, y no es manía

    Lo evidente sería `voz.synthesize_wav(texto, fichero_wave)` y dejar que
    Piper ponga la cabecera. **No vale**, y el motivo es feo: esa función pone
    los parámetros del `wave` dentro del bucle, al llegar el primer trozo de
    audio. Si no llega ninguno, el fichero se cierra sin cabecera y lo que
    salta es un `wave.Error: # channels not specified` de la librería estándar
    —un error que habla del `wave` y no dice **nada** de que Piper no haya
    sintetizado—. Se persiguen cosas raras durante un buen rato por eso.

    Aquí se juntan los trozos primero y la cabecera se escribe con los números
    delante. Si no hay audio, lo que salta lo dice: no hay audio.

    ## Dos APIs, porque Piper las ha cambiado

    - `synthesize_stream_raw(texto)` → bytes crudos (piper < 1.3).
    - `synthesize(texto)` → objetos con `.audio_int16_bytes` (piper ≥ 1.3).

    Se prueban las dos. Fijar una versión en un `requirements.txt` no arregla
    la máquina de nadie: aquí se instala con el `pip` del sistema.
    """

    def __init__(self, voz: str = VOZ_POR_DEFECTO, carpeta: str | Path | None = None):
        self.voz = voz
        self.carpeta = Path(carpeta) if carpeta else Path.home() / ".cache" / "piper"
        self._motor = None

    def _cargar(self):
        if self._motor is None:
            try:
                from piper import PiperVoice
                from piper.download_voices import download_voice
            except ImportError as error:
                raise RuntimeError(
                    "falta piper-tts para este Python. Instalalo con el pip de "
                    "ESTE interprete, que no tiene por que ser el que contesta "
                    f"a `pip`:\n      {sys.executable} -m pip install piper-tts"
                ) from error
            # `load` quiere la ruta de un .onnx, no el nombre de la voz. Se
            # descarga la primera vez y se queda en cache: pedirle a alguien
            # que baje el modelo a mano antes de arrancar es una forma segura
            # de que no lo arranque.
            carpeta = Path(self.carpeta)
            carpeta.mkdir(parents=True, exist_ok=True)
            modelo = carpeta / f"{self.voz}.onnx"
            if not modelo.exists():
                try:
                    download_voice(self.voz, carpeta)
                except Exception as error:  # noqa: BLE001 — red y nombres de voz
                    raise RuntimeError(
                        f"no se pudo bajar la voz {self.voz!r} a {carpeta}: "
                        f"{error}. Las que hay se listan con "
                        f"`{sys.executable} -m piper.download_voices --help`; "
                        "sin red, copia el .onnx y su .onnx.json a esa carpeta."
                    ) from error
            self._motor = PiperVoice.load(modelo)
        return self._motor

    def _audio(self, texto: str) -> tuple[bytes, int, int, int]:
        """(bytes crudos, tasa, ancho de muestra, canales) por cualquiera de las dos APIs."""
        motor = self._cargar()
        config = getattr(motor, "config", None)
        tasa = getattr(config, "sample_rate", None) or 22050
        ancho, canales = 2, 1  # PCM de 16 bits, mono: lo que saca Piper.

        if hasattr(motor, "synthesize_stream_raw"):          # piper < 1.3
            partes = list(motor.synthesize_stream_raw(texto))
        else:                                                # piper >= 1.3
            partes = []
            for trozo in motor.synthesize(texto):
                # AudioChunk si es reciente; si no, los bytes tal cual.
                partes.append(getattr(trozo, "audio_int16_bytes", trozo))
                tasa = getattr(trozo, "sample_rate", None) or tasa
                ancho = getattr(trozo, "sample_width", None) or ancho
                canales = getattr(trozo, "sample_channels", None) or canales

        return b"".join(partes), tasa, ancho, canales

    def decir(self, texto: str, destino: Path) -> Path:
        import wave

        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)

        crudo, tasa, ancho, canales = self._audio(texto)
        if not crudo:
            # El fallo de verdad, dicho donde pasa. Antes esto se manifestaba
            # como un «# channels not specified» del modulo wave.
            raise RuntimeError(
                f"Piper no ha sacado ni un byte de audio para {texto[:40]!r} "
                f"con la voz {self.voz!r}. Casi siempre es que falta espeak-ng "
                "(la fonemizacion) o que el .onnx bajo a medias: borra "
                f"{Path(self.carpeta) / (self.voz + '.onnx')} y deja que se "
                "vuelva a bajar. `python3 voz.py` lo comprueba de una pieza.")

        with wave.open(str(destino), "wb") as salida:
            salida.setnchannels(canales)
            salida.setsampwidth(ancho)
            salida.setframerate(tasa)
            salida.writeframes(crudo)
        return destino


class LocutorFalso:
    """Escribe el texto en vez de hablarlo. Para probar lo de encima."""

    def __init__(self):
        self.dicho: list[str] = []

    def decir(self, texto: str, destino: Path) -> Path:
        self.dicho.append(texto)
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
        return destino


def para_decir(texto: str) -> str:
    """El texto como hay que leerlo en voz alta. Lo escrito se queda como está.

    «45 €» en pantalla es perfecto; en voz, un motor lo lee como «cuarenta y
    cinco» y un signo raro, o «euro» en singular. «90 min» sale «noventa min».
    Esto se aplica solo en el momento de hablar —Piper o el proveedor—, para
    que la página, los avisos y las pruebas sigan viendo el texto escrito.
    """
    import re

    def euros(m):
        entero, decimales = m.group(1), m.group(2)
        dicho = f"{entero} euro" if entero == "1" and not decimales else f"{entero} euros"
        return f"{dicho} con {decimales.lstrip('0') or '0'}" if decimales else dicho

    texto = re.sub(r"(\d+)(?:[,.](\d{1,2}))?\s*€", euros, texto)
    texto = re.sub(r"\b(\d+)\s*min\b", lambda m: f"{m.group(1)} minutos", texto)
    texto = re.sub(r"\b1 minutos\b", "1 minuto", texto)
    texto = re.sub(r"\b(\d+)\s*h\b", lambda m: f"{m.group(1)} horas", texto)
    # «10:00» se lee «diez», «16:30» «dieciséis y media»: el horario de la FAQ
    # está escrito con reloj y por teléfono no se lee un reloj.
    minutos = {"00": "", "15": " y cuarto", "30": " y media"}

    def reloj(m):
        return m.group(1) + minutos.get(m.group(2), f" y {int(m.group(2))}")

    texto = re.sub(r"\b(\d{1,2}):(\d{2})\b", reloj, texto)
    return texto.replace("; ", ", ")


def hablar(texto: str, destino: Path, locutor: Locutor) -> Path | None:
    """El audio de una frase. `None` si no hay nada que decir.

    Devolver None y no un wav de silencio es a propósito: quien llama no tiene
    por qué oír medio segundo de nada y pensar que se ha cortado.
    """
    texto = para_decir((texto or "").strip())
    return locutor.decir(texto, Path(destino)) if texto else None


# ---- el diagnostico ----------------------------------------------------
#
#     python3 voz.py
#
# Existe porque la voz **solo falla en la maquina donde se instala**, y ahi
# no hay nadie mirando el codigo: hay alguien mirando un traceback de treinta
# lineas que habla del modulo `wave`. Esto contesta la unica pregunta que
# importa —¿oye y habla esta maquina?— y dice que version de cada cosa hay,
# que es lo primero que se pregunta cuando no funciona.


def _version(modulo, paquete: str) -> str:
    """La version instalada. Del paquete primero: piper no publica __version__."""
    import importlib.metadata
    try:
        return importlib.metadata.version(paquete)
    except importlib.metadata.PackageNotFoundError:
        pass
    for atributo in ("__version__", "VERSION", "version"):
        if (valor := getattr(modulo, atributo, None)) is not None:
            return str(valor)
    return "?"


def _probar_boca(frase: str, destino: Path) -> dict:
    locutor = Piper()
    motor = locutor._cargar()   # si falta, el error ya trae las instrucciones
    import piper

    api = ("synthesize_stream_raw (piper < 1.3)"
           if hasattr(motor, "synthesize_stream_raw") else "synthesize (piper >= 1.3)")

    arranque = time.perf_counter()
    locutor.decir(frase, destino)
    ms = (time.perf_counter() - arranque) * 1000

    crudo, tasa, ancho, canales = locutor._audio(frase)
    segundos = len(crudo) / (tasa * ancho * canales) if tasa else 0
    return {"version": _version(piper, "piper-tts"), "api": api, "ms": ms, "bytes": len(crudo),
            "segundos": segundos, "tasa": tasa, "voz": locutor.voz}


def _probar_oreja(audio: Path) -> dict:
    transcriptor = Whisper()
    transcriptor._cargar()      # idem: el mensaje util sale de aqui
    import faster_whisper

    arranque = time.perf_counter()
    oido = escuchar(audio, transcriptor)
    return {"version": _version(faster_whisper, "faster-whisper"),
            "modelo": transcriptor.modelo,
            "ms": (time.perf_counter() - arranque) * 1000, "oido": oido}


def main() -> int:
    frase = "Hola, ha llamado a la peluquería. ¿En qué puedo ayudarle?"
    print(f"Python {sys.version.split()[0]} · {sys.executable}")
    if sys.prefix == sys.base_prefix:
        # Fuera de un entorno virtual, y esa es la causa numero uno de «lo
        # instale y dice que falta»: en Arch, Debian y compania `pip install`
        # sobre el Python del sistema o lo bloquea (externally-managed) o deja
        # el paquete en ~/.local, donde otro interprete no lo ve.
        print("   (sin entorno virtual)")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "prueba.wav"

        print("🗣️  La boca (Piper)")
        try:
            boca = _probar_boca(frase, audio)
        except Exception as error:  # noqa: BLE001 — aqui abajo hay modelos y disco
            print(f"   ❌ {type(error).__name__}: {error}\n")
            return 1
        print(f"   piper {boca['version']} · voz {boca['voz']} · {boca['api']}")
        print(f"   {boca['bytes']} bytes · {boca['segundos']:.1f} s de audio "
              f"a {boca['tasa']} Hz · {boca['ms']:.0f} ms\n")

        print("👂 La oreja (Whisper)")
        try:
            oreja = _probar_oreja(audio)
        except Exception as error:  # noqa: BLE001 — idem
            print(f"   ❌ {type(error).__name__}: {error}\n")
            return 1
        print(f"   faster-whisper {oreja['version']} · modelo {oreja['modelo']} "
              f"· {oreja['ms']:.0f} ms")
        print(f"   oyo: «{oreja['oido']}»\n")

    # Que se parezca no se exige: Whisper puede comerse una tilde o un signo y
    # dar igual. Lo que se exige es que haya oido algo, porque lo contrario
    # —silencio— es el fallo que de verdad deja el agente mudo.
    if not oreja["oido"].strip():
        print("⚠️  Hay audio pero Whisper no ha oido nada. Revisa la voz de Piper:")
        print(f"    escuchala tu mismo con  python3 -c \"import voz,pathlib;"
              f"voz.Piper().decir('{frase[:20]}', pathlib.Path('/tmp/p.wav'))\"")
        return 1

    print("✅ Oye y habla. Ya se puede medir:  python3 medir_voz.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
