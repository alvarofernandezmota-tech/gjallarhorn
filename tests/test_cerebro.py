"""Pruebas de cerebro.py — el LLM entra solo donde las reglas no llegan.

Sin clave ni red: `preguntar` se sustituye por una función que devuelve lo
que se le diga. Lo que se prueba no es el modelo —eso es del modelo—, es que
lo que devuelva se atienda por el mismo camino que las reglas, y que **no
pueda colar ni un precio ni un servicio que no esté en la tabla**.
"""

import json
import os
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

import cerebro  # noqa: E402
import negocio as negocios  # noqa: E402
import recepcion  # noqa: E402


def modelo_que_dice(**campos):
    """Un `preguntar` de mentira: siempre contesta lo mismo."""
    base = {"intencion": "otro", "servicio": None, "cuando": None, "nombre": None}
    def preguntar(frase, servicios):
        return {**base, **campos}
    return preguntar


def modelo_roto(frase, servicios):
    raise ConnectionError("sin red")


class CasoCerebro(unittest.TestCase):
    def setUp(self):
        self.negocio = negocios.cargar("peluqueria")
        self.base = self.negocio.conocimiento

    def llamada(self, preguntar):
        return recepcion.Conversacion(self.base, preguntar=preguntar)


class TestEntender(CasoCerebro):
    def test_devuelve_lo_que_el_modelo_entendio(self):
        e = cerebro.entender("hacéis mechas?", self.base,
                             preguntar=modelo_que_dice(intencion="precio", servicio="Mechas"))
        self.assertEqual((e.intencion, e.servicio), ("precio", "Mechas"))

    def test_un_servicio_que_no_esta_en_la_tabla_se_descarta(self):
        # Diga lo que diga el modelo, un servicio fuera de la tabla no existe.
        e = cerebro.entender("alisado?", self.base,
                             preguntar=modelo_que_dice(intencion="precio", servicio="Alisado"))
        self.assertIsNone(e.servicio)

    def test_una_intencion_inventada_se_descarta_entera(self):
        self.assertIsNone(cerebro.entender("x", self.base,
                                           preguntar=modelo_que_dice(intencion="reembolso")))

    def test_si_falla_devuelve_none_y_no_revienta(self):
        self.assertIsNone(cerebro.entender("x", self.base, preguntar=modelo_roto))

    def test_sin_clave_no_hay_modelo(self):
        import os
        real = dict(os.environ)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(real)))
        import avisar
        leer = avisar._leer_env
        avisar._leer_env = lambda *a, **k: None
        self.addCleanup(setattr, avisar, "_leer_env", leer)
        self.assertFalse(cerebro.configurado())
        self.assertIsNone(cerebro.entender("x", self.base))

    def test_mide_cuanto_tarda(self):
        e = cerebro.entender("x", self.base, preguntar=modelo_que_dice(intencion="horario"))
        self.assertGreaterEqual(e.ms, 0)


class TestElEsquema(unittest.TestCase):
    def test_el_servicio_solo_puede_ser_de_la_tabla_o_nulo(self):
        esquema = cerebro._esquema(["Tinte", "Mechas"])
        self.assertEqual(esquema["properties"]["servicio"]["enum"], ["Tinte", "Mechas", None])
        self.assertFalse(esquema["additionalProperties"])
        self.assertEqual(set(esquema["required"]),
                         {"intencion", "servicio", "cuando", "nombre",
                          "franja", "confianza"})

    def test_las_instrucciones_llevan_la_lista_y_prohiben_inventar(self):
        texto = cerebro._instrucciones(["Tinte"])
        self.assertIn("- Tinte", texto)
        self.assertIn("Nunca inventes", texto)


