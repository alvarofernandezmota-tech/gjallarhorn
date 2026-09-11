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
`voz.py`, `avisos.py`, `fechas.py`, `almacen.py`— viven en la raíz, y también
los dos ejecutables que no automatizan un procedimiento sino que **son** el
producto: `servidor.py` y `medir_voz.py`. Esta carpeta es para lo otro.

## Antes de dar algo por bueno

```bash
python3 -m unittest discover -s tests
ruff check .
```

Desde la raíz del repo. No hay otra verificación real mientras la CI de la
cuenta siga sin arrancar.
