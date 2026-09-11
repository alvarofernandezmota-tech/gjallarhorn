"""Pruebas de negocio.py y del bucle de llamada entero.

Lo que se vigila aquí:

1. **Copiar una carpeta da de alta un negocio**, sin tocar código.
2. **El aviso de que es automático no se puede quitar** editando un `.toml`.
3. **Una llamada deja rastro aunque falle la voz.** Perder la contestación es
   malo; perder el registro de que alguien llamó, peor.
"""

import shutil
import os
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401 — antes que nada

from guardado import avisos  # noqa: E402
from negocio import negocio as negocios  # noqa: E402
from mente import recepcion  # noqa: E402
from telefono import voz  # noqa: E402


class TestDarDeAltaUnNegocio(unittest.TestCase):
    def test_la_peluqueria_de_ejemplo_carga(self):
        n = negocios.cargar("peluqueria")
        self.assertEqual(n.nombre, "Peluquería")
        self.assertTrue((n.conocimiento / "tarifas.md").exists())

    def test_una_carpeta_con_los_dos_markdown_ya_es_un_negocio(self):
        # Sin negocio.toml. Pedir un fichero de configuración para dar de alta
        # una peluquería sería ponerse exquisito.
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "mi-negocio"
            ruta.mkdir()
            (ruta / "tarifas.md").write_text("| Servicio | Precio |\n|---|---|\n| X | 1 € |\n",
                                             encoding="utf-8")
            n = negocios.cargar(ruta)
            self.assertEqual(n.nombre, "mi-negocio")
            self.assertIn("automático", n.saludo)

    def test_un_negocio_que_no_existe_dice_cuales_hay(self):
        with self.assertRaises(FileNotFoundError) as caso:
            negocios.cargar("no-existe")
        self.assertIn("peluqueria", str(caso.exception))

    def test_listar_los_da_de_alta_por_carpeta(self):
        self.assertIn("peluqueria", negocios.listar())


class TestElAvisoNoSePuedeQuitar(unittest.TestCase):
    def test_un_saludo_propio_sin_aviso_se_lo_lleva_puesto(self):
        # La garantía: no depende de que quien edita el .toml se acuerde.
        puesto = negocios._con_aviso("Hola, ha llamado a la peluquería.")
        self.assertIn("automático", puesto)
        self.assertTrue(puesto.startswith("Hola, ha llamado"))

    def test_si_ya_avisa_no_se_le_repite(self):
        propio = "Hola, le habla un asistente automático de la peluquería."
        self.assertEqual(negocios._con_aviso(propio), propio)

    def test_otras_formas_de_avisar_tambien_valen(self):
        for saludo in ("Hola, soy un robot.",
                       "Le atiende una inteligencia artificial.",
                       "Esto no es una persona."):
            self.assertEqual(negocios._con_aviso(saludo), saludo, saludo)

    def test_el_saludo_del_negocio_de_ejemplo_avisa(self):
        self.assertIn("automático", negocios.cargar("peluqueria").saludo)


