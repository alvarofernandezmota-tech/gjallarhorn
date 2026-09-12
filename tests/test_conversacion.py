"""Pruebas de `Conversacion` — la llamada entera, no la frase suelta.

Un recepcionista que no recuerda es un contestador. Todo lo que hay aquí
comprueba la diferencia: que el servicio dicho en el primer turno siga vivo en
el cuarto, y que «a las cinco» —que por sí sola no es nada— sea una cita
cuando el día se dijo dos frases antes.

Y dos reglas que no se relajan por estar en mitad de una conversación:

1. **Un precio sale de la tabla o no sale.**
2. **Una hora sin acotar se pregunta**, aunque llevemos cinco turnos y quede
   feo insistir. Citar a alguien a las 05:00 queda peor.
"""

import sys
import unittest
from pathlib import Path

# La raiz del repo **es** el paquete `hugin`, asi que lo que tiene que
# estar en el sys.path es la carpeta que lo contiene.
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ.parent))

import entorno  # noqa: E402,F401

from hugin.guardado import avisos  # noqa: E402
from hugin.negocio import negocio as negocios  # noqa: E402
from hugin.mente import recepcion  # noqa: E402


class CasoLlamada(unittest.TestCase):
    def setUp(self):
        self.negocio = negocios.cargar("peluqueria")
        self.llamada = recepcion.Conversacion(self.negocio.conocimiento)

    def decir(self, *frases):
        """Dice varias cosas seguidas y devuelve la última contestación."""
        respuesta = None
        for frase in frases:
            respuesta = self.llamada.atender(frase)
        return respuesta.texto

    def guion(self, *frases):
        return [self.llamada.atender(f).texto for f in frases]


class TestRecuerdaElServicio(CasoLlamada):
    def test_lo_dicho_en_el_primer_turno_sigue_vivo_en_el_tercero(self):
        dicho = self.decir("¿cuánto vale un tinte?", "el tinte", "pues quiero cita")
        self.assertIn("tinte", dicho.lower(),
                      "se le ha olvidado de qué era la cita")

    def test_sin_memoria_no_sabria_de_que_es_la_cita(self):
        # El contraste: `atender` suelta, sin conversación, no puede saberlo.
        suelta = recepcion.atender("pues quiero cita", self.negocio.conocimiento)
        self.assertNotIn("tinte", suelta.texto.lower())

    def test_elegir_entre_varias_opciones_da_el_precio_de_esa(self):
        primera = self.decir("¿cuánto vale un tinte?")
        self.assertIn("¿Cuál le interesa?", primera)
        self.assertIn("45", self.decir("el tinte"))


class TestLaCitaSeConstruyeATrozos(CasoLlamada):
    def test_dia_y_hora_llegan_en_turnos_distintos(self):
        guion = self.guion("quiero cita", "un tinte", "el jueves", "a las cinco",
                           "sí", "Álvaro")
        self.assertIn("qué servicio", guion[0].lower())   # sin saberlo, la duración falla
        self.assertIn("qué día", guion[1].lower())
        self.assertIn("hora", guion[2].lower())
        self.assertIn("de la tarde", guion[3])            # repregunta la franja
        self.assertIn("nombre", guion[4].lower())
        self.assertIn("Álvaro", guion[5])

    def test_una_hora_suelta_sin_dia_previo_no_es_una_cita(self):
        # Sin nadie que recuerde el día, «a las cinco» sigue sin serlo.
        self.assertIn("devolvemos la llamada", self.decir("a las cinco"))

    def test_todo_de_una_vez_tambien_vale(self):
        dicho = self.decir("quiero cita para un tinte el jueves a las 17:30")
        self.assertIn("nombre", dicho.lower())       # solo le falta eso

    def test_el_nombre_se_coge_aunque_llegue_antes_de_tiempo(self):
        guion = self.guion("me llamo Álvaro", "quiero cita de tinte el viernes a las 17:00")
        self.assertIn("Álvaro", guion[1])


class TestLaHoraAmbiguaSePreguntaSiempre(CasoLlamada):
    def test_decir_que_si_la_lleva_a_la_tarde(self):
        self.decir("quiero cita", "el jueves", "a las cinco")
        self.assertIn("cinco de la tarde", self.decir("sí", "Álvaro"))

    def test_decir_que_no_vuelve_a_preguntar_la_hora(self):
        # No se apunta a las 05:00 «porque lo ha dicho». Se pregunta otra vez.
        self.decir("quiero cita", "el jueves", "a las cinco")
        dicho = self.decir("no")
        self.assertIn("a qué hora", dicho.lower())

    def test_una_hora_ya_acotada_no_se_repregunta(self):
        dicho = self.decir("quiero cita", "el jueves", "a las cinco de la tarde")
        self.assertIn("nombre", dicho.lower())

    def test_una_hora_de_tarde_en_reloj_de_24_tampoco(self):
        dicho = self.decir("quiero cita", "el jueves", "a las 17:00")
        self.assertIn("nombre", dicho.lower())


