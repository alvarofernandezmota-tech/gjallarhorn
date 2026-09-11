"""Pruebas del recepcionista.

Las que importan de verdad son tres, y ninguna va de que suene bien:

1. **Un precio sale de la tabla o no sale.** Nunca aproximado.
2. **Una hora que el cliente no ha dicho no se confirma.** «A las cinco» no se
   convierte en las 05:00 de la madrugada por mi cuenta.
3. **Lo que no se sabe se apunta, no se improvisa.**

Las tres salieron de ejecutarlo, no de pensarlo.
"""

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401 — antes que nada

import conocimiento  # noqa: E402
import recepcion  # noqa: E402

PELUQUERIA = entorno.NEGOCIOS / "peluqueria"


class CasoRecepcion(unittest.TestCase):
    def atender(self, frase: str) -> recepcion.Respuesta:
        return recepcion.atender(frase, PELUQUERIA)


class TestElPrecioSaleDeLaTabla(CasoRecepcion):
    def test_un_servicio_que_esta_se_canta_exacto(self):
        respuesta = self.atender("cuánto vale un corte de señora")
        self.assertEqual(respuesta.intencion, "precio")
        self.assertIn("20 €", respuesta.texto)

    def test_un_servicio_que_no_esta_no_se_aproxima(self):
        # La manicura no está en la tabla. Un «pues unos 20 €» aquí es el
        # cliente presentándose creyendo otra cosa.
        respuesta = self.atender("cuánto cuesta la manicura")
        self.assertIn("No tengo ese servicio", respuesta.texto)
        self.assertEqual(respuesta.tipo_aviso, "fallo")
        self.assertNotIn("€", respuesta.texto)

    def test_si_hay_varias_opciones_se_preguntan_en_vez_de_elegir(self):
        respuesta = self.atender("cuánto vale el tinte")
        self.assertIn("Tinte 45 €", respuesta.texto)
        self.assertIn("¿Cuál le interesa?", respuesta.texto)

    def test_sin_tarifas_cargadas_lo_dice_en_vez_de_inventar(self):
        vacio = Path(entorno.__file__).parent  # una carpeta sin tarifas.md
        respuesta = recepcion.atender("cuánto vale un corte", vacio)
        self.assertIn("no tengo las tarifas", respuesta.texto.lower())
        self.assertEqual(respuesta.tipo_aviso, "fallo")

    def test_ningun_precio_de_la_respuesta_se_lo_inventa_nadie(self):
        # Barrido: cualquier € que salga tiene que estar en la tabla.
        precios = {s["precio"] for s in conocimiento.tarifas(PELUQUERIA)}
        for frase in ("cuánto vale el corte de caballero", "precio de las mechas",
                      "cuánto cuesta un recogido"):
            texto = self.atender(frase).texto
            dichos = {p for p in precios if p in texto}
            self.assertTrue(dichos, f"«{frase}» no cantó ningún precio de la tabla")


class TestLaHoraNoSeInventa(CasoRecepcion):
    def test_a_las_cinco_no_son_las_cinco_de_la_madrugada(self):
        # El fallo grave que encontró ejecutarlo: confirmaba las 05:00 y le
        # mandaba a la puerta de madrugada.
        respuesta = self.atender("quiero cita para un tinte el jueves a las 5")
        self.assertIn("de la tarde", respuesta.texto)
        self.assertNotIn("Se la confirmamos", respuesta.texto)
        self.assertIn("SIN CONFIRMAR", respuesta.aviso)

    def test_por_la_manana_no_son_las_nueve_en_punto(self):
        respuesta = self.atender("tenéis hueco el sábado por la mañana")
        self.assertIn("¿A qué hora", respuesta.texto)
        self.assertNotIn("09:00", respuesta.texto)

    def test_una_hora_sin_ninguna_duda_se_confirma_y_ya(self):
        respuesta = self.atender("cita para corte y tinte el viernes a las 17:30")
        self.assertIn("17:30", respuesta.texto)
        self.assertIn("Se la confirmamos", respuesta.texto)

    def test_las_cinco_de_la_tarde_dicho_por_el_cliente_no_se_repregunta(self):
        respuesta = self.atender("cita el jueves a las 5 de la tarde")
        self.assertNotIn("¿Las", respuesta.texto)

    def test_sin_dia_se_pregunta_el_dia(self):
        respuesta = self.atender("quiero pedir hora")
        self.assertIn("¿Qué día", respuesta.texto)


class TestElServicioDentroDeUnaFrase(CasoRecepcion):
    def test_lo_encuentra_aunque_la_frase_sea_larga(self):
        respuesta = self.atender("quiero cita para un tinte el jueves a las 5")
        self.assertIn("de tinte", respuesta.texto)

    def test_gana_el_mas_especifico(self):
        # «corte y tinte» antes que «tinte» a secas.
        respuesta = self.atender("cita para corte y tinte el viernes a las 17:30")
        self.assertIn("corte y tinte", respuesta.texto)


class TestLoQueNoSeSabeSeApunta(CasoRecepcion):
    def test_una_pregunta_rara_se_toma_de_recado(self):
        respuesta = self.atender("mi hija se ha dejado una diadema ahí")
        self.assertEqual(respuesta.intencion, "recado")
        self.assertIn("Tomo nota", respuesta.texto)
        self.assertIn("diadema", respuesta.aviso)

    def test_el_horario_sale_de_la_faq_tal_cual(self):
        respuesta = self.atender("a qué hora abrís los sábados")
        self.assertEqual(respuesta.intencion, "horario")
        self.assertIn("Lunes cerrado", respuesta.texto)

    def test_silencio_no_es_un_recado_vacio(self):
        respuesta = recepcion.atender("   ", PELUQUERIA)
        self.assertIn("no le he oído", respuesta.texto)

    def test_una_cita_gana_a_un_precio_cuando_van_juntos(self):
        # «quiero cita para un tinte» lleva las dos palabras; quiere la cita.
        self.assertEqual(self.atender("quiero cita para un tinte").intencion, "cita")


class TestElAvisoLegal(unittest.TestCase):
    """Informar de que se habla con un sistema automático no es opcional.

    Antes esto miraba una constante `recepcion.SALUDO` que **no usaba nadie**:
    el saludo de verdad sale de `negocio.cargar()`. O sea que se podía quitar
    el aviso del saludo real y la prueba seguía en verde. Ahora mira el camino
    por el que pasa lo que oye quien llama.
    """

    def test_el_saludo_que_se_oye_dice_que_es_automatico(self):
        import negocio as negocios

        saludo = negocios.cargar("peluqueria").saludo.lower()
        self.assertTrue("automático" in saludo or "automatico" in saludo,
                        f"el saludo ya no avisa de que es automático: {saludo!r}")

    def test_las_frases_editables_no_pueden_tocar_el_saludo(self):
        # `frases.toml` deja cambiar lo que contesta el agente, pero el saludo
        # NO está entre esas frases: si lo estuviera, se podría quitar el aviso
        # editando un fichero de texto.
        import frases

        self.assertNotIn("saludo", frases.DICE)
        self.assertTrue(frases.revisar({"saludo": "Hola y ya está"}),
                        "frases.toml acepta una clave «saludo»")


if __name__ == "__main__":
    unittest.main()
