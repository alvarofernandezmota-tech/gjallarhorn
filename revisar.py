"""¿Está este bot listo para coger llamadas? Una orden y una respuesta.

Antes de dar un número de teléfono a un negocio hay seis cosas que mirar, y
están repartidas en seis sitios: si el conocimiento está puesto, si las
frases se cargan, si hay horario, si el webhook tiene token, si los avisos
llegan al móvil, si hay copia de hoy. Cada una tiene su orden y su salida, y
nadie se las sabe todas de memoria.

    make revisar

Esto las junta y contesta una cosa: **listo** o **no listo**, con lo que
falta. Sale 1 si hay algo roto, así que sirve igual para un gancho o un
cron. Es la misma idea que `verificar.py` en midgaror: una sola orden que
encadena todo y devuelve 1 si algo falla.

## Qué es un fallo y qué es un aviso

- **Fallo** es lo que hace que una llamada salga mal: sin tarifas no puede
  dar precios, un `frases.toml` con una errata deja al bot diciendo la
  frase de fábrica, y sin token no hay webhook que valga.
- **Aviso** es lo que funciona pero conviene mirar: sin horario toma nota en
  vez de reservar, sin Telegram los avisos se quedan en el fichero, y sin
  copia de hoy estás a un borrado de perder la agenda.

Nada de esto arregla nada solo. Aquí se mira y se dice; escribir las tarifas
o poner el token lo hace quien lleva el negocio.
"""

import os
from dataclasses import dataclass
from datetime import date

import aprender
import avisar
import conocimiento
import copias
import datos
import frases as _frases
import negocio as negocios
import telefonia

BIEN, AVISO, FALLO = "✅", "⚠️ ", "❌"


@dataclass(frozen=True)
class Punto:
    """Una cosa mirada: cómo ha salido y qué decir de ella."""

    marca: str
    titulo: str
    detalle: str = ""

    @property
    def roto(self) -> bool:
        return self.marca == FALLO


def _conocimiento(negocio) -> list[Punto]:
    servicios = conocimiento.tarifas(negocio.conocimiento)
    faltan = conocimiento.que_falta(negocio.conocimiento)
    puntos = []
    if servicios:
        puntos.append(Punto(BIEN, f"tarifas: {len(servicios)} servicio(s)"))
    else:
        puntos.append(Punto(FALLO, "tarifas: ninguna",
                            "sin tabla no puede dar un precio: negocios/"
                            f"{negocio.ruta.name}/tarifas.md"))
    if "faq.md" in faltan:
        puntos.append(Punto(AVISO, "faq.md: vacía",
                            "el horario y lo que se pregunta por teléfono salen de ahí"))
    else:
        cuantos = len(__import__("rag").indice(negocio.conocimiento).pasajes)
        puntos.append(Punto(BIEN, f"conocimiento: {cuantos} párrafo(s) que puede contestar"))
    return puntos


def _frases_del_bot(negocio) -> list[Punto]:
    problemas = _frases.problemas(negocio.conocimiento)
    if problemas:
        return [Punto(FALLO, "frases.toml: no se puede usar", "; ".join(problemas))]

    trato, descolgadas = _frases.como_trata(negocio.conocimiento)
    como = {"tu": "de tú", "usted": "de usted"}.get(trato, "sin decidir")
    if descolgadas:
        return [Punto(AVISO, f"frases: trata {como}, pero {len(descolgadas)} no",
                      f"{', '.join(descolgadas[:6])} — se ven con «make frases»")]
    return [Punto(BIEN, f"frases: trata {como} en todo")]


def _agenda_y_datos(negocio, hoy: date) -> list[Punto]:
    puntos = []
    if negocio.horario is None:
        puntos.append(Punto(AVISO, "horario: no está escrito",
                            "sin él toma nota, pero no reserva ni ofrece huecos"))
    else:
        abiertos = sum(1 for tramos in negocio.horario.tramos.values() if tramos)
        puntos.append(Punto(BIEN, f"horario: abre {abiertos} día(s) por semana"))

    fechas_copias = copias.listar()
    if hoy.isoformat() in fechas_copias:
        puntos.append(Punto(BIEN, f"copias: la de hoy hecha ({len(fechas_copias)} guardadas)"))
    elif fechas_copias:
        puntos.append(Punto(AVISO, f"copias: la última es del {fechas_copias[-1]}",
                            "«make copia» hace la de hoy"))
    else:
        puntos.append(Punto(AVISO, "copias: ninguna todavía", "«make copia»"))
    return puntos


