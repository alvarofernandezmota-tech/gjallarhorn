"""Un negocio = una carpeta. Copiarla es dar de alta otro cliente.

    negocios/
      peluqueria/
        negocio.toml   nombre, saludo, voz
        tarifas.md     la tabla de precios
        faq.md         lo que se pregunta por teléfono

Para montar otro no se toca código: se copia la carpeta, se cambian los dos
Markdown y el nombre. Eso es todo, y es a propósito — quien lleva el negocio
tiene que poder cambiar un precio sin llamar a nadie.

    python3 recepcion.py --negocio peluqueria

## El aviso de que es automático no se puede quitar

`negocio.toml` deja personalizar el saludo, pero **si el saludo propio no dice
que se habla con un sistema automático, se le añade al cargarlo**. No es un
descuido que se pueda cometer editando un fichero de texto: informar de eso no
es opcional, y la forma de garantizarlo es que no dependa de que alguien se
acuerde.
"""

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

AVISO_AUTOMATICO = "Le atiende un asistente automático."

SALUDO_POR_DEFECTO = (f"Hola, {AVISO_AUTOMATICO[0].lower()}{AVISO_AUTOMATICO[1:]} "
                      "Puedo darle precios y tomarle una cita. ¿En qué puedo ayudarle?")

# Lo que cuenta como haber avisado, sin tildes ni mayúsculas.
SENALES_DE_AVISO = ("automatic", "automátic", "asistente virtual", "robot",
                    "inteligencia artificial", "no es una persona")


VARIABLE = "GJALLARHORN_NEGOCIOS"


def carpeta_negocios() -> Path:
    """Dónde viven los negocios. Por defecto, aquí dentro; y se puede mover.

    Que se pueda mover no es un capricho de configuración: **este repo es
    público**, y lo que se deje en `negocios/` se publica con él. El nombre
    de tu negocio, tus precios y tus preguntas frecuentes puede que quieras
    publicarlos; el fichero con la forma de saludar a tus clientes y lo que
    cobras, a lo mejor no.

        export GJALLARHORN_NEGOCIOS=~/negocios

    Y con eso, los datos del negocio viven fuera del repo, no se suben al
    hacer `git push` y `git pull` no te los pisa nunca.
    """
    valor = os.environ.get(VARIABLE, "").strip()
    if valor:
        return Path(valor).expanduser().resolve()
    return Path(__file__).resolve().parent / "negocios"


@dataclass(frozen=True)
class Negocio:
    """Todo lo que cambia de un cliente a otro. Ni una línea de código."""

    nombre: str
    ruta: Path
    saludo: str
    despedida: str
    voz: str | None = None
    horario: "object | None" = None   # agenda.Horario, si negocio.toml lo trae

    @property
    def conocimiento(self) -> Path:
        """Dónde están `tarifas.md` y `faq.md`. Es la carpeta del negocio."""
        return self.ruta


def _con_aviso(saludo: str) -> str:
    """El saludo, avisando de que es automático. Si no lo dice, se lo dice."""
    plano = saludo.lower()
    if any(senal in plano for senal in SENALES_DE_AVISO):
        return saludo
    return f"{saludo.rstrip()} {AVISO_AUTOMATICO}".strip()


def _horario(config, fichero):
    """El horario del negocio, o None si no está escrito.

    Un horario mal escrito se dice con el fichero y la línea que lo causa, al
    cargar, no en la primera llamada que intente reservar.
    """
    if not config:
        return None
    import agenda
    try:
        return agenda.Horario.desde(config)
    except ValueError as error:
        raise ValueError(f"{fichero}: {error}") from error


def cargar(cual: str | Path) -> Negocio:
    """El negocio por su nombre de carpeta, o por una ruta.

    Sin `negocio.toml` funciona igual con los valores por defecto: una carpeta
    con los dos Markdown ya es un negocio. Pedir un fichero de configuración
    para dar de alta una peluquería sería ponerse exquisito.
    """
    ruta = Path(cual)
    if not ruta.is_absolute() and not ruta.exists():
        ruta = carpeta_negocios() / cual
    if not ruta.is_dir():
        disponibles = ", ".join(sorted(p.name for p in carpeta_negocios().iterdir()
                                       if p.is_dir())) if carpeta_negocios().is_dir() else "ninguno"
        raise FileNotFoundError(
            f"no encuentro el negocio {str(cual)!r} en {ruta}. Hay: {disponibles}")

    config = {}
    fichero = ruta / "negocio.toml"
    if fichero.exists():
        try:
            config = tomllib.loads(fichero.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as error:
            # Esto lo edita quien lleva el negocio, no quien programa: un
            # error de sintaxis tiene que decir qué fichero y qué línea, no
            # salir como un traceback de tomllib en mitad del arranque.
            raise ValueError(
                f"{fichero}: la línea no está bien escrita ({error}).\n"
                '   Recuerda: los textos van entre comillas —nombre = "Mi negocio"— y\n'
                '   los horarios son listas de cadenas: lunes = ["10:00-14:00", "16:30-20:00"],\n'
                "   y un día cerrado es una lista vacía: domingo = []."
            ) from error

    return Negocio(
        nombre=config.get("nombre", ruta.name),
        ruta=ruta,
        saludo=_con_aviso(config.get("saludo", SALUDO_POR_DEFECTO)),
        despedida=config.get("despedida", "Gracias por llamar. Hasta luego."),
        voz=config.get("voz"),
        horario=_horario(config.get("horario"), fichero),
    )


TELEFONO = re.compile(r"(?<![\d.])(?:\+34\s?)?[6789]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}(?![\d.])")


def advertencias(negocio: Negocio) -> list[str]:
    """Lo que conviene saber antes de arrancar. Vacío si nada.

    De momento una sola cosa, pero importa: **este repositorio es público**.
    Un teléfono escrito en `faq.md` o `negocio.toml` acaba en GitHub a la
    vista de cualquiera. Si es el del negocio y quiere que se diga, adelante;
    si es el de alguien, que lo sepa antes de que lo indexe un buscador.
    """
    encontradas = []
    for fichero in ("negocio.toml", "tarifas.md", "faq.md", "frases.toml"):
        ruta = negocio.ruta / fichero
        if not ruta.exists():
            continue
        for numero in TELEFONO.findall(ruta.read_text(encoding="utf-8")):
            encontradas.append(
                f"{fichero} lleva un teléfono ({numero.strip()}). Este repositorio es "
                "público: si no es del negocio y para decirlo a quien llame, fuera.")
    return encontradas


def listar() -> list[str]:
    """Los negocios dados de alta."""
    base = carpeta_negocios()
    return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
