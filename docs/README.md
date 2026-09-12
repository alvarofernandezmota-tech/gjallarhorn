---
tipo: readme
fecha: 2026-09-12
repo: hugin
etiquetas: [indice, documentacion]
---

# Documentación de hugin

Sigue las convenciones de
[midgaror](https://github.com/alvarofernandezmota-tech/midgaror): los `.md` de
`docs/` llevan frontmatter `tipo/fecha/repo`; los de la raíz no.

## Dónde está cada cosa

| Qué | Dónde | Por qué ahí |
|---|---|---|
| **Cómo se usa y cómo se monta** | [`README.md`](../README.md) (raíz) | Lo primero que lee quien llega |
| **Las reglas del dominio y las invariantes** | [`CLAUDE.md`](../CLAUDE.md) (raíz) | Lo que hay que saber **antes** de tocar nada |
| **Qué ha ido cambiando** | [`CHANGELOG.md`](CHANGELOG.md) | Sacado del historial |

## Lo que no hay, y por qué

**No hay `CONTEXT.md` ni `docs/adr/`.** Las decisiones que dieron origen a
este repo no son suyas: son de gjallarhorn, que es quien decidió partirse. Están
en el [ADR-019 de midgaror](https://github.com/alvarofernandezmota-tech/midgaror/blob/main/docs/adr/019-cerebro-de-gjallarhorn-en-hugin.md),
y duplicarlas aquí crearía dos versiones de la misma decisión que se separan
con el tiempo. **El día que hugin tome una decisión propia** —un segundo
consumidor, un cambio de contrato— entonces sí.

**No hay `docs/procedimientos/` ni `scripts/`.** Una librería no se opera: no
se arranca, no se despliega, no se reinicia. No hay procedimiento que escribir.

## Al añadir un `.md` aquí

1. Frontmatter obligatorio: `tipo`, `fecha`, `repo: hugin`.
2. Entra en la tabla de arriba en el **mismo commit**.
