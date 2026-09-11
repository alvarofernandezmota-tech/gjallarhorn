"""Pruebas de voz.py — la oreja y la boca, sin descargar ni un modelo.

Aquí no se prueba Whisper ni Piper: eso es de ellos. Se prueba **la tubería
que los envuelve**, y una cosa en concreto que ya falló en producción:

`Piper.synthesize_wav()` escribe la cabecera del WAV dentro del bucle de
trozos. Si Piper no saca ni un trozo, el fichero se cierra sin cabecera y lo
que salta es `wave.Error: # channels not specified` —un error de la librería
estándar que habla del módulo `wave` y **no dice nada** de que la síntesis
haya fallado—. Se persiguen cosas raras un buen rato por eso.

Por eso la cabecera se escribe aquí, con los números delante, y el «no hay
audio» se dice como lo que es.
"""

import sys
import tempfile
import unittest
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

import voz  # noqa: E402

TASA = 22050


class Trozo:
    """Lo que devuelve `synthesize()` en piper >= 1.3."""

    def __init__(self, crudo, tasa=TASA, ancho=2, canales=1):
        self.audio_int16_bytes = crudo
        self.sample_rate, self.sample_width, self.sample_channels = tasa, ancho, canales


class MotorNuevo:
    """piper >= 1.3: `synthesize(texto)` da trozos con metadatos."""

    class config:
        sample_rate = TASA

    def __init__(self, *trozos):
        self.trozos = trozos

    def synthesize(self, texto):
        return iter(self.trozos)


class MotorViejo:
    """piper < 1.3: `synthesize_stream_raw(texto)` da bytes pelados."""

    class config:
        sample_rate = TASA

    def __init__(self, *crudos):
        self.crudos = crudos

    def synthesize_stream_raw(self, texto):
        return iter(self.crudos)


class CasoVoz(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.destino = Path(self._tmp.name) / "sale" / "voz.wav"

    def locutor_con(self, motor):
        locutor = voz.Piper()
        locutor._motor = motor          # sin descargar nada
        return locutor


class TestLaCabeceraSeEscribeAqui(CasoVoz):
    def test_el_wav_sale_con_cabecera_y_se_puede_abrir(self):
        crudo = b"\x01\x02" * 1000
        self.locutor_con(MotorNuevo(Trozo(crudo))).decir("hola", self.destino)

        with wave.open(str(self.destino), "rb") as leido:
            self.assertEqual(leido.getnchannels(), 1)
            self.assertEqual(leido.getsampwidth(), 2)
            self.assertEqual(leido.getframerate(), TASA)
            self.assertEqual(leido.readframes(leido.getnframes()), crudo)

    def test_varios_trozos_salen_pegados_y_en_orden(self):
        partes = (b"\x01\x01" * 10, b"\x02\x02" * 10, b"\x03\x03" * 10)
        self.locutor_con(MotorNuevo(*(Trozo(p) for p in partes))).decir("hola", self.destino)
        with wave.open(str(self.destino), "rb") as leido:
            self.assertEqual(leido.readframes(leido.getnframes()), b"".join(partes))

    def test_crea_la_carpeta_si_no_existe(self):
        self.locutor_con(MotorNuevo(Trozo(b"\x00\x00" * 10))).decir("hola", self.destino)
        self.assertTrue(self.destino.exists())


class TestSinAudioSeDiceQueNoHayAudio(CasoVoz):
    """La regresión de verdad: el fallo que se vio en la máquina de casa."""

    def test_no_es_un_wave_error_pelado(self):
        # `wave.Error` no hereda de RuntimeError, así que este assert ya
        # distingue el error traducido del crudo. Es justo lo que se rompió:
        # el traceback hablaba de `wave.py`, no de Piper.
        with self.assertRaises(RuntimeError) as caso:
            self.locutor_con(MotorNuevo()).decir("hola", self.destino)
        self.assertNotIsInstance(caso.exception, wave.Error)

    def test_el_mensaje_dice_que_piper_no_saco_audio_y_con_que_voz(self):
        with self.assertRaises(RuntimeError) as caso:
            self.locutor_con(MotorNuevo()).decir("cuánto vale un corte", self.destino)
        mensaje = str(caso.exception)
        self.assertIn("Piper", mensaje)
        self.assertIn("audio", mensaje)
        self.assertIn(voz.VOZ_POR_DEFECTO, mensaje)
        self.assertIn("cuánto vale un corte", mensaje)

    def test_no_deja_un_wav_roto_tirado(self):
        # Un .wav de cero bytes en disco es peor que ninguno: parece que hay
        # audio hasta que alguien intenta reproducirlo.
        with self.assertRaises(RuntimeError):
            self.locutor_con(MotorNuevo()).decir("hola", self.destino)
        self.assertFalse(self.destino.exists())


class TestPorQueNoSeUsaSynthesizeWav(CasoVoz):
    """La prueba de que el diagnóstico era ese y no otro.

    `MotorComoPiper.synthesize_wav` hace lo mismo que el de verdad: pone los
    parámetros del `wave` **al llegar el primer trozo**. Sin trozos no los pone
    nunca, y el `wave` revienta al cerrarse hablando de canales.

    Si algún día alguien vuelve a delegar la cabecera en Piper «porque es más
    corto», esta prueba explica lo que se compra.
    """

    class MotorComoPiper(MotorNuevo):
        def synthesize_wav(self, texto, fichero, set_wav_format=True):
            primero = True
            for trozo in self.synthesize(texto):
                if primero and set_wav_format:
                    fichero.setframerate(trozo.sample_rate)
                    fichero.setsampwidth(trozo.sample_width)
                    fichero.setnchannels(trozo.sample_channels)
                    primero = False
                fichero.writeframes(trozo.audio_int16_bytes)

    def escribir_delegando(self, motor):
        """Lo que hacía `decir()` antes: dejar la cabecera en manos de Piper."""
        self.destino.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(self.destino), "wb") as salida:
            motor.synthesize_wav("hola", salida)

    def test_delegar_la_cabecera_revienta_cuando_no_hay_audio(self):
        with self.assertRaises(wave.Error) as caso:
            self.escribir_delegando(self.MotorComoPiper())
        self.assertIn("channels", str(caso.exception))

    def test_y_el_nuestro_dice_lo_que_pasa_de_verdad(self):
        # Mismo motor, mismo silencio, error que se puede leer.
        with self.assertRaises(RuntimeError) as caso:
            self.locutor_con(self.MotorComoPiper()).decir("hola", self.destino)
        self.assertIn("Piper", str(caso.exception))


