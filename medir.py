"""Mide un cerebro contra el banco: cuánto acierta y cuánto tarda.

    python3 medir.py                 # el cerebro de reglas (el listón)

Las dos columnas importan, y la segunda más de lo que parece: **un agente de
voz que tarda cuatro segundos en contestar no se usa**, por mucho que acierte.
Un modelo que sube el acierto del 90 % al 95 % y la latencia de 10 ms a 3 s es
un mal negocio, y eso solo se ve midiendo las dos cosas juntas.

La latencia que sale aquí es la del **cerebro solo**. A lo que se tarda de
verdad hay que sumarle la transcripción, que en Whisper es casi todo el tiempo.
"""

import argparse
import statistics
import sys
import time

import banco
import cerebro


def medir(decidir, frases=None) -> dict:
    """El resultado del banco, más los tiempos por frase en milisegundos."""
    frases = banco.FRASES if frases is None else frases
    tiempos = []

    def cronometrado(frase):
        arranque = time.perf_counter()
        try:
            return decidir(frase)
        finally:
            tiempos.append((time.perf_counter() - arranque) * 1000)

    resultado = banco.evaluar(cronometrado, frases)
    resultado["ms_mediana"] = statistics.median(tiempos) if tiempos else 0.0
    # El peor caso importa más que la media: es el que te hace abandonar.
    resultado["ms_peor"] = max(tiempos) if tiempos else 0.0
    return resultado


def informe(nombre: str, resultado: dict) -> str:
    lineas = [
        f"── {nombre}",
        f"   Acierto   {resultado['aciertos']}/{resultado['total']} "
        f"({resultado['acierto']:.0%})",
        f"   Latencia  {resultado['ms_mediana']:.1f} ms mediana, "
        f"{resultado['ms_peor']:.1f} ms el peor",
    ]
    if resultado["fallos"]:
        lineas.append(f"   Falla en {len(resultado['fallos'])}:")
        for frase, esperada, motivo in resultado["fallos"]:
            lineas.append(f"     «{frase}»")
            lineas.append(f"        esperaba {esperada}, {motivo}")
    return "\n".join(lineas)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mide un cerebro contra el banco")
    parser.add_argument("--solo-fallos", action="store_true",
                        help="sin la cabecera, solo en qué se equivoca")
    args = parser.parse_args()

    resultado = medir(cerebro.decidir)
    if args.solo_fallos:
        for frase, esperada, motivo in resultado["fallos"]:
            print(f"«{frase}» → esperaba {esperada}, {motivo}")
    else:
        print(f"Banco: {len(banco.FRASES)} frases\n")
        print(informe("cerebro de reglas", resultado))
        print("\nEste es el listón. Un LLM tiene que superarlo para merecer la pena.")
        if resultado["acierto"] >= 1.0:
            print(
                "\n⚠️  100 % no es una nota, es un aviso: el banco y el cerebro los\n"
                "   ha escrito el mismo. Hasta que las frases salgan del uso real,\n"
                "   este número mide la coherencia del autor, no la del agente.")
    # Sin código de error: esto informa, no aprueba ni suspende. El día que
    # haya un mínimo acordado, aquí irá.
    return 0


if __name__ == "__main__":
    sys.exit(main())
