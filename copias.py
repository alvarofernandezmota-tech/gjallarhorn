"""Copias de lo que no se puede perder: las citas, los clientes y los avisos.

Lo peor que puede pasar aquí no es que el bot conteste mal: es que un día
el fichero de citas no esté. Un disco que se llena a mitad de una escritura,
un `rm` con la mano torcida, un despliegue que borra la carpeta. `almacen.py`
protege de la escritura a medias —escribe y renombra—, pero no del borrado ni
del error humano.

Así que una copia al día, en la misma carpeta del negocio:

    datos/<negocio>/copias/2026-09-11/agenda.json …

Sin comprimir y en JSON, a propósito: una copia que hay que descomprimir con
una herramienta concreta es una copia que el día malo no sabes abrir. Estos
ficheros pesan kilobytes y se leen con cualquier cosa, incluso a mano.

## Restaurar no borra lo que hay

`restaurar()` copia **primero** lo que hay ahora mismo a una copia aparte y
luego pone la del día que se pida. Restaurar la copia equivocada y quedarse
sin las dos versiones es un error que se comete una vez en la vida, y aquí
no se puede cometer.

## Esto no sustituye a una copia fuera de la máquina

Si arde la máquina, arden las copias. Para eso está `GJALLARHORN_DATOS`
apuntando a una carpeta que ya sincronices, o un `rsync` en un cron. Lo que
esto cubre es el 90 % de los sustos: el borrado, el error humano y el «ayer
esto estaba bien».
"""

import shutil
from datetime import date
from pathlib import Path

import datos

# Qué se copia. Lo que no está aquí se puede volver a generar; esto no.
FICHEROS = ("agenda.json", "clientes.json", "avisos.json")

# Cuántas copias se guardan. Dos semanas es lo que tarda alguien en darse
# cuenta de que algo se borró, y son unos pocos kilobytes.
CUANTAS = 14

CARPETA = "copias"


def carpeta(negocio: str | None = None) -> Path:
    """Dónde van las copias de este bot."""
    base = datos.carpeta_de(negocio) if negocio else datos.carpeta()
    return base / CARPETA


def listar(negocio: str | None = None) -> list[str]:
    """Las fechas de las copias que hay, de la más vieja a la más nueva."""
    raiz = carpeta(negocio)
    if not raiz.is_dir():
        return []
    return sorted(p.name for p in raiz.iterdir() if p.is_dir())


def hacer(negocio: str | None = None, hoy: date | None = None) -> tuple[Path, list[str]]:
    """La copia de hoy. Devuelve (dónde, qué ficheros se han copiado).

    Repetirla el mismo día sobrescribe la de hoy: la copia es «cómo estaba
    esto hoy», no un registro de cada cambio.
    """
    origen = datos.carpeta_de(negocio) if negocio else datos.carpeta()
    destino = carpeta(negocio) / (hoy or date.today()).isoformat()
    destino.mkdir(parents=True, exist_ok=True)
    copiados = []
    for nombre in FICHEROS:
        fichero = origen / nombre
        if fichero.is_file():
            shutil.copy2(fichero, destino / nombre)
            copiados.append(nombre)
    return destino, copiados


def limpiar(negocio: str | None = None, cuantas: int = CUANTAS) -> list[str]:
    """Deja las `cuantas` copias más nuevas. Devuelve las que ha borrado."""
    fechas = listar(negocio)
    sobran = fechas[:-cuantas] if cuantas > 0 else fechas
    for fecha in sobran:
        shutil.rmtree(carpeta(negocio) / fecha, ignore_errors=True)
    return sobran


def restaurar(fecha: str, negocio: str | None = None,
              hoy: date | None = None) -> list[str]:
    """Pone la copia de ese día. Antes guarda lo que hay ahora.

    Devuelve qué ficheros ha puesto. Levanta si esa copia no existe: poner
    «nada» encima de los datos de verdad no es restaurar, es borrar.
    """
    origen = carpeta(negocio) / fecha
    if not origen.is_dir():
        raise FileNotFoundError(
            f"no hay copia del {fecha}. Hay: {', '.join(listar(negocio)) or 'ninguna'}")

    destino = datos.carpeta_de(negocio) if negocio else datos.carpeta()
    # Lo de ahora se guarda aparte ANTES de tocar nada.
    antes = carpeta(negocio) / f"antes-de-restaurar-{(hoy or date.today()).isoformat()}"
    antes.mkdir(parents=True, exist_ok=True)
    for nombre in FICHEROS:
        actual = destino / nombre
        if actual.is_file():
            shutil.copy2(actual, antes / nombre)

    puestos = []
    for nombre in FICHEROS:
        copia = origen / nombre
        if copia.is_file():
            shutil.copy2(copia, destino / nombre)
            puestos.append(nombre)
    return puestos


def main(argumentos: list[str] | None = None) -> int:
    """`python3 copias.py`: hace la copia de hoy y tira las viejas."""
    import argparse

    import negocio as negocios

    parser = argparse.ArgumentParser(description="Copias de las citas y los clientes")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--listar", action="store_true", help="qué copias hay")
    parser.add_argument("--restaurar", metavar="FECHA",
                        help="poner la copia de ese día (AAAA-MM-DD)")
    args = parser.parse_args(argumentos)

    try:
        negocio = negocios.cargar(args.negocio)
    except (FileNotFoundError, ValueError) as error:
        print(f"❌ {error}")
        return 1
    datos.usar(negocio)

    if args.listar:
        fechas = listar()
        print(f"{len(fechas)} copia(s) en {carpeta()}:")
        for fecha in fechas:
            cuantos = len(list((carpeta() / fecha).glob("*.json")))
            print(f"   {fecha}  ({cuantos} fichero(s))")
        return 0

    if args.restaurar:
        try:
            puestos = restaurar(args.restaurar)
        except FileNotFoundError as error:
            print(f"❌ {error}")
            return 1
        print(f"✅ puesta la copia del {args.restaurar}: {', '.join(puestos)}")
        print(f"   Lo que había se ha guardado en {carpeta()}/antes-de-restaurar-…")
        print("   Reinicia el servicio para que la lea: make reiniciar")
        return 0

    destino, copiados = hacer()
    borradas = limpiar()
    if not copiados:
        print("No hay nada que copiar todavía: este negocio no tiene datos.")
        return 0
    print(f"✅ copia en {destino}: {', '.join(copiados)}")
    if borradas:
        print(f"   ({len(borradas)} copia(s) vieja(s) borrada(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