class TestLoQueSeDiceSuenaAPersona(CasoLlamada):
    """Esto se escucha, no se lee. Una fecha ISO por teléfono no se entiende."""

    def test_no_canta_la_fecha_en_iso(self):
        dicho = self.decir("quiero cita", "el jueves", "a las cinco de la tarde",
                           "Álvaro")
        self.assertNotIn("-", dicho, f"está diciendo una fecha de ordenador: {dicho}")
        self.assertIn("jueves", dicho)

    def test_no_canta_la_hora_en_reloj_digital(self):
        dicho = self.decir("quiero cita", "el jueves", "a las cinco de la tarde",
                           "Álvaro")
        self.assertNotIn("17:00", dicho)
        self.assertIn("cinco de la tarde", dicho)


class TestLasReglasNoSeRelajan(CasoLlamada):
    def test_un_servicio_que_no_esta_sigue_sin_tener_precio(self):
        dicho = self.decir("¿cuánto vale un tinte?", "¿y cambiar el parabrisas?")
        self.assertIn("No tengo ese servicio", dicho)

    def test_una_frase_larga_encuentra_el_servicio_igual(self):
        # Por teléfono nadie dice «tinte» a secas. Si esto falla, el agente
        # contesta «no lo tengo» teniéndolo en la tabla.
        self.assertIn("45", self.decir("buenas, quería saber cuánto vale un tinte"))

    def test_el_horario_sale_de_la_faq_tal_cual(self):
        self.assertIn("Lunes cerrado", self.decir("¿qué horario tenéis?"))


class TestColgar(CasoLlamada):
    def ultimo_aviso(self):
        return avisos.ultimos(1, ruta=None)[0] if hasattr(avisos, "ultimos") else None

    def test_una_cita_cerrada_se_apunta_con_la_fecha_de_ordenador(self):
        self.decir("quiero cita para un tinte", "el jueves",
                   "a las cinco de la tarde", "Álvaro")
        apuntado = self.llamada.colgar()
        self.assertIn("tinte", apuntado)
        self.assertIn("Álvaro", apuntado)
        self.assertRegex(apuntado, r"\d{4}-\d{2}-\d{2}")   # esto lo lee el dueño

    def test_una_llamada_cortada_a_medias_tambien_se_apunta(self):
        # Perder el rastro de quien llamó es lo peor que puede pasar aquí.
        self.decir("quiero cita para un tinte", "el jueves")
        apuntado = self.llamada.colgar()
        self.assertIn("a medias", apuntado)
        self.assertIn("Falta: hora", apuntado)

    def test_sin_cita_no_se_apunta_nada(self):
        self.decir("¿qué horario tenéis?")
        self.assertIsNone(self.llamada.colgar())

    def test_despues_de_colgar_se_empieza_de_cero(self):
        self.decir("quiero cita para un tinte", "el jueves")
        self.llamada.colgar()
        # La cita vieja no puede reaparecer en la llamada siguiente.
        self.assertIn("devolvemos la llamada", self.decir("a las cinco"))


if __name__ == "__main__":
    unittest.main()


class TestElegirEntreLoOfrecido(CasoLlamada):
    """«El de caballero» tras «¿cuál le interesa?» elige por lo que distingue."""

    def test_la_palabra_que_distingue_basta(self):
        self.decir("¿cuánto vale un corte?")
        self.assertIn("14 €", self.decir("el de caballero"))

    def test_la_palabra_comun_a_todos_no_elige(self):
        # «corte» está en las tres opciones: no dice cuál.
        self.decir("¿cuánto vale un corte?")
        self.assertNotIn("14 €", self.decir("el corte"))

    def test_fuera_de_ese_momento_no_se_adivina(self):
        # Sin haber ofrecido nada, «el de caballero» no es una pregunta de precio.
        self.assertNotIn("14 €", self.decir("el de caballero"))

    def test_elegir_deja_el_servicio_recordado_para_la_cita(self):
        self.decir("¿cuánto vale un corte?", "el de caballero")
        self.assertIn("caballero", self.decir("pues quiero cita").lower())