class TestEnLaConversacion(CasoCerebro):
    def test_donde_las_reglas_no_llegan_entra_el_modelo(self):
        # «lo del color ese» no lleva ninguna palabra de precio: por reglas es
        # un recado. El modelo entiende que pregunta por el tinte.
        dicho = self.llamada(modelo_que_dice(intencion="precio", servicio="Tinte")) \
            .atender("oye, ¿hacéis lo del color ese?").texto
        self.assertIn("45", dicho)

    def test_las_reglas_van_primero_y_el_modelo_no_las_pisa(self):
        # Con «cuánto vale» las reglas entienden; el modelo ni se consulta.
        llamada = self.llamada(modelo_roto)
        self.assertIn("45", llamada.atender("¿cuánto vale un tinte?").texto)

    def test_el_modelo_no_puede_colar_un_precio(self):
        # Servicio fuera de la tabla → «no tengo ese servicio», nunca un número.
        dicho = self.llamada(modelo_que_dice(intencion="precio", servicio="Alisado")) \
            .atender("¿hacéis alisado?").texto
        self.assertIn("No tengo ese servicio", dicho)
        self.assertNotRegex(dicho, r"\d+ €")

    def test_una_cita_entendida_por_el_modelo_sigue_el_camino_normal(self):
        llamada = self.llamada(modelo_que_dice(
            intencion="cita", servicio="Tinte", cuando="el jueves a las cinco de la tarde"))
        dicho = llamada.atender("me gustaría pasarme el jueves a las cinco de la tarde a por un tinte").texto
        self.assertIn("nombre", dicho.lower())      # día y hora ya puestos: falta el nombre
        self.assertEqual(llamada.cita.servicio, "Tinte")
        self.assertEqual(llamada.cita.hora, "17:00")

    def test_si_el_modelo_falla_se_toma_nota_como_siempre(self):
        dicho = self.llamada(modelo_roto).atender("una cosa rara").texto
        self.assertIn("devolvemos la llamada", dicho)

    def test_la_despedida_entendida_por_el_modelo(self):
        dicho = self.llamada(modelo_que_dice(intencion="despedida")).atender("pues nada, hasta otra").texto
        self.assertIn("Hasta luego", dicho)


if __name__ == "__main__":
    unittest.main()


# ---- el cerebro entero: contexto, confianza, tope de gasto ----------------

def modelo_con_memoria(respuestas):
    """Un `preguntar` que apunta con qué se le ha llamado y va contestando."""
    vistas = []

    def preguntar(frase, servicios, turnos=None, sabido="", esperando=None):
        vistas.append({"frase": frase, "turnos": list(turnos or []),
                       "sabido": sabido, "esperando": esperando})
        return respuestas[min(len(vistas) - 1, len(respuestas) - 1)]

    preguntar.vistas = vistas
    return preguntar


def dice(**campos):
    base = {"intencion": "otro", "servicio": None, "cuando": None,
            "nombre": None, "franja": None, "confianza": "alta"}
    return {**base, **campos}


class TestLoQueVeElModelo(CasoCerebro):
    def test_le_llegan_los_turnos_de_la_llamada(self):
        preguntar = modelo_con_memoria([dice(intencion="otro")])
        llamada = self.llamada(preguntar)
        llamada.atender("¿cuánto vale el corte de caballero?")   # lo resuelven las reglas
        llamada.atender("frobnicar el bazinga")                  # y esto llega al modelo
        self.assertEqual(preguntar.vistas[0]["turnos"][0][0],
                         "¿cuánto vale el corte de caballero?")

    def test_le_llega_lo_que_se_le_acaba_de_preguntar(self):
        preguntar = modelo_con_memoria([dice(intencion="otro")])
        llamada = self.llamada(preguntar)
        llamada.atender("quiero cita")                 # → «¿qué día le viene bien?»
        llamada.atender("uy, pues no sé")
        self.assertIn("qué día", preguntar.vistas[0]["esperando"])

    def test_le_llega_lo_que_el_negocio_tiene_escrito(self):
        preguntar = modelo_con_memoria([dice(intencion="otro")])
        cerebro.entender("¿qué productos usáis para el pelo?", self.base, preguntar=preguntar)
        self.assertIn("tintes sin amoniaco", preguntar.vistas[0]["sabido"])

    def test_un_preguntar_de_los_de_antes_sigue_valiendo(self):
        # Firma vieja, (frase, servicios): se le llama como sabe.
        e = cerebro.entender("x", self.base,
                             preguntar=modelo_que_dice(intencion="horario"))
        self.assertEqual(e.intencion, "horario")


