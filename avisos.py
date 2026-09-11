"""Lo que pasa en las llamadas, guardado y ordenado para leerlo de un vistazo.

Un agente que atiende el teléfono y no deja rastro es inservible: no sabes si
ha cogido tres llamadas o treinta, ni qué dijo, ni qué citó. Esto es ese
rastro.

Guarda cuatro cosas:

    llamada   entró una llamada, y de qué fue
    cita      se cerró una cita: con quién y cuándo
    tarifa    preguntaron un precio, y cuál se dio
    fallo     algo salió mal: el modelo no contestó, la cita chocaba…

## Por qué esto no va en una agenda personal

Porque estas llamadas **no son tuyas**. La reserva de un cliente en tu agenda
mezcla tu vida con la de un negocio en el mismo fichero, y el día que dejes el
negocio hay que separarlas a mano. Los avisos viven aquí, con el negocio.

## Dónde se guardan

En `GJALLARHORN_DATOS` si está puesta; si no, en `datos/` dentro del repo —que
está en el `.gitignore`, porque esto son datos, no código—. La ruta se
configura; no se clava en el código.

El fichero se escribe con `almacen.py`, que es de aquí: versión de esquema y
escritura atómica. gjallarhorn no depende de ningún otro repo.
"""

import os
import threading
from pathlib import Path

import almacen
import fechas

VARIABLE = "GJALLARHORN_DATOS"
VERSION = 1

# Dos llamadas a la vez registran avisos a la vez, y el id sale de mirar el
# maximo de los que hay: sin esto se repiten ids y se pisa una escritura.
_ESCRIBIENDO = threading.Lock()

TIPOS = {
    "llamada": "📞",
    "cita": "📅",
    "tarifa": "💶",
    "fallo": "⚠️",
}

# Telegram corta en 4096. Se deja margen para la cabecera y el aviso de recorte.
TOPE_TELEGRAM = 3800


def raiz() -> Path:
    valor = os.environ.get(VARIABLE, "").strip()
    return Path(valor).expanduser().resolve() if valor else Path(__file__).resolve().parent / "datos"


def _ruta(ruta: Path | None = None) -> Path:
    return ruta if ruta is not None else raiz() / "avisos.json"


def cargar(ruta: Path | None = None) -> list[dict]:
    return almacen.cargar(_ruta(ruta), VERSION, vacio=[])


