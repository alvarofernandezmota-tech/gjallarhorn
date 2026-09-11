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

Vacío: todavía no hay ningún script. El primero será el de la transcripción
local.

## Antes de dar algo por bueno

`python3 scripts/verificar.py` **desde la raíz de midgaror**, que encadena
las pruebas y el lint de los tres repos. No hay otra verificación real
mientras la CI de la cuenta siga sin arrancar.
