"""Pruebas del buscador del conocimiento: que encuentre, y que se calle.

Lo segundo importa más. Un buscador que contesta casi siempre le suelta a
quien llama la respuesta de otra pregunta, y eso es peor que un recado: el
cliente se va con una información falsa y nadie se entera.

El caso que obligó a pesar el título por encima del cuerpo está aquí: la
respuesta de «¿hace falta cita?» nombra el tinte, las mechas y los
recogidos, así que cualquiera que dijera «tinte» se llevaba esa respuesta en
vez de su precio.
"""

import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

import frases  # noqa: E402
import negocio as negocios  # noqa: E402
import rag  # noqa: E402


class CasoRag(unittest.TestCase):
    def setUp(self):
        rag.olvidar()
        self.addCleanup(rag.olvidar)
        self.base = negocios.cargar("peluqueria").conocimiento

    def responde(self, frase):
        pasaje = rag.responder(frase, self.base)
        return pasaje.texto if pasaje else None


class TestEncuentraLoQueEstaEscrito(CasoRag):
    def test_la_pregunta_dicha_de_otra_forma(self):
        self.assertIn("Bizum", self.responde("¿se puede pagar con tarjeta?"))
        self.assertIn("Bizum", self.responde("oiga, ¿aceptan bizum ahí?"))

    def test_donde_estais(self):
        self.assertIn("centro", self.responde("¿dónde estáis exactamente?"))

    def test_el_horario(self):
        self.assertIn("martes a viernes", self.responde("¿qué horario tenéis?"))

    def test_como_anulo(self):
        self.assertIn("cuatro horas", self.responde("¿y si no puedo ir?"))

    def test_el_texto_se_da_tal_cual(self):
        # Sin parafrasear y sin modelo: lo escribió el dueño.
        escrito = (Path(self.base) / "faq.md").read_text(encoding="utf-8")
        self.assertIn(self.responde("¿aceptáis tarjeta?"), escrito)

    def test_dice_de_donde_ha_salido(self):
        pasaje = rag.responder("¿aceptáis tarjeta?", self.base)
        self.assertEqual(pasaje.fuente, "faq.md")
        self.assertIn("tarjeta", pasaje.titulo.lower())