def guardar(avisos: list[dict], ruta: Path | None = None) -> None:
    destino = _ruta(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    almacen.guardar(destino, avisos, VERSION)


def registrar(tipo: str, texto: str, datos: dict | None = None,
              ruta: Path | None = None, ahora=None) -> dict:
    """Apunta un aviso. Solo añade: nunca pisa ni reordena lo que ya hay.

    La hora es la de Madrid, como todo el ecosistema: el `ahora` del sistema y
    el «ayer» del diario tienen que ser el mismo reloj.
    """
    if tipo not in TIPOS:
        raise ValueError(f"tipo desconocido: {tipo!r} (hay {', '.join(TIPOS)})")
    if not texto.strip():
        raise ValueError("un aviso sin texto no sirve de nada")
    momento = ahora or fechas.ahora()
    with _ESCRIBIENDO:
        return _apuntar(tipo, texto, datos, ruta, momento)


def _apuntar(tipo, texto, datos, ruta, momento) -> dict:
    avisos = cargar(ruta)
    aviso = {
        "id": max((a["id"] for a in avisos), default=0) + 1,
        "tipo": tipo,
        "texto": texto.strip(),
        "fecha": momento.strftime("%Y-%m-%d"),
        "hora": momento.strftime("%H:%M"),
        "visto": False,
        **({"datos": datos} if datos else {}),
    }
    avisos.append(aviso)
    guardar(avisos, ruta)
    return aviso


def listar(tipo: str | None = None, solo_nuevos: bool = False,
           limite: int | None = None, ruta: Path | None = None) -> list[dict]:
    """Los avisos, **del más reciente al más antiguo**.

    Ese orden y no otro: lo que acaba de pasar es lo que quieres ver primero
    cuando abres el móvil.
    """
    avisos = cargar(ruta)
    if tipo:
        avisos = [a for a in avisos if a["tipo"] == tipo]
    if solo_nuevos:
        avisos = [a for a in avisos if not a.get("visto")]
    avisos.sort(key=lambda a: (a["fecha"], a["hora"], a["id"]), reverse=True)
    return avisos[:limite] if limite else avisos


def marcar_vistos(ids: list[int] | None = None, ruta: Path | None = None) -> int:
    """Marca avisos como vistos. Sin `ids`, todos. Devuelve cuántos cambió."""
    avisos = cargar(ruta)
    cambiados = 0
    for aviso in avisos:
        if (ids is None or aviso["id"] in ids) and not aviso.get("visto"):
            aviso["visto"] = True
            cambiados += 1
    if cambiados:
        guardar(avisos, ruta)
    return cambiados


def _linea(aviso: dict) -> str:
    marca = "" if aviso.get("visto") else "🔵 "
    return f"{marca}{TIPOS[aviso['tipo']]} {aviso['hora']}  {aviso['texto']}"


AVISO_RECORTE = "\n\n… hay más. Se mandan en el siguiente mensaje."


def encajar(avisos: list[dict], tope: int = TOPE_TELEGRAM) -> list[dict]:
    """Los avisos que caben enteros en un mensaje de `tope` caracteres.

    Se cuenta **aviso a aviso**, no bloque a bloque. Antes se descartaba el
    bloque de un día entero si no cabía, así que un día con muchas llamadas se
    mandaba vacío —y `avisar.py` los marcaba como vistos igual—. Medido: con
    400 avisos del mismo día no cabía **ninguno**, se decía haber mandado 400,
    y los 400 desaparecían para siempre. Perder el rastro de una llamada es lo
    peor que puede pasar aquí, y estaba pasando en silencio.

    Siempre devuelve al menos uno: un aviso larguísimo se recorta al leerlo,
    pero no puede bloquear la cola detrás de él.
    """
    cabidos, usados, dia = [], 40, None
    for aviso in avisos:
        coste = len(_linea(aviso)) + 1
        if aviso["fecha"] != dia:
            coste += len(aviso["fecha"]) + 4
        if cabidos and usados + coste > tope:
            break
        cabidos.append(aviso)
        usados += coste
        dia = aviso["fecha"]
    return cabidos


def formato(avisos: list[dict], tope: int = TOPE_TELEGRAM) -> str:
    """Los avisos como se leen en el chat: agrupados por día, el de hoy arriba.

    Recorta si no cabe —lo viejo es lo que sobra— y **lo dice**. Un resumen
    recortado en silencio hace creer que no hubo más llamadas.
    """
    if not avisos:
        return "Sin avisos."

    cabidos = encajar(avisos, tope - len(AVISO_RECORTE))
    nuevos = sum(1 for a in avisos if not a.get("visto"))
    cabecera = f"{len(avisos)} aviso(s)" + (f", {nuevos} sin ver" if nuevos else "")

    partes, dia_actual = [], None
    for aviso in cabidos:
        if aviso["fecha"] != dia_actual:
            dia_actual = aviso["fecha"]
            partes.append(f"\n*{dia_actual}*")
        partes.append(_linea(aviso))

    texto = cabecera + "".join(
        p if p.startswith("\n") else f"\n{p}" for p in partes)
    if len(cabidos) < len(avisos):
        texto += AVISO_RECORTE
    return texto


def main() -> int:
    """`python3 avisos.py` — los avisos, ordenados, como se verían en el chat."""
    import argparse

    parser = argparse.ArgumentParser(description="Los avisos de las llamadas")
    parser.add_argument("--nuevos", action="store_true", help="solo los que no has visto")
    parser.add_argument("--tipo", choices=sorted(TIPOS), help="filtrar por tipo")
    parser.add_argument("--limite", type=int, help="cuántos como mucho")
    parser.add_argument("--marcar-vistos", action="store_true",
                        help="darlos por leídos DESPUÉS de enseñarlos")
    args = parser.parse_args()

    lista = listar(tipo=args.tipo, solo_nuevos=args.nuevos, limite=args.limite)
    print(formato(lista))
    if args.marcar_vistos and lista:
        # Después de imprimir, nunca antes: si falla la impresión, no se han
        # visto.
        print(f"\n({marcar_vistos([a['id'] for a in lista])} marcados como vistos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
