---
tipo: readme
fecha: 2026-09-11
repo: gjallarhorn
---

# Scripts

Un script por procedimiento, con el **mismo nombre base** que su `.md` en
[`docs/procedimientos/`](../docs/procedimientos/README.md) (ADR-004 de
midgaror): `transcribir.md` ↔ `transcribir.py`.

## Índice

Vacío todavía.

Los **módulos de librería** —`agente.py`, `acciones.py`, `cerebro.py`,
`voz.py`, `midgaror.py`— viven en la raíz, como en bifrost (`bot.py`,
`utils/`). Esta carpeta es para lo que **automatiza un procedimiento**, con el
mismo nombre base que su `.md`.

## Antes de dar algo por bueno

`python3 scripts/verificar.py` **desde la raíz de midgaror**, que encadena
las pruebas y el lint de los tres repos. No hay otra verificación real
mientras la CI de la cuenta siga sin arrancar.
