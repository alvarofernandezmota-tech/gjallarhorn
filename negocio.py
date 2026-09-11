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

import tomllib
from dataclasses import dataclass
from pathlib import Path

AVISO_AUTOMATICO = "Le atiende un asistente automático."

SALUDO_POR_DEFECTO = (f"Hola, {AVISO_AUTOMATICO[0].lower()}{AVISO_AUTOMATICO[1:]} "
                      "Puedo darle precios y tomarle una cita. ¿En qué puedo ayudarle?")

# Lo que cuenta como haber avisado, sin tildes ni mayúsculas.
SENALES_DE_AVISO = ("automatic", "automátic", "asistente virtual", "robot",
                    "inteligencia artificial", "no es una persona")


def carpeta_negocios() -> Path:
    return Path(__file__).resolve().parent / "negocios"


@dataclass(frozen=True)
class Negocio:
    """Todo lo que cambia de un cliente a otro. Ni una línea de código."""

    nombre: str
    ruta: Path
    saludo: str
    despedida: str
    voz: str | None = None

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
        config = tomllib.loads(fichero.read_text(encoding="utf-8"))

    return Negocio(
        nombre=config.get("nombre", ruta.name),
        ruta=ruta,
        saludo=_con_aviso(config.get("saludo", SALUDO_POR_DEFECTO)),
        despedida=config.get("despedida", "Gracias por llamar. Hasta luego."),
        voz=config.get("voz"),
    )


def listar() -> list[str]:
    """Los negocios dados de alta."""
    base = carpeta_negocios()
    return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
