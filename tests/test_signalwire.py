"""Pruebas de SignalWire, el tercer proveedor.

SignalWire firma **igual que Twilio** —el mismo HMAC-SHA1 sobre la URL más
los campos ordenados— y solo cambia el nombre de la cabecera. Su propia
librería usa el validador de Twilio por dentro.

Eso hace que estas pruebas tengan un trabajo muy concreto: comprobar que la
compatibilidad es de verdad y no una suposición. Si algún día SignalWire
cambiara de esquema, esto se pone en rojo aquí y no en una llamada.

Y lo que de verdad no puede fallar: que la firma de un proveedor NO valga
para otro. Tres proveedores comparten la misma puerta, y confundirlos sería
aceptar como buena una petición que no lo es.
"""

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

from telefono import telefonia  # noqa: E402

CLAVE = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
URL = "https://maquina.tailnet.ts.net/telefono/entrada"
CAMPOS = {"CallSid": "CA1", "From": "+34600111222"}


def firmar(clave, url=URL, campos=None):
    """La firma tal como la calcula el proveedor: HMAC-SHA1 y base64."""
    import base64
    import hashlib
    import hmac
    campos = CAMPOS if campos is None else campos
    base = url + "".join(k + campos[k] for k in sorted(campos))
    return base64.b64encode(
        hmac.new(clave.encode(), base.encode(), hashlib.sha1).digest()).decode()


class TestLaFirmaEsLaDeTwilio(unittest.TestCase):
    def test_una_firma_buena_entra(self):
        self.assertTrue(telefonia.firma_valida(CLAVE, URL, CAMPOS, firmar(CLAVE)))

    def test_con_otra_clave_no(self):
        self.assertFalse(telefonia.firma_valida(CLAVE, URL, CAMPOS, firmar("otra")))

    def test_con_los_campos_cambiados_no(self):
        otros = {"CallSid": "CA1", "From": "+34600999999"}
        self.assertFalse(telefonia.firma_valida(CLAVE, URL, otros, firmar(CLAVE)))

    def test_con_otra_url_no(self):
        # La URL entra en la firma: un proxy que la reescriba la tira.
        self.assertFalse(telefonia.firma_valida(
            CLAVE, "https://otra/telefono/entrada", CAMPOS, firmar(CLAVE)))


class TestLaCabecera(unittest.TestCase):
    def test_se_reconoce_a_signalwire_por_su_cabecera(self):
        self.assertEqual(
            telefonia.quien_firma({telefonia.CABECERA_SIGNALWIRE: "x"}), "signalwire")

    def test_los_tres_proveedores_se_distinguen(self):
        for cabecera, quien in ((telefonia.CABECERA_TWILIO, "twilio"),
                                (telefonia.CABECERA_SIGNALWIRE, "signalwire"),
                                (telefonia.CABECERA_TELNYX, "telnyx")):
            with self.subTest(quien=quien):
                self.assertEqual(telefonia.quien_firma({cabecera: "x"}), quien)

    def test_sin_cabecera_no_es_de_nadie(self):
        self.assertEqual(telefonia.quien_firma({"Host": "algo.ts.net"}), "")


class TestLaConfiguracion(unittest.TestCase):
    def setUp(self):
        import os
        self.antes = {k: os.environ.get(k) for k in
                      ("GJALLARHORN_TELEFONO_TOKEN",
                       "GJALLARHORN_TELEFONO_CLAVE_SIGNALWIRE",
                       "GJALLARHORN_TELEFONO_CLAVE_PUBLICA")}
        for k in self.antes:
            os.environ.pop(k, None)
        self.addCleanup(self.restaurar)

    def restaurar(self):
        import os
        for k, v in self.antes.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def poner(self, **variables):
        import os
        for k, v in variables.items():
            os.environ[k] = v
        return telefonia.configuracion()

    def test_la_clave_de_signalwire_cae_en_el_token_si_no_se_pone_aparte(self):
        # Quien solo usa SignalWire pone su clave donde el token y funciona,
        # sin enterarse de que existe otra variable.
        config = self.poner(GJALLARHORN_TELEFONO_TOKEN=CLAVE)
        self.assertEqual(config["clave_signalwire"], CLAVE)

    def test_se_pueden_separar_para_tener_los_dos(self):
        config = self.poner(GJALLARHORN_TELEFONO_TOKEN="deltwilio1234567890abcdef12",
                            GJALLARHORN_TELEFONO_CLAVE_SIGNALWIRE=CLAVE)
        self.assertEqual(config["clave_signalwire"], CLAVE)
        self.assertNotEqual(config["token"], config["clave_signalwire"])
        self.assertEqual(sorted(telefonia.proveedores(config)),
                         ["signalwire", "twilio"])

    def test_con_una_sola_clave_no_se_anuncian_dos_proveedores(self):
        # Si la misma clave sirve para los dos, es una sola configuración: no
        # tiene sentido decir que hay dos proveedores puestos.
        config = self.poner(GJALLARHORN_TELEFONO_TOKEN=CLAVE)
        self.assertEqual(telefonia.proveedores(config), ["twilio"])

    def test_un_hueco_de_relleno_no_cuenta(self):
        config = self.poner(GJALLARHORN_TELEFONO_TOKEN="deltwilio1234567890abcdef12",
                            GJALLARHORN_TELEFONO_CLAVE_SIGNALWIRE="<tu Signing Key>")
        self.assertNotIn("signalwire", telefonia.proveedores(config))


if __name__ == "__main__":
    unittest.main()
