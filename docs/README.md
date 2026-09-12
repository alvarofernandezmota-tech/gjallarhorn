---
tipo: readme
fecha: 2026-09-12
repo: gjallarhorn
etiquetas: [indice, documentacion]
---

# Documentación de gjallarhorn

Sigue las convenciones de
[midgaror](https://github.com/alvarofernandezmota-tech/midgaror): todo `.md`
de `docs/` lleva frontmatter `tipo/fecha/repo`, y cada carpeta tiene su
índice. Los `.md` de la raíz **no** lo llevan, igual que allí.

## Dónde está cada cosa

Este repo es joven —nació el 2026-09-11— y la documentación no está repartida
en once carpetas porque no hay once carpetas de contenido. Lo que hay:

| Qué | Dónde | Por qué ahí |
|---|---|---|
| **Cómo se usa** | [`README.md`](../README.md) (raíz) | Es lo primero que lee quien llega |
| **Las reglas del dominio y las invariantes** | [`CLAUDE.md`](../CLAUDE.md) (raíz) | Lo que una sesión de IA necesita saber **antes** de tocar nada |
| **Reglas de trabajo en el repo** | [`AGENTS.md`](../AGENTS.md) (raíz) | Cómo se commitea, qué no se toca, cómo se verifica |
| **Las decisiones y sus porqués** | [`CONTEXT.md`](../CONTEXT.md) (raíz) | Nueve decisiones numeradas, con su contexto y su razón |
| **Qué ha ido cambiando** | [`CHANGELOG.md`](CHANGELOG.md) | Sacado del historial, no de la memoria |

## Lo que todavía no existe, y por qué

**No hay `docs/adr/`.** En midgaror las decisiones son un fichero por ADR
porque son diecinueve, de meses distintos y sobre sistemas distintos. Aquí son
nueve, de dos días, y viven numeradas en `CONTEXT.md`. Partirlas en nueve
ficheros sería ceremonia sin beneficio. **El día que una decisión de aquí
supere a otra** —y haya que dejar la vieja intacta con su nota de estado, que
es la regla de midgaror— entonces sí: se crea `docs/adr/` y se migran.

**No hay `docs/procedimientos/` ni `scripts/`.** Los hubo, vacíos, con un
índice que decía «vacío», y se quitaron el 2026-09-12. La convención sigue
escrita en `AGENTS.md` —`docs/procedimientos/algo.md` ↔ `scripts/algo.py`— y
las carpetas se crean el día que exista el primero. Una carpeta vacía no es
documentación pendiente: es sitio reservado para algo que no existe.

**No hay `docs/sesiones/`.** El registro de sesiones de midgaror es de
midgaror ([ADR-010](https://github.com/alvarofernandezmota-tech/midgaror/blob/main/docs/adr/010-sesiones-por-bloques.md));
aquí lo que hay que saber de cada día está en el CHANGELOG.

## Al añadir un `.md` aquí

1. Frontmatter obligatorio: `tipo`, `fecha`, `repo: gjallarhorn`.
2. Entra en la tabla de arriba en el **mismo commit**. Un documento que no
   está en el índice es un documento que nadie va a encontrar.
3. Si creas una carpeta, lleva su propio `README.md` índice.
