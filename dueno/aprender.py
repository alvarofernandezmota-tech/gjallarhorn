"""Lo que el agente no supo contestar, agrupado, para que el dueño lo escriba.

Un recepcionista nuevo pregunta: «oye, me han llamado tres veces preguntando
por las uñas, ¿eso lo hacemos?». Este es ese momento, y es lo que convierte
el bot en algo que **mejora solo**: no aprendiendo por su cuenta —eso sería
inventarse respuestas—, sino diciéndole a quien sabe qué le falta por
escribir.

De dónde sale: cada vez que el agente se queda sin saber algo deja el aviso
con `datos={"falta": …, "frase": …}`. Aquí se leen esos avisos, se agrupan
las frases que preguntan lo mismo y se ordenan por cuántas veces han
preguntado. Sin modelo y sin adivinar nada: contar y agrupar.

## Se agrupa por la palabra que más se repite, y por qué

«¿Hacéis uñas?», «¿y las uñas de gel?» y «quería preguntar por las uñas» son
la misma pregunta, y lo único que comparten es «uñas». Agrupar por el
conjunto entero de palabras las separaba en tres líneas iguales.

Así que primero se cuenta qué palabras aparecen en lo que queda sin
contestar, y cada frase va al grupo de **su palabra más repetida**. Lo que
más preguntan es lo que da nombre al grupo, que es justo lo que el dueño
quiere ver arriba del todo. Las palabras van sin plural y con los sinónimos
del negocio aplicados, como en el buscador: «masaje» y «masajes» son lo
mismo.

Es tosco y se nota: «¿tenéis parking?» y «¿hay dónde aparcar?» caen en dos
grupos porque no comparten palabra. Prefiero eso a juntar cosas que no van
juntas: dos líneas se leen en un segundo, y un grupo mal hecho manda al
dueño a escribir una respuesta que no le han preguntado.

## Qué NO hace esto

No escribe en `tarifas.md` ni en `faq.md`. Lo que sabe el negocio lo escribe
el negocio: ese es el trato desde el principio, y es lo que impide que el
agente acabe contestando algo que nadie ha dicho nunca.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import re

from hugin.guardado import avisos
from hugin.guardado import datos
from hugin.mente import conocimiento

# Cuánto se mira hacia atrás. Un mes: lo de hace medio año o ya lo escribió
# o ya no le interesa.
DIAS = 30

# Cuántos ejemplos se guardan de cada grupo. Con dos se entiende la pregunta;
# con diez, la lista deja de leerse.
EJEMPLOS = 3

# Qué le faltaba al agente, y dónde se arregla eso.
DONDE = {
    "tarifa": "tarifas.md",
    "respuesta": "faq.md",
    "tarifas": "tarifas.md",
    "horario": "faq.md",
}

COMO_SE_DICE = {
    "tarifa": "preguntaron por un servicio que no está en la tabla de precios",
    "respuesta": "preguntaron algo que no está escrito en ningún sitio",
    "tarifas": "preguntaron precios y no había tabla cargada",
    "horario": "preguntaron el horario y no está en la FAQ",
    "persona": "pidieron hablar con una persona",
}


@dataclass
class Falta:
    """Una cosa que el agente no supo, y cuántas veces se la han preguntado."""

    que: str                                  # tarifa | respuesta | persona…
    palabras: tuple[str, ...]                 # lo que comparten las frases
    veces: int = 0
    ejemplos: list[str] = field(default_factory=list)
    ultima: str = ""                          # fecha del último caso

    @property
    def donde(self) -> str:
        """En qué fichero se arregla. Vacío si no se arregla escribiendo."""
        return DONDE.get(self.que, "")

    @property
    def titulo(self) -> str:
        return " ".join(self.palabras) or "(sin palabras claras)"

    @property
    def ejemplo(self) -> str:
        """El ejemplo que mejor se lee: el más corto, que es el más directo."""
        return min(self.ejemplos, key=len) if self.ejemplos else self.titulo

    def dicho(self) -> str:
        """Una línea para el dueño: qué le preguntan y dónde se contesta."""
        veces = "1 vez" if self.veces == 1 else f"{self.veces} veces"
        donde = f" → {self.donde}" if self.donde else ""
        return f"«{self.ejemplo}» ({veces}){donde}"

    def como_dict(self) -> dict:
        return {"que": self.que, "titulo": self.titulo, "veces": self.veces,
                "ejemplo": self.ejemplo, "ejemplos": self.ejemplos,
                "donde": self.donde, "ultima": self.ultima,
                "dicho": COMO_SE_DICE.get(self.que, self.que)}


def _palabras(frase: str, base: Path | None) -> set[str]:
    """Las palabras con contenido, sin plural y con los sinónimos del negocio.

    Las mismas que usa el buscador: si «uñas» y «uña» fueran dos palabras
    distintas, la mitad de los grupos saldrían partidos por una ese.
    """
    from hugin.mente import rag

    return set(rag._tokens(frase, base))


def _como_se_dicen(frase: str) -> dict[str, str]:
    """De la raíz con la que se compara a la palabra tal cual la dijeron.

    La raíz («masaj») sirve para agrupar y no se le enseña a nadie; en la
    pantalla del dueño tiene que poner «masajes», que es lo que le han
    preguntado.
    """
    from hugin.mente import rag

    dichas = {}
    for palabra in re.findall(r"\w+", frase):
        dichas.setdefault(rag._raiz(conocimiento._sin_tildes(palabra)), palabra)
    return dichas


def faltas(base: Path | None = None, dias: int = DIAS, minimo: int = 1,
           hoy: date | None = None, ruta: Path | None = None) -> list[Falta]:
    """Lo que no supo contestar, agrupado y de lo más preguntado a lo menos.

    `minimo` sube el listón: con 2, solo lo que ha pasado más de una vez, que
    es lo que de verdad merece que alguien escriba un párrafo.
    """
    desde = ((hoy or date.today()) - timedelta(days=dias)).isoformat()

    # Primera vuelta: qué hay pendiente y con qué palabras.
    pendientes = []
    cuantas: dict[str, int] = {}
    como_se_dicen: dict[str, str] = {}
    for aviso in avisos.listar(ruta=ruta):
        datos = aviso.get("datos") or {}
        que = datos.get("falta")
        if not que or aviso.get("fecha", "") < desde:
            continue
        frase = (datos.get("frase") or "").strip()
        palabras = _palabras(frase, base) if frase else set()
        # Una frase sin ninguna palabra con contenido («pues nada») no es una
        # pregunta pendiente: es ruido, y llenaría la lista de grupos vacíos.
        if frase and not palabras:
            continue
        pendientes.append((que, palabras, frase, aviso.get("fecha", "")))
        for palabra in palabras:
            cuantas[palabra] = cuantas.get(palabra, 0) + 1
        for raiz, dicha in _como_se_dicen(frase).items():
            como_se_dicen.setdefault(raiz, dicha)

    # Segunda vuelta: cada frase, al grupo de su palabra más repetida.
    grupos: dict[tuple, Falta] = {}
    for que, palabras, frase, fecha in pendientes:
        if palabras:
            # A igualdad de repeticiones, la más larga: entre «uña» y «gel»
            # con una cada una, la que más dice de la pregunta.
            clave = (max(palabras, key=lambda p: (cuantas[p], len(p), p)),)
        else:
            clave = ()
        grupo = grupos.setdefault(
            (que, clave),
            Falta(que=que, palabras=tuple(como_se_dicen.get(p, p) for p in clave)))
        grupo.veces += 1
        grupo.ultima = max(grupo.ultima, fecha)
        if frase and frase not in grupo.ejemplos and len(grupo.ejemplos) < EJEMPLOS:
            grupo.ejemplos.append(frase)

    encontrados = [g for g in grupos.values() if g.veces >= minimo]
    for grupo in encontrados:
        if not grupo.ejemplos:
            grupo.ejemplos.append(COMO_SE_DICE.get(grupo.que, grupo.que))
    encontrados.sort(key=lambda g: (-g.veces, g.ultima, g.titulo))
    return encontrados


def por_tipo(lista: list[Falta]) -> dict[str, list[Falta]]:
    """Las faltas repartidas por lo que le faltaba al agente."""
    reparto: dict[str, list[Falta]] = {}
    for falta in lista:
        reparto.setdefault(falta.que, []).append(falta)
    return reparto


def texto(lista: list[Falta], tope: int = 8) -> list[str]:
    """Las líneas que se le enseñan al dueño, agrupadas por dónde se arreglan."""
    lineas = []
    for que, suyas in por_tipo(lista[:tope]).items():
        lineas.append(f"{COMO_SE_DICE.get(que, que)}:")
        lineas += [f"  {falta.dicho()}" for falta in suyas]
    return lineas


def main(argumentos: list[str] | None = None) -> int:
    """`python3 aprender.py`: qué le falta saber al agente, por orden."""
    import argparse

    from hugin.negocio import negocio as negocios

    parser = argparse.ArgumentParser(
        description="Lo que el agente no supo contestar, para escribirlo")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--dias", type=int, default=DIAS)
    parser.add_argument("--minimo", type=int, default=1,
                        help="solo lo preguntado al menos estas veces")
    args = parser.parse_args(argumentos)

    try:
        negocio = negocios.cargar(args.negocio)
    except (FileNotFoundError, ValueError) as error:
        print(f"❌ {error}")
        return 1
    datos.usar(negocio)

    lista = faltas(negocio.conocimiento, dias=args.dias, minimo=args.minimo)
    if not lista:
        print(f"Nada pendiente en los últimos {args.dias} días: "
              "lo ha sabido contestar todo.")
        return 0

    print(f"Lo que el agente no supo contestar (últimos {args.dias} días):\n")
    for linea in texto(lista, tope=20):
        print(linea)
    print("\nEscríbelo en el fichero que dice cada línea y reinicia: "
          "a partir de ahí lo contesta solo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
