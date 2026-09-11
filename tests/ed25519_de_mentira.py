"""Firmar con Ed25519, SOLO para las pruebas.

`firmas.py` solo verifica, que es lo unico que hace falta en produccion.
Para probar el webhook de Telnyx hace falta el otro lado: una clave y una
firma de verdad, no un `assert` contra una constante pegada a mano.

Esto NO es para usarlo en serio. Firma con una semilla fija, no protege
nada y no se molesta en ser constante en tiempo. Es un Telnyx de mentira
para que las pruebas puedan mandar una peticion bien firmada y otra mal.
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import firmas  # noqa: E402

L, P = firmas.L, firmas.P


def _comprimir(punto) -> bytes:
    x, y, z, _ = punto
    inverso = pow(z, P - 2, P)
    x, y = x * inverso % P, y * inverso % P
    return (y | (x & 1) << 255).to_bytes(32, "little")


def clave(semilla: bytes) -> tuple[bytes, bytes]:
    """(semilla de 32 bytes, clave publica de 32 bytes)."""
    semilla = hashlib.sha256(semilla).digest()          # 32 bytes hagas lo que hagas
    h = hashlib.sha512(semilla).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8                                 # clamp
    a |= 1 << 254
    return semilla, _comprimir(firmas._por(firmas._BASE, a))


def firmar(semilla: bytes, mensaje: bytes) -> bytes:
    h = hashlib.sha512(semilla).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    publica = _comprimir(firmas._por(firmas._BASE, a))
    r = int.from_bytes(hashlib.sha512(h[32:] + mensaje).digest(), "little") % L
    erre = _comprimir(firmas._por(firmas._BASE, r))
    k = int.from_bytes(hashlib.sha512(erre + publica + mensaje).digest(), "little") % L
    return erre + ((r + k * a) % L).to_bytes(32, "little")
