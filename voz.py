"""La oreja: audio → texto. Capa 3 del ADR-018, la mitad que sí se puede hacer.

La transcripción es **local**, sobre el hardware de casa. El audio del diario
no sale de casa: mandarlo a una API de terceros es lo que el ADR-016 y el repo
privado del diario tratan de evitar.

El motor está detrás de una interfaz de una sola función a propósito. No es
ceremonia: permite que todo lo de arriba —el cerebro, las acciones, el
agente— se pruebe sin descargar un modelo de varios cientos de megas, y permite
cambiar Whisper por otra cosa sin tocar nada más.

    from voz import Whisper, escuchar
    escuchar(Path("nota.ogg"), Whisper())

En las pruebas se le pasa un `TranscriptorFalso`, que devuelve lo que se le
diga. Lo que se prueba ahí no es Whisper —eso es de Whisper—, es que la tubería
de encima haga lo correcto con lo que oye.
"""

from pathlib import Path
from typing import Protocol

# Español. El diario está en español y forzarlo evita que una frase corta se
# detecte como portugués o gallego, que es el fallo típico de estos modelos.
IDIOMA = "es"

# `small` es el equilibrio razonable en una máquina sin GPU. Se mide en Madre
# antes de darlo por bueno: el ADR-018 dice que la carga se mide, no se supone.
MODELO_POR_DEFECTO = "small"


class Transcriptor(Protocol):
    """Cualquier cosa que convierta un fichero de audio en texto."""

    def transcribir(self, audio: Path) -> str:
        ...


class Whisper:
    """Whisper en local, por `faster-whisper`.

    El import va dentro y no arriba a propósito: `faster_whisper` arrastra
    `ctranslate2` y descarga el modelo la primera vez. Importarlo al cargar el
    módulo haría que las pruebas —y cualquiera que solo quiera el catálogo de
    acciones— pagaran eso sin usarlo.
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
