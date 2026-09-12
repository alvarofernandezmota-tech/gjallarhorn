"""Buscar en lo que ha escrito el dueño. Sin embeddings y sin salir de casa.

`conocimiento.py` mete **todo** el texto del negocio en el prompt, y eso vale
mientras todo quepa: `cabe_en()` dice cuándo deja de caber. Este fichero es lo
que hay que tener el día que no quepa, y sirve desde antes: encuentra el
párrafo que contesta a una pregunta aunque la FAQ tenga cuarenta.

## Por qué léxico y no embeddings

La respuesta corta: porque aquí gana, no porque sea más fácil.

- **No sale de casa.** Un embedding se calcula con un modelo; si es de la
  nube, cada pregunta del cliente viaja. Esto se resuelve entero en local.
- **Sin dependencias.** Ni base vectorial, ni un modelo de 90 MB, ni un
  índice que reconstruir. Son cien líneas y el diccionario de Python.
- **Es determinista.** La misma pregunta da el mismo párrafo siempre, y eso
  se puede probar. Un vecino más cercano cambia al cambiar de modelo.
- **El corpus es diminuto.** Cuarenta párrafos. BM25 sobre cuarenta párrafos
  no es peor que un embedding: es que no hay sitio donde ser peor.

El día que un negocio tenga cien páginas y la gente pregunte con palabras que
no están escritas en ningún sitio («¿me lo dejáis rubio ceniza?» contra un
texto que solo dice «coloración»), entonces sí: embeddings **encima** de
esto, no en vez de esto. Los sinónimos de `frases.toml` cubren hoy ese hueco
y los escribe quien conoce a su clientela.

## La regla que no cambia

**Los precios no salen de aquí.** Salen de la tabla de `tarifas.md` por
`conocimiento.buscar()`, que es una consulta exacta. Las filas de tabla se
quitan antes de indexar justamente para eso: que ningún camino pueda acabar
leyendo un precio recuperado «por parecido». Lo que se recupera aquí se dice
**tal cual lo escribió el dueño**, sin parafrasear y sin modelo por medio.

## Cuándo se calla

Casi siempre es mejor un recado que la respuesta a otra pregunta. Así que
hace falta que el párrafo cubra buena parte de lo preguntado (`MINIMO`) y
que le saque distancia al segundo (`VENTAJA`). Si dos párrafos empatan, no
se contesta: es el caso de «tarjeta» cuando hay un bloque de pagos y otro de
tarjetas regalo.

## Los números no están puestos a ojo

`MINIMO`, `VENTAJA` y los pesos salen de un banco de frases etiquetadas
—`TestElBanco`, en las pruebas— con lo que contesta cada una y lo que debe
callar. Se probaron todas las combinaciones contra ese banco y se eligió la
que no falla ninguna. Cuando alguien cambie una constante, el banco dirá si
la ha mejorado o si solo ha movido el fallo de sitio.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path

from hugin.mente import conocimiento

# Cuánto de lo preguntado tiene que cubrir un párrafo para darlo por bueno.
# Se mide con los pesos de las palabras, no contándolas: en «¿aceptáis
# tarjeta?» lo que importa es «tarjeta», que sale en un sitio, no «aceptáis»,
# que puede salir en cinco.
MINIMO = 0.25

# Y cuánto le tiene que sacar al segundo. Por debajo de esto hay empate y no
# se contesta.
VENTAJA = 1.25

# Lo que pesa el título —la pregunta del bloque— frente al cuerpo. Es la
# diferencia entre contestar y contestar otra cosa: la respuesta de «¿hace
# falta cita?» nombra el tinte, las mechas y los recogidos, así que sin esto
# cualquiera que dijera «tinte» se llevaba «para tinte, mechas y recogidos
# sí» en vez de su precio. Lo que identifica a un bloque es su pregunta.
PESO_TITULO = 0.75

# BM25 de manual. `k1` satura la repetición (una palabra diez veces no vale
# diez veces) y `b` corrige por longitud (un párrafo largo tiene más palabras
# y no por eso es más relevante).
K1 = 1.5
B = 0.75

# Lo que pesa una palabra que NO está escrita en ningún sitio del negocio.
# Cero era el fallo gordo: «me paso el jueves a las cinco a por un tinte» se
# quedaba en «tinte» —lo único conocido— y salía cubierto al 100 %, así que
# contestaba la pregunta del tinte a quien estaba pidiendo hora. Una palabra
# que el dueño no ha escrito nunca es justamente señal de que esto no lo
# cubre, así que cuenta en el denominador; a la mitad que una conocida,
# porque también puede ser una muletilla.
PESO_DESCONOCIDA = 0.5

# Una palabra que solo sale en un pasaje es muy específica, y entonces da
# igual que esté en el cuerpo y no en el título: «amoniaco» sale una vez en
# toda la casa, así que quien lo dice está preguntando por ese párrafo. Sin
# esto, el peso del título tumbaba justo las preguntas más concretas.
ESPECIFICA = 0.8          # a partir de qué parte del idf máximo se llama rara
PESO_ESPECIFICA = 0.5     # y cuánto vale cubrirlo entero solo con el cuerpo

# Las filas de tabla se quitan: los precios son consulta exacta, no búsqueda.
FILA_TABLA = re.compile(r"^\s*\|.*$", re.M)

_CACHE: dict[str, tuple[tuple, "Indice"]] = {}


@dataclass(frozen=True)
class Pasaje:
    """Un trozo del conocimiento del negocio, con de dónde ha salido."""

    fuente: str          # el fichero: «faq.md»
    titulo: str          # la pregunta o el encabezado que lo encabeza
    texto: str           # lo que se le diría a quien llama, tal cual
    puntos: float = 0.0  # cuánto encaja con lo preguntado, de 0 a 1

    @property
    def dicho(self) -> str:
        """Lo que se dice en voz alta. El texto del dueño, sin adornos."""
        return self.texto


def _singular(palabra: str) -> str:
    """La raíz con la que se compara: «novias» → «novia», «masajes» → «masaj».

    Dos pasos, y el segundo es el que importa: se quita la ese del plural y
    **luego la e final**. Sin el segundo paso, «masaje» y «masajes» eran dos
    palabras distintas —una acababa en «masaje» y la otra en «masaj»— y la
    misma pregunta salía en dos líneas. Con él, las dos caen en «masaj», que
    es lo único que hace falta: esto no se le enseña a nadie, solo se compara.

    Por eso tampoco importa que «flores» y «flor» acaben en «flor» y «clase»
    en «clas»: mientras la regla se aplique igual a lo que pregunta el
    cliente y a lo que escribió el dueño, casan. Es toda la morfología que
    hay aquí, a propósito: un lematizador de verdad es otra dependencia y
    otro sitio donde equivocarse, y lo que no cubre —«aparcar» contra
    «aparcamiento»— lo cubren los sinónimos de `frases.toml`.
    """
    if len(palabra) >= 4 and palabra.endswith("s"):
        palabra = palabra[:-1]
    if len(palabra) >= 5 and palabra.endswith("e"):
        palabra = palabra[:-1]
    return palabra


def _tokens(texto: str, base: Path | None = None) -> list[str]:
    """Las palabras con contenido, en orden y con repeticiones.

    Pasa por los sinónimos del negocio igual que lo que dice quien llama: si
    el dueño escribió «reflejos» y el cliente dice «mechas», los dos acaban
    en la misma palabra. `conocimiento.palabras_dichas` devuelve un conjunto
    —le vale— pero BM25 necesita contar, así que aquí se rehace en lista.

    """
    from hugin.negocio import frases as _frases

    llano = conocimiento._sin_tildes(texto)
    traducido = llano
    sinonimos = _frases.cargar(base).sinonimos
    for dicho in sorted(sinonimos, key=len, reverse=True):
        traducido = re.sub(rf"\b{re.escape(dicho)}\b", sinonimos[dicho], traducido)
    palabras = _utiles(llano)
    # Los sinónimos **suman**, no sustituyen. Sustituyendo se perdía la
    # palabra original, y con ella la pregunta: «peinados de novia» tiene
    # «de novia» como sinónimo de «recogido», y al cambiarla desaparecía
    # «novia», que es justo lo que había que buscar en la FAQ.
    return palabras + [p for p in _utiles(traducido) if p not in palabras]


def propias(texto: str, base: Path | None = None) -> set[str]:
    """Solo las palabras que dijo de verdad, sin lo que añaden los sinónimos.

    Un sinónimo es una pista, no una palabra dicha: sirve para encontrar, no
    para dar por concreta una pregunta que no lo era.
    """
    return set(_utiles(conocimiento._sin_tildes(texto)))


def _utiles(texto: str) -> list[str]:
    """Las palabras con contenido de un texto ya en minúsculas y sin tildes.

    Las vacías se quitan **antes y después** de quitar el plural: «gracias»
    es una muletilla, y en singular sería «gracia», que ya no está en la
    lista y volvería a colarse.
    """
    crudas = [p for p in re.findall(r"\w+", texto) if p not in conocimiento.VACIAS]
    return [_raiz(p) for p in crudas]


def _raiz(palabra: str) -> str:
    """La raíz, salvo que al quitarle el plural se convierta en una muletilla.

    «uñas» sin tildes es «unas», y quitándole la ese queda «una», que es un
    artículo y está en la lista de palabras vacías. Sin esta excepción, quien
    preguntaba por las uñas se quedaba sin ninguna palabra que buscar: la
    pregunta desaparecía entera.
    """
    raiz = _singular(palabra)
    return palabra if raiz in conocimiento.VACIAS else raiz


def _partir(texto: str, fuente: str) -> list[Pasaje]:
    """El texto de un fichero, en párrafos con su título.

    Tres formas de escribir, las tres válidas porque las tres se usan:

        **¿Aceptáis tarjeta?**     una pregunta en negrita y debajo la respuesta
        ## Aparcamiento            un encabezado de Markdown
        (un párrafo suelto)        sin título, se titula solo con su primera línea

    Un bloque sin cuerpo —un título y nada debajo— no es un pasaje: no hay
    nada que contestar con él.
    """
    limpio = FILA_TABLA.sub("", conocimiento.COMENTARIO.sub("", texto))
    pasajes = []
    for bloque in re.split(r"\n(?=\*\*|#{1,6}\s)|\n\s*\n", limpio):
        bloque = bloque.strip()
        if not bloque:
            continue
        cabeza, _, cuerpo = bloque.partition("\n")
        titulo = cabeza.strip().strip("*# ").strip()
        cuerpo = cuerpo.strip()
        if not cuerpo:
            # Un párrafo suelto: es su propio cuerpo, y el título es él mismo.
            if cabeza.strip().startswith(("#", "**")):
                continue        # un encabezado sin nada debajo no contesta nada
            cuerpo, titulo = cabeza.strip(), cabeza.strip()
        pasajes.append(Pasaje(fuente=fuente, titulo=titulo, texto=cuerpo))
    return pasajes


class _Campo:
    """Un campo indexado (los títulos, o los cuerpos) y su BM25."""

    def __init__(self, documentos: list[list[str]]):
        self.largos = [len(d) or 1 for d in documentos]
        self.medio = sum(self.largos) / len(self.largos) if self.largos else 1.0
        self.frecuencias = [_contar(d) for d in documentos]

    def puntuar(self, consulta: list[str], pesos: list[float], techo: float) -> list[float]:
        puntuaciones = []
        for frecuencia, largo in zip(self.frecuencias, self.largos):
            suma = 0.0
            for palabra, peso in zip(consulta, pesos):
                f = frecuencia.get(palabra, 0)
                if not f:
                    continue
                suma += peso * (f * (K1 + 1)) / (f + K1 * (1 - B + B * largo / self.medio))
            # El (K1+1) hace que el máximo por palabra pase de 1, así que se
            # acota: cubrir una palabra dos veces no es cubrirla el doble.
            puntuaciones.append(min(suma / techo, 1.0))
        return puntuaciones


def _contar(palabras: list[str]) -> dict[str, int]:
    cuenta: dict[str, int] = {}
    for palabra in palabras:
        cuenta[palabra] = cuenta.get(palabra, 0) + 1
    return cuenta


class Indice:
    """Los párrafos del negocio, listos para buscar. BM25, en memoria.

    Dos campos, y no por gusto: el **título** es la pregunta con la que se
    identifica el bloque y el **cuerpo** es la respuesta. Una respuesta que
    nombra medio catálogo no convierte al bloque en la respuesta de medio
    catálogo, y medirlos juntos sí lo hacía.
    """

    def __init__(self, pasajes: list[Pasaje], base: Path | None = None):
        self.base = base
        self.pasajes = pasajes
        self.titulos = [_tokens(p.titulo, base) for p in pasajes]
        self.cuerpos = [_tokens(p.texto, base) for p in pasajes]
        self.idf = self._idf()
        self._titulo = _Campo(self.titulos)
        self._cuerpo = _Campo(self.cuerpos)

    def _idf(self) -> dict[str, float]:
        """Cuánto pesa cada palabra: las que salen en todos lados no pesan."""
        total = len(self.pasajes) or 1
        # Lo que pesaría una palabra que sale en un solo pasaje: el techo.
        self.idf_maximo = math.log(1 + (total - 0.5) / 1.5)
        en_cuantos: dict[str, int] = {}
        for titulo, cuerpo in zip(self.titulos, self.cuerpos):
            for palabra in set(titulo) | set(cuerpo):
                en_cuantos[palabra] = en_cuantos.get(palabra, 0) + 1
        return {palabra: math.log(1 + (total - cuantos + 0.5) / (cuantos + 0.5))
                for palabra, cuantos in en_cuantos.items()}

    def puntuar(self, consulta: list[str], propias_de: set[str] | None = None) -> list[float]:
        """Cuánto encaja cada pasaje con la consulta, de 0 a 1.

        La escala es *cuánto de lo preguntado se ha cubierto*, no los puntos
        crudos de BM25: así el umbral significa algo y no hay que retocarlo
        cada vez que crece el corpus. `propias_de` son las palabras que dijo
        de verdad: las que añaden los sinónimos valen para encontrar, pero no
        para dar una pregunta por concreta.
        """
        propias_de = set(consulta) if propias_de is None else propias_de
        desconocida = self.idf_maximo * PESO_DESCONOCIDA
        pesos = [self.idf.get(palabra, desconocida) for palabra in consulta]
        techo = sum(pesos)
        if techo <= 0:
            return [0.0] * len(self.pasajes)
        titulos = self._titulo.puntuar(consulta, pesos, techo)
        cuerpos = self._cuerpo.puntuar(consulta, pesos, techo)

        # Las palabras raras de la consulta, medidas aparte sobre el cuerpo.
        # Sobre el techo de la consulta **entera**: una palabra rara cubierta
        # no tapa que el resto de la pregunta no lo esté. Sin eso, «quiero
        # cita para mañana a las once» se llevaba el párrafo del aparcamiento
        # porque allí sale «por la mañana».
        raras = [(palabra, peso) for palabra, peso in zip(consulta, pesos)
                 if peso >= ESPECIFICA * self.idf_maximo and palabra in propias_de]
        if raras:
            especificos = self._cuerpo.puntuar([p for p, _ in raras],
                                               [p for _, p in raras], techo)
        else:
            especificos = [0.0] * len(self.pasajes)

        return [max(PESO_TITULO * t + (1 - PESO_TITULO) * c, PESO_ESPECIFICA * e)
                for t, c, e in zip(titulos, cuerpos, especificos)]

    def _solo_un_servicio(self, frase: str) -> bool:
        """¿Lo único que dice es el nombre de un servicio de la tabla?

        «¿Cuánto vale un tinte?» y «oye, ¿hacéis lo del color ese?» se quedan
        en «tinte» al quitar las muletillas. Eso no es una pregunta de la FAQ:
        es precio o es cita, y de eso se encargan la tabla y las reglas. Sin
        esta regla, quien preguntaba un precio se llevaba el párrafo de la FAQ
        donde salía la palabra.
        """
        dichas = conocimiento.palabras_dichas(frase, self.base)
        return bool(dichas) and dichas <= conocimiento.vocabulario(self.base)

    def buscar(self, consulta: str, tope: int = 3, minimo: float = 0.0) -> list[Pasaje]:
        """Los pasajes que mejor encajan, el mejor primero."""
        palabras = _tokens(consulta, self.base)
        if not palabras or not self.pasajes:
            return []
        suyas = propias(consulta, self.base)
        puntuados = [(puntos, pasaje)
                     for puntos, pasaje in zip(self.puntuar(palabras, suyas), self.pasajes)
                     if puntos > minimo]
        puntuados.sort(key=lambda p: (-p[0], p[1].fuente, p[1].titulo))
        return [Pasaje(p.fuente, p.titulo, p.texto, round(puntos, 4))
                for puntos, p in puntuados[:tope]]

    def responder(self, frase: str) -> Pasaje | None:
        """El pasaje que contesta, o None si no hay uno claro.

        Claro quiere decir dos cosas: que cubra `MINIMO` de lo preguntado y
        que le saque `VENTAJA` al siguiente. Con dos pasajes parecidos se
        calla, porque contestar el que no era es peor que tomar el recado.
        """
        if self._solo_un_servicio(frase) or _habla_de_cuando(frase):
            return None
        encontrados = self.buscar(frase, tope=2)
        if not encontrados or encontrados[0].puntos < MINIMO:
            return None
        if len(encontrados) > 1 and encontrados[1].puntos > 0 \
                and encontrados[0].puntos < encontrados[1].puntos * VENTAJA:
            return None
        return encontrados[0]


def _habla_de_cuando(frase: str) -> bool:
    """¿La frase dice un día o una hora? Entonces no es una pregunta de la FAQ.

    «Me paso el jueves a las cinco a por un tinte» lleva la palabra «tinte» y
    sin esto se llevaba el párrafo de la FAQ donde sale. Quien dice cuándo
    está pidiendo hora, y de eso se encargan las reglas de la cita.
    """
    from hugin.mente import fechas

    return fechas.interpretar(frase) is not None or fechas.hora_suelta(frase) is not None


def _ficheros(base: Path | None) -> list[Path]:
    """Los `.md` del negocio, en orden fijo para que el índice sea estable."""
    carpeta = Path(base) if base else conocimiento.carpeta()
    if not carpeta.is_dir():
        return []
    return sorted(carpeta.glob("*.md"))


def indice(base: Path | None = None) -> Indice:
    """El índice del negocio. Se rehace solo cuando se toca un fichero.

    Sin la caché se reconstruye en cada turno de cada llamada; con una caché
    que no mire las fechas, editar `faq.md` no serviría de nada hasta
    reiniciar, y eso es justo lo que promete el README que no pasa.
    """
    ficheros = _ficheros(base)
    huella = tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in ficheros)
    clave = str(base or "")
    guardado = _CACHE.get(clave)
    if guardado is not None and guardado[0] == huella:
        return guardado[1]

    pasajes = []
    for fichero in ficheros:
        pasajes += _partir(fichero.read_text(encoding="utf-8"), fichero.name)
    nuevo = Indice(pasajes, base)
    _CACHE[clave] = (huella, nuevo)
    return nuevo


def olvidar() -> None:
    """Tira la caché. Para las pruebas y para recargar sin reiniciar."""
    _CACHE.clear()


def responder(frase: str, base: Path | None = None) -> Pasaje | None:
    """Qué contesta el conocimiento del negocio a esto, o None si no lo cubre."""
    return indice(base).responder(frase)


def buscar(frase: str, base: Path | None = None, tope: int = 3) -> list[Pasaje]:
    """Los pasajes que más encajan, aunque ninguno sea concluyente."""
    return indice(base).buscar(frase, tope=tope)


def contexto(frase: str, base: Path | None = None, tope: int = 3,
             limite: int = 1200) -> str:
    """Lo que sabe el negocio sobre esto, para metérselo a un modelo.

    Con la fuente delante de cada trozo, y acotado: el prompt de una llamada
    de teléfono no puede crecer sin freno. Si todo el conocimiento cabe
    —lo normal— esto no hace falta y `conocimiento.para_prompt` va entero.
    """
    trozos, usado = [], 0
    for pasaje in buscar(frase, base, tope=tope):
        trozo = f"[{pasaje.fuente} · {pasaje.titulo}]\n{pasaje.texto}"
        if usado + len(trozo) > limite:
            break
        trozos.append(trozo)
        usado += len(trozo)
    return "\n\n".join(trozos)


def main() -> int:
    """`python3 rag.py "¿aceptáis tarjeta?"`: qué encuentra y con cuántos puntos."""
    import argparse

    from hugin.negocio import negocio as negocios

    parser = argparse.ArgumentParser(description="Qué encuentra el buscador del conocimiento")
    parser.add_argument("frase", nargs="?", default="¿se puede pagar con tarjeta?")
    parser.add_argument("--negocio", default="peluqueria")
    parser.add_argument("--todo", action="store_true", help="listar los pasajes indexados")
    args = parser.parse_args()

    negocio = negocios.cargar(args.negocio)
    el_indice = indice(negocio.conocimiento)

    if args.todo:
        print(f"{len(el_indice.pasajes)} pasajes indexados:")
        for pasaje in el_indice.pasajes:
            print(f"  {pasaje.fuente:12} {pasaje.titulo[:60]}")
        return 0

    print(f"«{args.frase}»")
    for pasaje in el_indice.buscar(args.frase):
        print(f"  {pasaje.puntos:.2f}  [{pasaje.fuente}] {pasaje.titulo}")
        print(f"        {pasaje.texto[:120]}")
    contestado = el_indice.responder(args.frase)
    print(f"\n→ {contestado.texto if contestado else '(no hay nada claro: recado)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