def _por_donde_habla() -> list[Punto]:
    puntos = []
    puesto = telefonia.configuracion()
    if puesto and telefonia.token_de_mentira(puesto["token"]):
        puntos.append(Punto(FALLO, "teléfono: el token es el hueco del ejemplo",
                            "GJALLARHORN_TELEFONO_TOKEN en .env tiene el texto de "
                            "relleno; el webhook arranca y luego cada llamada se "
                            "cae con un 403"))
    elif puesto:
        puntos.append(Punto(BIEN, "teléfono: token puesto, el webhook arranca"))
    else:
        puntos.append(Punto(FALLO, "teléfono: sin token",
                            "GJALLARHORN_TELEFONO_TOKEN en .env; sin él no hay webhook"))
    repetidas = avisar.repetidas_en_env()
    if repetidas:
        puntos.append(Punto(AVISO, f".env: {', '.join(repetidas)} está puesto dos veces",
                            "vale el de abajo; borra el que sobre para no jugártela"))
    if avisar.configuracion():
        puntos.append(Punto(BIEN, "avisos al móvil: configurados"))
    else:
        puntos.append(Punto(AVISO, "avisos al móvil: sin configurar",
                            "se quedan en el fichero; «make telegram-prueba» cuando lo pongas"))
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        puntos.append(Punto(BIEN, "cerebro: encendido (el texto del cliente sale de casa)"))
    else:
        puntos.append(Punto(BIEN, "cerebro: apagado, solo reglas"))
    return puntos


def _lo_que_no_sabe(negocio, hoy: date) -> list[Punto]:
    pendientes = aprender.faltas(negocio.conocimiento, minimo=2, hoy=hoy)
    if not pendientes:
        return [Punto(BIEN, "no hay preguntas repetidas sin contestar")]
    primera = pendientes[0]
    return [Punto(AVISO, f"{len(pendientes)} pregunta(s) repetida(s) que no sabe contestar",
                  f"la más repetida: «{primera.ejemplo}» ({primera.veces} veces)"
                  f"{' → ' + primera.donde if primera.donde else ''} — «make aprender»")]


def revisar(negocio, hoy: date | None = None) -> list[Punto]:
    """Todo lo que hay que mirar antes de dar el número. En orden de gravedad."""
    hoy = hoy or date.today()
    puntos = [Punto(BIEN, f"negocio: {negocio.nombre} ({negocio.ruta.name})")]
    puntos += _conocimiento(negocio)
    puntos += _frases_del_bot(negocio)
    puntos += _agenda_y_datos(negocio, hoy)
    puntos += _por_donde_habla()
    puntos += _lo_que_no_sabe(negocio, hoy)
    puntos += [Punto(AVISO, aviso) for aviso in negocios.advertencias(negocio)]
    return puntos


def main(argumentos: list[str] | None = None) -> int:
    """`make revisar`: listo o no listo, y qué falta. Sale 1 si algo está roto."""
    import argparse

    parser = argparse.ArgumentParser(description="¿Está este bot listo para coger llamadas?")
    parser.add_argument("--negocio", default="peluqueria")
    args = parser.parse_args(argumentos)

    try:
        negocio = negocios.cargar(args.negocio)
    except (FileNotFoundError, ValueError) as error:
        print(f"{FALLO} {error}")
        return 1
    datos.usar(negocio)

    puntos = revisar(negocio)
    for punto in puntos:
        print(f" {punto.marca} {punto.titulo}")
        if punto.detalle:
            print(f"      {punto.detalle}")

    rotos = [p for p in puntos if p.roto]
    print()
    if rotos:
        print(f"{FALLO} No está listo para coger llamadas: {len(rotos)} cosa(s) rotas.")
        return 1
    avisos_ = [p for p in puntos if p.marca == AVISO]
    print(f"{BIEN} Listo para coger llamadas."
          + (f" ({len(avisos_)} aviso(s) que mirar cuando puedas)" if avisos_ else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
