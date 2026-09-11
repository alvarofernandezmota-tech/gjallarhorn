"""Pruebas de frases.py — las palabras, que ahora las pone quien lleva el negocio.

Este fichero lo edita alguien que no programa, a las once de la noche, con el
negocio abierto mañana. Así que lo que se prueba aquí no es que sepa leer TOML:
es que **una errata no pueda tumbar una llamada**, y que lo que no se puede
cambiar siga sin poder cambiarse.
"""

import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

import avisos  # noqa: E402
import frases  # noqa: E402
import recepcion  # noqa: E402


class CasoFrases(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(frases.olvidar)
        frases.olvidar()
        self.base = Path(self._tmp.name)
        (self.base / "tarifas.md").write_text(
            "| Servicio | Precio |\n|---|---|\n| Tinte | 45 € |\n", encoding="utf-8")
        (self.base / "faq.md").write_text("**¿Horario?**\nDe 10 a 20.\n",
                                          encoding="utf-8")

    def escribir(self, toml: str):
        (self.base / "frases.toml").write_text(toml, encoding="utf-8")
        frases.olvidar()
        return frases.cargar(self.base)


class TestSeCambianSinTocarCodigo(CasoFrases):
    def test_lo_que_dice_el_agente(self):
        f = self.escribir('[dice]\nrecado = "Lo apunto y te llamamos, ¡chao!"\n')
        self.assertEqual(f.decir("recado"), "Lo apunto y te llamamos, ¡chao!")

    def test_lo_que_entiende_del_cliente(self):
        # Aquí es donde entra la forma de hablar de cada sitio.
        f = self.escribir('[entiende]\nprecio = ["cuanto raska", "precio"]\n')
        self.assertTrue(f.reconoce("precio", "oye cuanto raska un tinte"))

    def test_una_lista_propia_sustituye_a_la_de_fabrica(self):
        # Se sustituye y no se suma a propósito: quien escribe su lista quiere
        # la suya, no la suya más la que no ha visto.
        f = self.escribir('[entiende]\nprecio = ["cuanto raska"]\n')
        self.assertFalse(f.reconoce("precio", "cuanto vale un tinte"))

    def test_lo_que_no_se_toca_se_queda_como_estaba(self):
        f = self.escribir('[dice]\nrecado = "otra cosa"\n')
        self.assertEqual(f.decir("despedida"), frases.DICE["despedida"])

    def test_sin_fichero_funciona_igual(self):
        f = frases.cargar(self.base)
        self.assertEqual(f.decir("recado"), frases.DICE["recado"])


class TestUnaErrataNoTumbaLaLlamada(CasoFrases):
    def test_un_hueco_mal_escrito_no_levanta(self):
        # Lo peor que podría pasar: que `{fehca}` cuelgue a un cliente.
        f = self.escribir('[dice]\npide_hora = "Vale, el {fehca}. ¿A qué hora?"\n')
        dicho = f.decir("pide_hora", fecha="el jueves 17", servicio="")
        self.assertEqual(dicho, frases.DICE["pide_hora"].format(
            fecha="el jueves 17", servicio=""))

    def test_y_deja_aviso_para_que_se_arregle(self):
        f = self.escribir('[dice]\npide_hora = "Vale, el {fehca}."\n')
        f.decir("pide_hora", fecha="el jueves 17", servicio="")
        ultimo = avisos.listar()[0]
        self.assertEqual(ultimo["tipo"], "fallo")
        self.assertIn("pide_hora", ultimo["texto"])
        self.assertIn("fehca", ultimo["texto"])

    def test_la_conversacion_entera_aguanta_con_las_frases_rotas(self):
        self.escribir('[dice]\npide_dia = "{loquesea}"\ncierra_cita = "{otro}"\n')
        llamada = recepcion.Conversacion(self.base)
        for frase in ("quiero cita", "el jueves", "a las cinco de la tarde", "Álvaro"):
            self.assertTrue(llamada.atender(frase).texto.strip())


class TestLosErroresSeVenAlArrancar(CasoFrases):
    """`problemas()` corre al arrancar: una errata se ve antes de que llame nadie."""

    def test_un_hueco_que_no_existe_en_esa_frase(self):
        self.escribir('[dice]\npide_dia = "Hola {fehca}"\n')
        problemas = frases.problemas(self.base)
        self.assertTrue(any("fehca" in p for p in problemas))
        self.assertTrue(any("{servicio}" in p for p in problemas),
                        "no dice cuáles sí puede usar")

    def test_una_frase_que_el_agente_no_dice(self):
        self.escribir('[dice]\nchistes = "toc toc"\n')
        self.assertTrue(any("chistes" in p for p in frases.problemas(self.base)))

    def test_una_intencion_que_no_existe(self):
        self.escribir('[entiende]\nbailar = ["chachacha"]\n')
        self.assertTrue(any("bailar" in p for p in frases.problemas(self.base)))

    def test_una_seccion_inventada(self):
        self.escribir('[cosas]\na = 1\n')
        self.assertTrue(any("[cosas]" in p for p in frases.problemas(self.base)))

    def test_un_toml_roto_se_explica_en_vez_de_reventar(self):
        (self.base / "frases.toml").write_text('[dice\nmal = ', encoding="utf-8")
        problemas = frases.problemas(self.base)
        self.assertTrue(problemas)
        self.assertIn("TOML", problemas[0])

    def test_un_fichero_correcto_no_da_problemas(self):
        self.escribir('[dice]\nrecado = "vale"\n[entiende]\nprecio = ["cuanto"]\n')
        self.assertEqual(frases.problemas(self.base), [])

    def test_el_de_la_peluqueria_esta_bien(self):
        import negocio as negocios
        self.assertEqual(frases.problemas(negocios.cargar("peluqueria").conocimiento), [])


class TestLoQueNoSePuedeCambiar(CasoFrases):
    def test_el_saludo_no_esta_entre_las_frases_editables(self):
        # Si lo estuviera, se podría quitar el aviso de sistema automático
        # editando un fichero de texto. Va en negocio.py, que lo impone.
        self.assertNotIn("saludo", frases.DICE)
        self.assertTrue(frases.revisar({"saludo": "Hola"}))

    def test_ninguna_frase_puede_meter_un_precio_inventado(self):
        # Los huecos de precio solo existen en las frases que los reciben de
        # la tabla. No hay forma de escribir un número «fijo» que el agente
        # cante como si fuera una tarifa.
        f = self.escribir('[dice]\nrecado = "Son unos 40 €, más o menos."\n')
        # Se puede escribir, claro: es texto libre. Lo que se comprueba es que
        # el camino del precio NO pasa por ahí.
        self.assertEqual(f.decir("precio_uno", servicio="Tinte", precio="45 €",
                                 duracion=""), "Tinte: 45 €.")


if __name__ == "__main__":
    unittest.main()
