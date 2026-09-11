"""Pruebas de conocimiento.py — las tarifas, sin inventarse un número.

Lo que más importa aquí: **un precio sale de la tabla, no de un modelo**. Un
agente que le canta a un cliente una cifra parafraseada es peor que uno que
dice «no lo sé».
"""

import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401 — antes que nada

from mente import conocimiento  # noqa: E402

TABLA = """# Tarifas

| Servicio | Precio | Duración |
|---|---|---|
| Revisión completa | 45 € | 60 min |
| Cambio de aceite y filtro | 60 € | 45 min |
| Presupuesto | gratis | 15 min |
"""


class CasoConocimiento(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def escribir(self, nombre: str, texto: str):
        (self.base / nombre).write_text(texto, encoding="utf-8")


class TestLeerLaTabla(CasoConocimiento):
    def test_saca_los_servicios_con_su_precio(self):
        self.escribir("tarifas.md", TABLA)
        servicios = conocimiento.tarifas(self.base)
        self.assertEqual(len(servicios), 3)
        self.assertEqual(servicios[0], {"servicio": "Revisión completa",
                                        "precio": "45 €", "duracion": "60 min"})

    def test_una_fila_torcida_se_salta_en_vez_de_adivinarse(self):
        # Adivinar qué quería decir una fila mal escrita es cómo se acaba
        # cantando un precio que no es.
        self.escribir("tarifas.md", TABLA + "| Fila rota | 20 € |\n")
        self.assertEqual(len(conocimiento.tarifas(self.base)), 3)

    def test_sin_fichero_no_revienta_y_devuelve_nada(self):
        self.assertEqual(conocimiento.tarifas(self.base), [])

    def test_la_linea_de_guiones_no_es_un_servicio(self):
        self.escribir("tarifas.md", TABLA)
        nombres = [s["servicio"] for s in conocimiento.tarifas(self.base)]
        self.assertNotIn("---", "".join(nombres))


class TestBuscarSinModelo(CasoConocimiento):
    def setUp(self):
        super().setUp()
        self.escribir("tarifas.md", TABLA)

    def test_encuentra_aunque_falten_tildes(self):
        # Whisper transcribe sin tilde a menudo, y quien habla no las dice.
        encontrado = conocimiento.buscar("cuanto vale la revision", self.base)
        self.assertEqual(encontrado[0]["precio"], "45 €")

    def test_encuentra_por_una_palabra_suelta(self):
        self.assertEqual(conocimiento.buscar("aceite", self.base)[0]["precio"], "60 €")

    def test_lo_que_no_esta_devuelve_vacio_en_vez_de_lo_mas_parecido(self):
        # Devolver «lo más parecido» a una pregunta sobre algo que no vendes es
        # exactamente cómo se promete un servicio que no existe.
        self.assertEqual(conocimiento.buscar("cambio de parabrisas", self.base), [])

    def test_una_pregunta_de_solo_palabras_vacias_no_devuelve_todo(self):
        self.assertEqual(conocimiento.buscar("cuanto cuesta", self.base), [])


class TestLoQueVeElModelo(CasoConocimiento):
    def test_el_prompt_lleva_tarifas_y_faq(self):
        self.escribir("tarifas.md", TABLA)
        self.escribir("faq.md", "**¿Horario?**\nDe 9 a 14.")
        texto = conocimiento.para_prompt(self.base)
        self.assertIn("TARIFAS", texto)
        self.assertIn("PREGUNTAS FRECUENTES", texto)
        self.assertIn("45 €", texto)
        self.assertIn("De 9 a 14", texto)

    def test_sin_conocimiento_el_prompt_va_vacio_y_no_con_cabeceras_huecas(self):
        self.assertEqual(conocimiento.para_prompt(self.base), "")

    def test_va_entero_y_sin_trocear(self):
        # Es la decisión: sin paso de recuperación no hay recuperación que se
        # equivoque de precio.
        self.escribir("tarifas.md", TABLA)
        texto = conocimiento.para_prompt(self.base)
        for servicio in conocimiento.tarifas(self.base):
            self.assertIn(servicio["precio"], texto)


class TestLaPlantillaVacia(CasoConocimiento):
    """Sin conocimiento, el agente no sabe nada — y eso tiene que notarse."""

    PLANTILLA_TARIFAS = """# Tarifas

<!--
  PLANTILLA — está vacía a propósito. Esto NO puede llegar al modelo.
  | Servicio | Precio |
  | Primera consulta | 40 € |
-->

| Servicio | Precio | Duración |
|---|---|---|
"""

    def test_las_instrucciones_de_la_plantilla_no_llegan_al_modelo(self):
        # Si llegaran, el modelo se creería que «PLANTILLA, está vacía a
        # propósito» es información del negocio, y el ejemplo de dentro del
        # comentario sería un precio real que cantarle a un cliente.
        self.escribir("tarifas.md", self.PLANTILLA_TARIFAS)
        texto = conocimiento.para_prompt(self.base)
        self.assertNotIn("PLANTILLA", texto)
        self.assertNotIn("40 €", texto)

    def test_una_tabla_sin_filas_no_es_una_tarifa(self):
        self.escribir("tarifas.md", self.PLANTILLA_TARIFAS)
        self.assertEqual(conocimiento.tarifas(self.base), [])

    def test_con_la_plantilla_el_prompt_va_completamente_vacio(self):
        # Ni siquiera la cabecera «### TARIFAS»: un título seguido de nada
        # invita al modelo a rellenar el hueco.
        self.escribir("tarifas.md", self.PLANTILLA_TARIFAS)
        self.escribir("faq.md", "# Preguntas frecuentes\n\n<!-- vacía -->\n")
        self.assertEqual(conocimiento.para_prompt(self.base), "")

    def test_dice_que_ficheros_siguen_sin_rellenar(self):
        self.escribir("tarifas.md", self.PLANTILLA_TARIFAS)
        self.escribir("faq.md", "# Preguntas frecuentes\n\n<!-- vacía -->\n")
        self.assertEqual(conocimiento.que_falta(self.base), ["tarifas.md", "faq.md"])
        self.assertFalse(conocimiento.esta_configurado(self.base))

    def test_una_sola_fila_de_verdad_ya_cuenta_como_rellenado(self):
        self.escribir("tarifas.md", self.PLANTILLA_TARIFAS + "| Primera consulta | 40 € | 45 min |\n")
        self.assertNotIn("tarifas.md", conocimiento.que_falta(self.base))
        self.assertIn("40 €", conocimiento.para_prompt(self.base))

    def test_la_plantilla_del_repo_esta_vacia_de_verdad(self):
        # Si alguien deja datos de ejemplo aquí, el agente se los canta a un
        # cliente creyendo que son de verdad.
        self.assertEqual(conocimiento.que_falta(), ["tarifas.md", "faq.md"])
        self.assertEqual(conocimiento.para_prompt(), "")


class TestCuandoTocaraRag(CasoConocimiento):
    def test_dice_si_cabe_y_cuanto_ocupa(self):
        self.escribir("tarifas.md", TABLA)
        cabe, tamano = conocimiento.cabe_en(base=self.base)
        self.assertTrue(cabe)
        self.assertGreater(tamano, 0)

    def test_avisa_cuando_deja_de_caber(self):
        # El día que esto sea False es el día de abrir la conversación del RAG,
        # con un número delante en vez de a ojo.
        self.escribir("faq.md", "línea de relleno\n" * 2000)
        cabe, tamano = conocimiento.cabe_en(base=self.base)
        self.assertFalse(cabe)
        self.assertGreater(tamano, conocimiento.LIMITE_COMODO)

    def test_la_plantilla_del_repo_cabe_de_sobra(self):
        cabe, tamano = conocimiento.cabe_en()
        self.assertTrue(cabe, f"ya no cabe: {tamano}")


if __name__ == "__main__":
    unittest.main()
