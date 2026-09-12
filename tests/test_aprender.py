"""Pruebas de lo que el agente no supo contestar.

Esto es lo que hace que el bot mejore con el uso, así que lo que se vigila
es que la lista sea **útil**: que junte las mismas preguntas aunque estén
dichas de otra forma, que diga en qué fichero se arregla cada una, y que no
se llene de ruido —«pues nada, gracias» no es una pregunta pendiente—.

Y una que no se puede caer: esto **no escribe** en tarifas.md ni en faq.md.
Lo que sabe el negocio lo escribe el negocio.
"""

import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402

from dueno import agentes  # noqa: E402
from dueno import aprender  # noqa: E402
from hugin.guardado import avisos  # noqa: E402
from hugin.negocio import negocio as negocios  # noqa: E402
from dueno import panel  # noqa: E402
from hugin.mente import recepcion  # noqa: E402

MADRID = ZoneInfo("Europe/Madrid")
VIERNES = datetime(2026, 9, 11, 10, 0, tzinfo=MADRID)
HOY = VIERNES.date()


class CasoAprender(unittest.TestCase):
    def setUp(self):
        entorno.aislar(self)
        self.negocio = negocios.cargar("peluqueria")

    def preguntar(self, *frases):
        """Una llamada por frase, como en la vida: se contesta y se apunta."""
        for frase in frases:
            llamada = recepcion.Conversacion(self.negocio.conocimiento)
            respuesta = llamada.atender(frase)
            if respuesta.aviso:
                avisos.registrar(respuesta.tipo_aviso, respuesta.aviso, respuesta.datos,
                                 ahora=VIERNES)
        return aprender.faltas(self.negocio.conocimiento, hoy=HOY)

    def titulos(self, lista):
        return [f.titulo for f in lista]


class TestLoQueNoSupoContestar(CasoAprender):
    def test_una_pregunta_que_no_esta_escrita_queda_pendiente(self):
        faltan = self.preguntar("¿tenéis wifi?")
        self.assertEqual(len(faltan), 1)
        self.assertEqual(faltan[0].que, "respuesta")
        self.assertEqual(faltan[0].donde, "faq.md")
        self.assertIn("wifi", faltan[0].titulo)

    def test_un_servicio_que_no_esta_en_la_tabla_manda_a_tarifas(self):
        faltan = self.preguntar("¿cuánto vale un masaje?")
        self.assertEqual(faltan[0].que, "tarifa")
        self.assertEqual(faltan[0].donde, "tarifas.md")

    def test_lo_mismo_preguntado_de_tres_formas_es_una_sola_linea(self):
        faltan = self.preguntar("¿hacéis uñas?", "¿y las uñas de gel?",
                                "quería preguntar por las uñas")
        self.assertEqual(len(faltan), 1, self.titulos(faltan))
        self.assertEqual(faltan[0].veces, 3)
        self.assertIn("uña", faltan[0].titulo)

    def test_el_ejemplo_que_se_enseña_es_el_mas_corto(self):
        faltan = self.preguntar("quería preguntar por las uñas", "¿hacéis uñas?")
        self.assertEqual(faltan[0].ejemplo, "¿hacéis uñas?")

    def test_el_singular_y_el_plural_son_lo_mismo(self):
        faltan = self.preguntar("¿hacéis masajes?", "¿tenéis masaje descontracturante?")
        self.assertEqual(len(faltan), 1, self.titulos(faltan))
        self.assertEqual(faltan[0].veces, 2)

    def test_lo_mas_preguntado_va_primero(self):
        faltan = self.preguntar("¿tenéis wifi?", "¿hacéis uñas?", "¿y las uñas?",
                                "las uñas, ¿las hacéis?")
        self.assertIn("uña", faltan[0].titulo)
        self.assertEqual(faltan[0].veces, 3)

    def test_el_precio_y_la_pregunta_suelta_no_se_mezclan(self):
        # Se arreglan en ficheros distintos, así que son dos líneas.
        faltan = self.preguntar("¿cuánto vale un masaje?", "¿hacéis masajes?")
        self.assertEqual({f.que for f in faltan}, {"tarifa", "respuesta"})

    def test_pedir_hablar_con_alguien_se_cuenta_aparte_y_no_se_arregla_escribiendo(self):
        faltan = self.preguntar("¿me pones con una persona?")
        self.assertEqual(faltan[0].que, "persona")
        self.assertEqual(faltan[0].donde, "")