class TestLaConfianza(CasoCerebro):
    def test_con_confianza_baja_no_se_hace_nada(self):
        dicho = self.llamada(modelo_con_memoria([
            dice(intencion="cita", cuando="el jueves", confianza="baja")])
        ).atender("mmm no sé, algo el jueves quizá").texto
        self.assertIn("Tomo nota", dicho)

    def test_con_confianza_media_si(self):
        llamada = self.llamada(modelo_con_memoria([
            dice(intencion="cita", servicio="Tinte", confianza="media")]))
        self.assertIn("tinte", llamada.atender("lo del pelo ese").texto.lower())

    def test_una_confianza_inventada_se_toma_por_alta(self):
        e = cerebro.entender("x", self.base, preguntar=modelo_con_memoria([
            dice(intencion="horario", confianza="regulinchi")]))
        self.assertEqual(e.confianza, "alta")
        self.assertTrue(e.fiable)


class TestElTopeDeGasto(CasoCerebro):
    def test_no_se_consulta_mas_de_la_cuenta_en_una_llamada(self):
        preguntar = modelo_con_memoria([dice(intencion="otro")])
        llamada = self.llamada(preguntar)
        for _ in range(cerebro.TOPE_CONSULTAS + 5):
            llamada.atender("frobnicar el bazinga")
        self.assertEqual(len(preguntar.vistas), cerebro.TOPE_CONSULTAS)

    def test_y_la_llamada_sigue_contestando(self):
        llamada = self.llamada(modelo_con_memoria([dice(intencion="otro")]))
        for _ in range(cerebro.TOPE_CONSULTAS + 2):
            llamada.atender("frobnicar el bazinga")
        self.assertIn("recado", llamada.atender("frobnicar el bazinga").texto.lower())


class TestLasIntencionesNuevas(CasoCerebro):
    def setUp(self):
        super().setUp()
        import tempfile
        from datetime import datetime
        from zoneinfo import ZoneInfo

        import agenda as ag
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.agenda = ag.Agenda("peluqueria", self.negocio.horario,
                                ruta=Path(self._tmp.name) / "agenda.json",
                                ahora=datetime(2026, 9, 11, 10, 0, tzinfo=ZoneInfo("Europe/Madrid")))
        self.agenda.reservar("2026-09-17", "17:00", 90, "Tinte", "Marta")

    def conversacion(self, preguntar):
        llamada = recepcion.Conversacion(self.base, agenda=self.agenda, preguntar=preguntar)
        llamada.nombre = "Marta"
        return llamada

    def test_anular_entendido_por_el_modelo(self):
        dicho = self.conversacion(modelo_con_memoria([dice(intencion="anular")])) \
            .atender("mira, al final me va fatal el jueves").texto
        self.assertIn("anulo", dicho.lower())
        self.assertEqual(self.agenda.citas(), [])

    def test_cambiar_entendido_por_el_modelo(self):
        dicho = self.conversacion(modelo_con_memoria([dice(intencion="cambiar")])) \
            .atender("¿lo podemos dejar para otro momento?").texto
        self.assertIn("anulo", dicho.lower())
        self.assertIn("nueva", dicho.lower())

    def test_la_franja_que_entiende_el_modelo_se_usa(self):
        llamada = self.conversacion(modelo_con_memoria([
            dice(intencion="cita", servicio="Tinte", cuando="el viernes", franja="tarde")]))
        dicho = llamada.atender("a ver si me podéis meter el viernes después de comer").texto
        self.assertIn("por la tarde", dicho)


class TestSiFallaQuedaConstancia(CasoCerebro):
    def test_un_fallo_del_modelo_deja_aviso(self):
        import avisos
        entorno.aislar(self)
        self.assertIsNone(cerebro.entender("x", self.base, preguntar=modelo_roto))
        registrados = avisos.listar()
        self.assertEqual(len(registrados), 1)
        self.assertEqual(registrados[0]["tipo"], "fallo")
        self.assertIn("no contestó", registrados[0]["texto"])