class TestLaLlamadaEntera(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.ruta_avisos = self.base / "avisos.json"
        # Los avisos del bucle van al temporal, no a los de verdad.
        real = avisos._ruta
        avisos._ruta = lambda ruta=None: ruta if ruta is not None else self.ruta_avisos
        self.addCleanup(setattr, avisos, "_ruta", real)
        self.negocio = negocios.cargar("peluqueria")

    def llamar(self, *frases, locutor=None):
        audio = self.base / "entrada.ogg"
        audio.write_bytes(b"")
        return recepcion.llamada(audio, self.negocio,
                                 voz.TranscriptorFalso(*frases), locutor,
                                 carpeta_audio=self.base)

    def test_de_audio_a_respuesta_hablada(self):
        locutor = voz.LocutorFalso()
        resultado = self.llamar("cuánto vale un corte de señora", locutor=locutor)
        self.assertEqual(resultado["oido"], "cuánto vale un corte de señora")
        self.assertIn("20 €", resultado["dicho"])
        # Lo hablado no es lo escrito: «20 €, unos 45 min.» se lee «20 euros,
        # unos 45 minutos.». La respuesta escrita se queda como esta.
        self.assertEqual(locutor.dicho, [voz.para_decir(resultado["dicho"])])
        self.assertIn("euros", locutor.dicho[0])
        self.assertTrue(resultado["audio"].exists())

    def test_la_llamada_queda_registrada(self):
        self.llamar("cuánto vale un corte de señora")
        registrados = avisos.listar(ruta=self.ruta_avisos)
        self.assertEqual(len(registrados), 1)
        self.assertEqual(registrados[0]["tipo"], "tarifa")

    def test_si_la_voz_revienta_la_llamada_SIGUE_registrada(self):
        # Perder la contestación es malo. Perder el rastro de que alguien
        # llamó y preguntó un precio, peor.
        class Roto:
            def decir(self, texto, destino):
                raise RuntimeError("no hay voz instalada")

        resultado = self.llamar("cuánto vale el tinte", locutor=Roto())
        self.assertIsNone(resultado["audio"])
        self.assertIn("Tinte", resultado["dicho"])
        tipos = [a["tipo"] for a in avisos.listar(ruta=self.ruta_avisos)]
        self.assertIn("tarifa", tipos)
        self.assertIn("fallo", tipos)

    def test_un_audio_mudo_se_contesta_y_no_se_inventa_nada(self):
        resultado = self.llamar("")
        self.assertEqual(resultado["oido"], "")
        self.assertIn("no le he oído", resultado["dicho"])

    def test_no_se_sintetiza_una_respuesta_vacia(self):
        self.assertIsNone(voz.hablar("   ", self.base / "x.wav", voz.LocutorFalso()))


class TestLaBoca(unittest.TestCase):
    def test_piper_no_se_carga_hasta_que_se_usa(self):
        self.assertIsNone(voz.Piper()._motor)

    def test_la_voz_por_defecto_es_en_espanol(self):
        self.assertTrue(voz.VOZ_POR_DEFECTO.startswith("es_"))


if __name__ == "__main__":
    unittest.main()


class TestElRepoEsPublico(unittest.TestCase):
    """Un teléfono en los ficheros del negocio acaba en GitHub a la vista de todos."""

    def negocio_con(self, contenido, fichero="faq.md"):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        for nombre in ("tarifas.md", "faq.md"):
            (Path(tmp) / nombre).write_text("# x\n", encoding="utf-8")
        (Path(tmp) / fichero).write_text(contenido, encoding="utf-8")
        return negocios.cargar(tmp)

    def test_un_movil_en_la_faq_se_avisa(self):
        avisos_ = negocios.advertencias(self.negocio_con("Llámanos al 612 345 678"))
        self.assertEqual(len(avisos_), 1)
        self.assertIn("faq.md", avisos_[0])
        self.assertIn("público", avisos_[0])

    def test_con_prefijo_y_en_el_toml_tambien(self):
        avisos_ = negocios.advertencias(self.negocio_con('nombre = "X"\n# +34 912 345 678\n',
                                                        fichero="negocio.toml"))
        self.assertEqual(len(avisos_), 1)

    def test_un_precio_o_una_hora_no_es_un_telefono(self):
        self.assertEqual(negocios.advertencias(self.negocio_con(
            "| Tinte | 45 € | 90 min |\nAbrimos de 10:00 a 14:00. Somos 3 personas.",
            fichero="tarifas.md")), [])

    def test_la_peluqueria_de_ejemplo_esta_limpia(self):
        self.assertEqual(negocios.advertencias(negocios.cargar("peluqueria")), [])


class TestDondeVivenLosNegocios(unittest.TestCase):
    """El negocio puede vivir fuera del repo, y un error suyo se entiende.

    Las dos cosas salieron del mismo día: el dueño editó el `negocio.toml` del
    ejemplo —que es lo que el README le dice que puede hacer—, escribió un
    horario con la sintaxis cambiada, y lo que se vio fue un traceback de
    `tomllib` y 291 pruebas en rojo que no tenían nada que ver con él.
    """

    def escribir(self, texto, nombre="mi-negocio"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        carpeta = Path(tmp.name) / nombre
        carpeta.mkdir()
        (carpeta / "negocio.toml").write_text(texto, encoding="utf-8")
        return Path(tmp.name), carpeta

    def test_la_carpeta_de_negocios_se_puede_mover(self):
        raiz, _ = self.escribir('nombre = "El Mío"\n')
        antes = os.environ.get(negocios.VARIABLE)
        os.environ[negocios.VARIABLE] = str(raiz)
        self.addCleanup(lambda: os.environ.__setitem__(negocios.VARIABLE, antes)
                        if antes else os.environ.pop(negocios.VARIABLE, None))
        self.assertEqual(negocios.carpeta_negocios(), raiz.resolve())
        self.assertEqual(negocios.cargar("mi-negocio").nombre, "El Mío")
        self.assertIn("mi-negocio", negocios.listar())

    def test_un_toml_mal_escrito_dice_el_fichero_y_como_se_escribe(self):
        _, carpeta = self.escribir('nombre = "X"\n[horario]\nlunes = [1:00-00:00]\n')
        with self.assertRaises(ValueError) as fallo:
            negocios.cargar(carpeta)
        dicho = str(fallo.exception)
        self.assertIn("negocio.toml", dicho)
        self.assertIn('lunes = ["10:00-14:00"', dicho, "hay que decir cómo se escribe")
        self.assertNotIn("Traceback", dicho)

    def test_un_horario_con_tramos_imposibles_tambien_se_explica(self):
        _, carpeta = self.escribir('[horario]\nlunes = ["25:00-26:00"]\n')
        with self.assertRaises(ValueError) as fallo:
            negocios.cargar(carpeta)
        self.assertIn("negocio.toml", str(fallo.exception))

    def test_las_pruebas_no_dependen_del_negocio_que_trae_el_repo(self):
        # Lo que se rompió: la suite usaba `negocios/peluqueria`, que es de
        # quien lleva el negocio. Ahora el ejemplo de las pruebas es suyo.
        self.assertEqual(negocios.carpeta_negocios(), entorno.NEGOCIOS)
        self.assertTrue((entorno.NEGOCIOS / "peluqueria" / "tarifas.md").exists())