class TestLoQueNoEntraEnLaLista(CasoAprender):
    def test_lo_que_si_supo_contestar_no_aparece(self):
        self.assertEqual(self.preguntar("¿cuánto vale un tinte?", "¿qué horario tenéis?",
                                        "¿aceptáis tarjeta?"), [])

    def test_una_muletilla_sin_contenido_no_es_una_pregunta_pendiente(self):
        self.assertEqual(self.preguntar("pues nada, gracias", "vale", "hola"), [])

    def test_lo_viejo_se_cae_de_la_lista(self):
        avisos.registrar("fallo", "Recado: «¿tenéis wifi?»",
                         {"falta": "respuesta", "frase": "¿tenéis wifi?"},
                         ahora=datetime(2026, 1, 1, tzinfo=MADRID))
        self.assertEqual(aprender.faltas(self.negocio.conocimiento, hoy=HOY), [])
        self.assertTrue(aprender.faltas(self.negocio.conocimiento, dias=400, hoy=HOY))

    def test_el_minimo_deja_solo_lo_repetido(self):
        self.preguntar("¿tenéis wifi?", "¿hacéis uñas?", "¿y las uñas?")
        solo_repetido = aprender.faltas(self.negocio.conocimiento, minimo=2, hoy=HOY)
        self.assertEqual(len(solo_repetido), 1)
        self.assertIn("uña", solo_repetido[0].titulo)

    def test_los_avisos_de_siempre_no_ensucian_la_lista(self):
        # Una cita reservada deja aviso, y no es nada pendiente de escribir.
        avisos.registrar("cita", "Reservada: tinte, el 2026-09-17", ahora=VIERNES)
        self.assertEqual(aprender.faltas(self.negocio.conocimiento, hoy=HOY), [])


class TestNoEscribeNada(CasoAprender):
    def test_no_toca_los_ficheros_del_negocio(self):
        antes = {f.name: f.read_bytes() for f in Path(self.negocio.conocimiento).glob("*")}
        self.preguntar("¿hacéis uñas?", "¿cuánto vale un masaje?")
        aprender.faltas(self.negocio.conocimiento, hoy=HOY)
        despues = {f.name: f.read_bytes() for f in Path(self.negocio.conocimiento).glob("*")}
        self.assertEqual(antes, despues, "el conocimiento lo escribe el dueño, no esto")


class TestElAgente(CasoAprender):
    def test_avisa_de_lo_repetido_y_calla_lo_suelto(self):
        self.preguntar("¿tenéis wifi?")
        mundo = agentes.mundo_de(self.negocio, ahora=VIERNES)
        self.assertIsNone(agentes.aprendizaje(mundo), "una vez es una anécdota")

        self.preguntar("¿hacéis uñas?", "¿y las uñas?")
        mundo = agentes.mundo_de(self.negocio, ahora=VIERNES)
        resultado = agentes.aprendizaje(mundo)
        self.assertIsNotNone(resultado)
        self.assertIn("no sé contestar", resultado.titulo)
        self.assertIn("faq.md", resultado.texto())

    def test_esta_dado_de_alta_en_la_colmena(self):
        self.assertIn("aprendizaje", agentes.TODOS)


class TestEnElPanel(CasoAprender):
    def test_sale_lo_que_no_supo_contestar(self):
        self.preguntar("¿hacéis uñas?", "¿cuánto vale un masaje?")
        datos = panel.vista(self.negocio, ahora=VIERNES)
        self.assertEqual(datos["cuentas"]["faltas"], 2)
        titulos = [f["titulo"] for f in datos["faltas"]]
        self.assertTrue(any("uña" in t for t in titulos), titulos)
        self.assertTrue(any(f["donde"] == "tarifas.md" for f in datos["faltas"]))

    def test_sin_nada_pendiente_la_lista_va_vacia(self):
        self.assertEqual(panel.vista(self.negocio, ahora=VIERNES)["faltas"], [])

    def test_no_se_enseñan_veinte(self):
        self.preguntar(*[f"¿tenéis {cosa}?" for cosa in
                         ("wifi", "parking", "sauna", "gimnasio", "cafetería",
                          "prensa", "televisión", "guardería")])
        self.assertLessEqual(len(panel.vista(self.negocio, ahora=VIERNES)["faltas"]),
                             panel.TOPE_FALTAS)


class TestLaOrdenEnLaTerminal(CasoAprender):
    def test_dice_que_no_hay_nada_cuando_no_lo_hay(self):
        import contextlib
        import io
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.assertEqual(aprender.main([]), 0)
        self.assertIn("Nada pendiente", salida.getvalue())

    def test_lista_lo_pendiente_con_su_fichero(self):
        import contextlib
        import io
        self.preguntar("¿hacéis uñas?")
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.assertEqual(aprender.main([]), 0)
        dicho = salida.getvalue()
        self.assertIn("uñas", dicho)
        self.assertIn("faq.md", dicho)


class TestLaFecha(unittest.TestCase):
    def test_hoy_por_defecto_no_revienta(self):
        entorno.aislar(self)
        self.assertEqual(aprender.faltas(), [])
        self.assertIsInstance(date.today(), date)


if __name__ == "__main__":
    unittest.main()