class TestElMotor(unittest.TestCase):
    """Con qué modelo se cuenta: Claude, uno local, o ninguno."""

    def setUp(self):
        self.antes = {k: os.environ.get(k) for k in
                      ("GJALLARHORN_LLM", "ANTHROPIC_API_KEY", "GJALLARHORN_LLM_MODELO")}
        self.addCleanup(self.devolver)
        for clave in self.antes:
            os.environ.pop(clave, None)

    def devolver(self):
        for clave, valor in self.antes.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor

    def test_sin_nada_no_hay_modelo(self):
        self.assertEqual(cerebro.proveedor(), "")
        self.assertFalse(cerebro.configurado())

    def test_con_clave_y_sin_elegir_es_claude(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-de-mentira"
        self.assertEqual(cerebro.proveedor(), "anthropic")
        self.assertEqual(cerebro.modelo(), cerebro.MODELO_POR_DEFECTO)

    def test_ollama_no_necesita_clave(self):
        os.environ["GJALLARHORN_LLM"] = "ollama"
        self.assertEqual(cerebro.proveedor(), "ollama")
        self.assertTrue(cerebro.configurado())
        self.assertEqual(cerebro.modelo(), cerebro.MODELO_LOCAL_POR_DEFECTO)

    def test_se_puede_apagar_teniendo_clave(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-de-mentira"
        os.environ["GJALLARHORN_LLM"] = "no"
        self.assertFalse(cerebro.configurado())

    def test_elegir_claude_sin_clave_no_enciende_nada(self):
        os.environ["GJALLARHORN_LLM"] = "anthropic"
        self.assertEqual(cerebro.proveedor(), "")

    def test_el_modelo_se_puede_fijar(self):
        os.environ["GJALLARHORN_LLM"] = "ollama"
        os.environ["GJALLARHORN_LLM_MODELO"] = "gemma3:4b"
        self.assertEqual(cerebro.modelo(), "gemma3:4b")


class TestElModeloLocal(CasoCerebro):
    """Ollama: por HTTP a esta misma máquina, con el mismo esquema."""

    def responder_con(self, contestado):
        """Sustituye urlopen por uno que devuelve lo que se le diga."""
        import io
        import urllib.request
        pedido = {}

        class Respuesta(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *_): return False

        def urlopen(peticion, timeout=None):
            pedido["url"] = peticion.full_url
            pedido["cuerpo"] = json.loads(peticion.data.decode("utf-8"))
            pedido["timeout"] = timeout
            return Respuesta(json.dumps(contestado).encode("utf-8"))

        antes = urllib.request.urlopen
        urllib.request.urlopen = urlopen
        self.addCleanup(lambda: setattr(urllib.request, "urlopen", antes))
        return pedido

    def test_le_manda_el_esquema_y_los_turnos(self):
        pedido = self.responder_con({"message": {"content": json.dumps(
            dice(intencion="precio", servicio="Tinte"))}})
        entendido = cerebro._preguntar_ollama(
            "lo del color", ["Tinte"], turnos=[("hola", "Dígame")], sabido="lo escrito")
        self.assertEqual(entendido["servicio"], "Tinte")
        self.assertIn("/api/chat", pedido["url"])
        self.assertEqual(pedido["cuerpo"]["format"]["properties"]["servicio"]["enum"],
                         ["Tinte", None])
        self.assertEqual(pedido["cuerpo"]["options"]["temperature"], 0)
        self.assertFalse(pedido["cuerpo"]["stream"])
        papeles = [m["role"] for m in pedido["cuerpo"]["messages"]]
        self.assertEqual(papeles, ["system", "user", "assistant", "user"])
        self.assertIn("lo escrito", pedido["cuerpo"]["messages"][0]["content"])

    def test_no_espera_mas_de_la_cuenta(self):
        pedido = self.responder_con({"message": {"content": json.dumps(dice())}})
        cerebro._preguntar_ollama("x", ["Tinte"])
        self.assertEqual(pedido["timeout"], cerebro.TOPE_SEGUNDOS)

    def test_si_ollama_no_esta_la_llamada_sigue(self):
        import urllib.error
        import urllib.request

        def urlopen(peticion, timeout=None):
            raise urllib.error.URLError("conexión rechazada")

        antes = urllib.request.urlopen
        urllib.request.urlopen = urlopen
        self.addCleanup(lambda: setattr(urllib.request, "urlopen", antes))
        entorno.aislar(self)
        self.assertIsNone(cerebro.entender("x", self.base, preguntar=cerebro._preguntar_ollama))