class TestLasDosApisDePiper(CasoVoz):
    def test_la_vieja_por_bytes_crudos(self):
        crudo = b"\x04\x04" * 50
        self.locutor_con(MotorViejo(crudo)).decir("hola", self.destino)
        with wave.open(str(self.destino), "rb") as leido:
            self.assertEqual(leido.readframes(leido.getnframes()), crudo)
            self.assertEqual(leido.getframerate(), TASA)

    def test_la_vieja_sin_audio_tambien_avisa(self):
        with self.assertRaises(RuntimeError):
            self.locutor_con(MotorViejo()).decir("hola", self.destino)

    def test_un_trozo_sin_metadatos_usa_los_del_config(self):
        # Versión intermedia: `synthesize()` existe pero devuelve bytes.
        self.locutor_con(MotorNuevo(b"\x05\x05" * 20)).decir("hola", self.destino)
        with wave.open(str(self.destino), "rb") as leido:
            self.assertEqual(leido.getframerate(), TASA)
            self.assertEqual(leido.getnchannels(), 1)


class TestHablar(CasoVoz):
    def test_una_frase_vacia_no_genera_fichero(self):
        self.assertIsNone(voz.hablar("   ", self.destino, voz.LocutorFalso()))
        self.assertFalse(self.destino.exists())

    def test_una_frase_de_verdad_si(self):
        self.assertIsNotNone(voz.hablar("hola", self.destino, voz.LocutorFalso()))


class TestEscuchar(CasoVoz):
    def test_devuelve_lo_oido_sin_espacios(self):
        self.assertEqual(voz.escuchar(self.destino, voz.TranscriptorFalso("  hola  ")), "hola")

    def test_sin_nada_que_oir_devuelve_cadena_vacia(self):
        self.assertEqual(voz.escuchar(self.destino, voz.TranscriptorFalso()), "")



class TestLoQueSeDiceCuandoFaltaElPaquete(unittest.TestCase):
    """El mensaje de «no está instalado» es el que más se lee, y estaba mal.

    Decía `pip install piper-tts` a secas. En una máquina con más de un Python
    —o sea, en todas— eso manda al `pip` equivocado y el paquete acaba en un
    sitio que el intérprete que falla no mira. El único `pip` que sirve es el
    de ese intérprete.
    """

    def sin_paquete(self, motor):
        """El import de piper/faster_whisper falla, como en una máquina pelada."""
        import builtins

        real = builtins.__import__

        def falla(nombre, *args, **kwargs):
            if nombre.split(".")[0] == motor:
                raise ImportError(f"No module named {motor!r}")
            return real(nombre, *args, **kwargs)

        builtins.__import__ = falla
        self.addCleanup(setattr, builtins, "__import__", real)

    def test_piper_manda_al_pip_de_este_interprete(self):
        self.sin_paquete("piper")
        with self.assertRaises(RuntimeError) as caso:
            voz.Piper()._cargar()
        mensaje = str(caso.exception)
        self.assertIn("piper-tts", mensaje)
        self.assertIn(sys.executable, mensaje)
        self.assertIn("-m pip install", mensaje)

    def test_whisper_manda_al_pip_de_este_interprete(self):
        self.sin_paquete("faster_whisper")
        with self.assertRaises(RuntimeError) as caso:
            voz.Whisper()._cargar()
        mensaje = str(caso.exception)
        self.assertIn("faster-whisper", mensaje)
        self.assertIn(sys.executable, mensaje)

    def test_el_diagnostico_no_suelta_un_modulenotfound_pelado(self):
        # Era el fallo: `python3 voz.py` importaba el paquete antes de cargar
        # el motor, así que salía el ImportError crudo y se perdían las
        # instrucciones. Primero el motor, que sabe explicarse.
        self.sin_paquete("piper")
        with self.assertRaises(RuntimeError):
            voz._probar_boca("hola", Path("/tmp/no-se-usa.wav"))


if __name__ == "__main__":
    unittest.main()
