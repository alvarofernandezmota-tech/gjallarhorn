"""Pruebas del agente entero: oreja → cerebro → acción → frase.

Con un transcriptor falso: lo que se prueba aquí no es Whisper —eso es de
Whisper— sino que la tubería de encima haga lo correcto con lo que oye. Y con
las rutas en un temporal, como en `test_acciones.py`: **el diario de verdad no
se toca**.
"""

import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401 — fija MIDGAROR_DATOS antes de cualquier import

import acciones  # noqa: E402
import agente  # noqa: E402
import cerebro  # noqa: E402
import midgaror  # noqa: E402
import voz  # noqa: E402

diario = midgaror.modulo("diario")
organizar = midgaror.modulo("organizar_diario")


class CasoAgente(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        for mod in (diario, organizar):
            anterior = mod.CARPETA_PERSONAL
            mod.CARPETA_PERSONAL = self.base / "personal"
            self.addCleanup(setattr, mod, "CARPETA_PERSONAL", anterior)


class TestElCerebroDecide(unittest.TestCase):
    def decide(self, frase):
        return cerebro.decidir(frase)

    def test_apunta_que_va_al_diario_sin_el_que(self):
        accion, args = self.decide("apunta que hoy he dormido fatal")
        self.assertEqual(accion, "apuntar_en_diario")
        self.assertEqual(args["texto"], "hoy he dormido fatal")

    def test_recuerdame_es_una_tarea(self):
        accion, args = self.decide("recuérdame llamar al dentista el jueves")
        self.assertEqual(accion, "crear_tarea")
        self.assertEqual(args["texto"], "llamar al dentista el jueves")

    def test_tengo_que_tambien_es_una_tarea(self):
        accion, _ = self.decide("tengo que comprar pan")
        self.assertEqual(accion, "crear_tarea")

    def test_cita_es_una_cita(self):
        accion, args = self.decide("cita con el fisio el martes a las 10")
        self.assertEqual(accion, "crear_cita")
        self.assertIn("fisio", args["texto"])

    def test_he_hecho_marca_un_habito(self):
        accion, args = self.decide("he hecho gimnasio")
        self.assertEqual(accion, "marcar_habito")
        self.assertEqual(args["nombre"], "gimnasio")

    def test_una_pregunta_no_escribe_nada(self):
        for frase in ("qué tengo hoy", "que hay mañana", "cómo va la semana"):
            accion, args = self.decide(frase)
            self.assertEqual(accion, "que_hay_hoy", frase)
            self.assertEqual(args, {}, frase)

    def test_leeme_el_diario_lee(self):
        accion, _ = self.decide("léeme el diario")
        self.assertEqual(accion, "leer_diario")

    def test_sin_tildes_decide_igual(self):
        # Quien dicta no pone tildes, y Whisper a veces tampoco.
        self.assertEqual(self.decide("recuerdame comprar pan")[0], "crear_tarea")
        self.assertEqual(self.decide("que tengo hoy")[0], "que_hay_hoy")

    def test_lo_que_no_entiende_va_al_diario_y_no_se_pierde(self):
        # La regla que más importa de todo el cerebro.
        frase = "pues no sé, el día ha sido raro"
        accion, args = self.decide(frase)
        self.assertEqual(accion, "apuntar_en_diario")
        self.assertEqual(args["texto"], frase)

    def test_una_orden_a_secas_no_inventa_una_tarea_vacia(self):
        accion, args = self.decide("recuérdame")
        self.assertEqual(accion, "apuntar_en_diario")
        self.assertEqual(args["texto"], "recuérdame")

    def test_una_frase_vacia_se_queja(self):
        with self.assertRaises(ValueError):
            self.decide("   ")


class TestElAgenteResponde(CasoAgente):
    def test_hablarle_al_diario_escribe_de_verdad(self):
        respuesta = agente.responder("apunta que hoy he ido a correr")
        entrada = next((self.base / "personal").rglob("*.md"))
        self.assertIn("hoy he ido a correr", entrada.read_text(encoding="utf-8"))
        self.assertIn("Apuntado", respuesta)

    def test_un_fallo_de_una_accion_se_dice_en_vez_de_tragarse(self):
        def revienta(**_):
            raise RuntimeError("el disco está lleno")
        anterior = acciones.ACCIONES["apuntar_en_diario"].funcion
        objeto = acciones.ACCIONES["apuntar_en_diario"]
        acciones.ACCIONES["apuntar_en_diario"] = acciones.Accion(
            objeto.nombre, objeto.descripcion, revienta,
            objeto.propiedades, objeto.obligatorios)
        self.addCleanup(acciones.ACCIONES.__setitem__, "apuntar_en_diario", objeto)
        self.assertEqual(anterior, objeto.funcion)

        respuesta = agente.responder("apunta que algo")
        self.assertIn("no he podido", respuesta)
        self.assertIn("disco", respuesta)


class TestDeAudioARespuesta(CasoAgente):
    def test_la_tuberia_entera_con_una_oreja_de_mentira(self):
        oreja = voz.TranscriptorFalso("apunta que el día ha ido bien")
        dicho, respuesta = agente.escuchar_y_responder(Path("nota.ogg"), oreja)
        self.assertEqual(dicho, "apunta que el día ha ido bien")
        self.assertIn("Apuntado", respuesta)
        self.assertEqual(oreja.oidos, [Path("nota.ogg")])
        entrada = next((self.base / "personal").rglob("*.md"))
        self.assertIn("el día ha ido bien", entrada.read_text(encoding="utf-8"))

    def test_un_audio_mudo_lo_dice_y_no_escribe(self):
        dicho, respuesta = agente.escuchar_y_responder(Path("silencio.ogg"),
                                                       voz.TranscriptorFalso(""))
        self.assertEqual(dicho, "")
        self.assertIn("No he oído nada", respuesta)
        self.assertFalse((self.base / "personal").exists())


class TestLaOreja(unittest.TestCase):
    def test_whisper_no_se_carga_hasta_que_se_usa(self):
        # El import de faster_whisper va dentro a propósito: si estuviera
        # arriba, estas pruebas descargarían un modelo de cientos de megas.
        oreja = voz.Whisper()
        self.assertIsNone(oreja._motor)

    def test_un_audio_que_no_existe_se_dice_antes_de_cargar_el_modelo(self):
        with self.assertRaises(FileNotFoundError):
            voz.Whisper().transcribir(Path("/no/existe/nada.ogg"))

    def test_el_idioma_va_fijado_a_espanol(self):
        # Sin fijarlo, una frase corta se detecta como portugués o gallego.
        self.assertEqual(voz.Whisper().idioma, "es")

    def test_escuchar_limpia_los_espacios(self):
        self.assertEqual(
            voz.escuchar(Path("x.ogg"), voz.TranscriptorFalso("  hola  ")), "hola")


if __name__ == "__main__":
    unittest.main()