class TestSeCallaCuandoNoEstaClaro(CasoRag):
    def test_lo_que_no_esta_escrito(self):
        self.assertIsNone(self.responde("¿hacéis uñas?"))
        self.assertIsNone(self.responde("¿vendéis pelucas?"))

    def test_una_frase_sin_palabras_con_contenido(self):
        self.assertIsNone(self.responde("pues nada, gracias"))
        self.assertIsNone(self.responde(""))

    def test_nombrar_un_servicio_no_es_preguntar_por_la_faq(self):
        # El caso que costó el peso del título: la respuesta de «¿hace falta
        # cita?» nombra el tinte, y esto es una pregunta de precio.
        self.assertIsNone(self.responde("oye, ¿hacéis lo del color ese?"))

    def test_decir_cuando_es_pedir_hora_no_preguntar_por_la_faq(self):
        self.assertIsNone(self.responde("me paso el jueves a las cinco a por un tinte"))
        self.assertIsNone(self.responde("¿me lo podéis hacer mañana?"))

    def test_un_empate_no_se_contesta(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        (base / "faq.md").write_text(
            "**¿Aceptáis tarjeta?**\nSí.\n\n**¿Vendéis tarjeta regalo?**\nTambién.\n",
            encoding="utf-8")
        self.assertIsNone(rag.responder("tarjeta", base))
        # Preguntando por una de las dos con todas las letras, sí contesta.
        self.assertEqual(rag.responder("¿vendéis tarjetas regalo?", base).texto, "También.")


class TestCualquierMdVale(CasoRag):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.nueva = Path(self.tmp.name)
        (self.nueva / "faq.md").write_text("**¿Qué horario tenéis?**\nDe 10 a 20.\n",
                                           encoding="utf-8")

    def test_un_fichero_nuevo_se_indexa_sin_tocar_codigo(self):
        (self.nueva / "aparcamiento.md").write_text(
            "## Aparcamiento\nHay parking público en la misma calle, dos euros la hora.\n",
            encoding="utf-8")
        rag.olvidar()
        pasaje = rag.responder("¿hay aparcamiento cerca?", self.nueva)
        self.assertIn("parking público", pasaje.texto)
        self.assertEqual(pasaje.fuente, "aparcamiento.md")

    def test_editar_un_fichero_se_nota_sin_reiniciar(self):
        fichero = self.nueva / "faq.md"
        self.assertIn("De 10 a 20", rag.responder("¿qué horario tenéis?", self.nueva).texto)
        fichero.write_text("**¿Qué horario tenéis?**\nDe 9 a 21, todo el día.\n",
                           encoding="utf-8")
        import os
        os.utime(fichero, (0, 0))     # que la fecha cambie seguro, aunque el reloj no
        self.assertIn("De 9 a 21", rag.responder("¿qué horario tenéis?", self.nueva).texto)

    def test_una_carpeta_vacia_no_revienta(self):
        vacia = Path(self.tmp.name) / "vacia"
        vacia.mkdir()
        self.assertIsNone(rag.responder("lo que sea", vacia))
        self.assertEqual(rag.buscar("lo que sea", vacia), [])


class TestLoQueNoSeIndexa(CasoRag):
    def test_las_filas_de_la_tabla_de_precios_no_son_pasajes(self):
        # Un precio se consulta, no se «recupera por parecido». Ninguna fila
        # de tarifas.md puede acabar siendo la respuesta a nada.
        for pasaje in rag.indice(self.base).pasajes:
            self.assertNotIn("€", pasaje.texto)

    def test_los_comentarios_de_la_plantilla_no_se_indexan(self):
        for pasaje in rag.indice(self.base).pasajes:
            self.assertNotIn("no lo lee nadie", pasaje.texto)
            self.assertNotIn("ESTE ES EL FICHERO", pasaje.texto)

    def test_un_encabezado_sin_nada_debajo_no_es_un_pasaje(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        (base / "vacio.md").write_text("# Promociones\n\n## Verano\n", encoding="utf-8")
        self.assertEqual(rag.indice(base).pasajes, [])


class TestLosSinonimosValenTambienAqui(CasoRag):
    def test_lo_que_dice_el_cliente_y_lo_que_escribio_el_dueño(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        (base / "faq.md").write_text(
            "**¿Cuánto dura un tinte?**\nHora y media, contando el lavado.\n",
            encoding="utf-8")
        (base / "frases.toml").write_text('[sinonimos]\ntinte = ["color", "teñir"]\n',
                                          encoding="utf-8")
        frases.olvidar()
        self.addCleanup(frases.olvidar)
        rag.olvidar()
        self.assertIn("Hora y media", rag.responder("¿cuánto dura teñir?", base).texto)


class TestElBanco(CasoRag):
    """El banco con el que están puestos los números de `rag.py`.

    Los umbrales no se afinan a ojo ni «probando una frase»: se probaron
    todas las combinaciones contra esta lista y se eligió una del centro de
    la zona que no falla ninguna. Esta prueba es la que avisa el día que
    alguien mueva una constante y lo empeore para otra frase.
    """

    CONTESTA = [
        ("¿se puede pagar con tarjeta?", "tarjeta"),
        ("oiga, ¿aceptan bizum ahí?", "tarjeta"),
        ("¿dónde estáis exactamente?", "dónde"),
        ("¿cuál es la dirección?", "dónde"),
        ("¿qué horario tenéis?", "horario"),
        ("¿y si no puedo ir?", "no puedo ir"),
        ("¿cómo anulo la cita?", "no puedo ir"),
        ("¿tenéis aparcamiento?", "aparcamiento"),
        ("¿usáis amoniaco?", "productos"),
        ("¿puedo llevar mi propio tinte de casa?", "traer"),
        ("¿hacéis peinados de novia?", "novias"),
        ("me caso en junio, ¿hacéis recogidos de boda?", "novias"),
        ("¿le cortáis el pelo a los niños?", "niños"),
        ("¿atendéis a niños pequeños?", "niños"),
    ]

    CALLA = [
        "pues nada, gracias",
        "",
        "¿hacéis uñas?",
        "oye, ¿hacéis lo del color ese?",
        "me gustaría pasarme el jueves a las cinco de la tarde a por un tinte",
        "¿cuánto vale un tinte?",
        "quiero cita para mañana a las once",
        "¿me pone con una persona?",
        "no me he enterado, ¿me lo repites?",
        "pues nada, hasta otra",
    ]

    def test_contesta_lo_que_tiene_que_contestar(self):
        for frase, esperado in self.CONTESTA:
            with self.subTest(frase=frase):
                pasaje = rag.responder(frase, self.base)
                self.assertIsNotNone(pasaje, "se ha callado y esto está escrito")
                self.assertIn(esperado.lower(), pasaje.titulo.lower())

    def test_se_calla_con_todo_lo_demas(self):
        for frase in self.CALLA:
            with self.subTest(frase=frase):
                pasaje = rag.responder(frase, self.base)
                self.assertIsNone(pasaje, f"ha contestado «{pasaje.titulo if pasaje else ''}»")


class TestParaElModelo(CasoRag):
    def test_el_contexto_lleva_la_fuente_y_va_acotado(self):
        contexto = rag.contexto("¿aceptáis tarjeta?", self.base)
        self.assertIn("faq.md", contexto)
        self.assertIn("Bizum", contexto)
        self.assertLessEqual(len(rag.contexto("cita tarjeta horario dirección", self.base,
                                              tope=5, limite=100)), 100)

    def test_sin_nada_que_aportar_el_contexto_va_vacio(self):
        self.assertEqual(rag.contexto("pelucas", self.base), "")


if __name__ == "__main__":
    unittest.main()
