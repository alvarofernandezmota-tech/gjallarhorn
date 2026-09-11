"""La oreja y la boca: audio → texto → audio. Las dos **en local**.

Whisper oye y Piper habla, los dos sobre el hardware de casa. Por aquí pasa lo
que un cliente cuenta por teléfono y lo que se le contesta: mandarlo a una API
de terceros es justo lo que se quiere evitar.

Los dos motores están detrás de una interfaz de una sola función a propósito.
No es ceremonia: permite probar todo lo de encima —el recepcionista, el
servidor— sin descargar modelos de varios cientos de megas, y permite cambiar
de motor sin tocar nada más.

    from voz import Whisper, escuchar
    escuchar(Path("llamada.ogg"), Whisper())

En las pruebas se les pasa un `TranscriptorFalso` y un `LocutorFalso`, que
devuelven lo que se les diga. Lo que se prueba ahí no es Whisper —eso es de
Whisper—, es que la tubería de encima haga lo correcto con lo que oye.
"""

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
                    "falta faster-whisper: pip install faster-whisper. "
                    "Va en la maquina donde corre el agente, no en la de desarrollo."
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

    Dos cosas que solo se ven instalándolo de verdad, y que estaban mal
    escritas de memoria:

    - `PiperVoice.load()` quiere **la ruta de un `.onnx`**, no el nombre de la
      voz. Hay que bajarla antes con `download_voice`, y se cachea.
    - El método es `synthesize_wav(texto, fichero)`, no `synthesize`, que
      devuelve trozos de audio y deja el `wave` sin cabecera («# channels not
      specified»).

    Local por lo mismo que Whisper: por aquí pasa lo que se le dice a un
    cliente y, del otro lado, lo que el cliente cuenta de su vida. El import
    va dentro porque descarga la voz la primera vez.
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
                    "falta piper-tts: pip install piper-tts. Va en la maquina "
                    "donde corre el agente, no en la de desarrollo."
                ) from error
            # `load` quiere la ruta de un .onnx, no el nombre de la voz. Se
            # descarga la primera vez y se queda en cache: pedirle a alguien
            # que baje el modelo a mano antes de arrancar es una forma segura
            # de que no lo arranque.
            carpeta = Path(self.carpeta)
            carpeta.mkdir(parents=True, exist_ok=True)
            modelo = carpeta / f"{self.voz}.onnx"
            if not modelo.exists():
                download_voice(self.voz, carpeta)
            self._motor = PiperVoice.load(modelo)
        return self._motor

    def decir(self, texto: str, destino: Path) -> Path:
        import wave

        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(destino), "wb") as salida:
            self._cargar().synthesize_wav(texto, salida)
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


def hablar(texto: str, destino: Path, locutor: Locutor) -> Path | None:
    """El audio de una frase. `None` si no hay nada que decir.

    Devolver None y no un wav de silencio es a propósito: quien llama no tiene
    por qué oír medio segundo de nada y pensar que se ha cortado.
    """
    texto = (texto or "").strip()
    return locutor.decir(texto, Path(destino)) if texto else None
