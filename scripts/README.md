---
tipo: readme
fecha: 2026-09-11
repo: gjallarhorn
---

# Scripts

Un script por procedimiento, con el **mismo nombre base** que su `.md` en
[`docs/procedimientos/`](../docs/procedimientos/README.md) — la regla de la
casa: `algo.md` ↔ `algo.py`. Así, quien lee el procedimiento sabe sin buscar
dónde está el código que lo ejecuta.

## Índice

Vacío todavía.

Los **módulos de librería** —`recepcion.py`, `negocio.py`, `conocimiento.py`,
`frases.py`, `agenda.py`, `voz.py`, `avisos.py`, `avisar.py`, `fechas.py`,
`almacen.py`— viven en la raíz, y también lo que no automatiza un
procedimiento sino que **es** el producto o su operación: `servidor.py`,
`medir_voz.py`, `diagnostico.py` y el `Makefile`. Esta carpeta es para lo otro.

## Antes de dar algo por bueno

```bash
make pruebas
```

Desde la raíz del repo. No hay otra verificación real mientras la CI de la
cuenta siga sin arrancar.
