# Instrucciones para agentes IA

## Lo primero: este repo es PÚBLICO

Comprobado contra la API el 2026-09-11: `private: false`. Nada de lo que se
escriba aquí puede llevar **IPs, nombres de host con dirección, rutas a
claves, tokens ni contenido de los repos privados**. Si hace falta un ejemplo
de dirección, va un marcador (`IP_DE_TU_MAQUINA`), no la de verdad.

Ya ha pasado una vez en la cuenta: una clave de OpenRouter vivió meses en el
historial público de `ai-toolkit`. Quitarla del árbol no la quita del
historial.

## Qué es gjallarhorn

Entrada por voz al diario de midgaror: **audio → texto → el diario**. Proyecto
aparte de bifrost, decidido en el ADR-017 de midgaror el 2026-09-11.

Por qué aparte y no dentro del bot, cómo escribe, y por qué la telefonía está
bloqueada: [`README.md`](README.md) y [`CONTEXT.md`](CONTEXT.md).

## Estado actual

✅ **El agente funciona de punta a punta**: `agente.py` toma audio (o texto),
decide qué acción toca y la ejecuta contra el diario de midgaror. 43 pruebas,
`ruff` limpio.

⚠️ Dos cosas que **no** están hechas, y conviene no leerlas al revés:
- El **modelo de Whisper no está instalado** aquí: `voz.Whisper` está escrito y
  probado en su interfaz, pero nadie ha transcrito audio de verdad todavía. Eso
  se hace en la máquina donde corra el agente.
- El **cerebro es de reglas**, no un LLM (ver `cerebro.py`). Elegir modelo es
  la decisión pendiente del ADR-018, y se decide midiendo contra estas reglas.

❌ La telefonía **no se toca** hasta que exista un ADR en midgaror que resuelva
cómo entra un webhook sin contradecir el ADR-015 («en el router no se abre
nada»).

## Reglas que vienen de midgaror y valen aquí

- **Un solo camino de escritura al diario**: `bifrost_bridge.escribir_entrada`
  (ADR-009). No se abre otro, ni «solo para probar».
- **El audio no sale de casa.** Transcripción local. El audio original no se
  guarda salvo decisión explícita, y el `.gitignore` ya lo excluye.
- **Procedimiento ↔ script con el mismo nombre base** (ADR-004):
  `docs/procedimientos/transcribir.md` ↔ `scripts/transcribir.py`.
- **Frontmatter** `tipo/fecha/repo` en todo `.md` de `docs/`, con
  `repo: gjallarhorn`. El estándar está en midgaror,
  `docs/estandares/frontmatter.md`.
- **Commits**: `tipo: descripción breve en presente` (feat, fix, docs, chore,
  refactor, test). Un commit por cambio lógico.
- **Trabajo no trivial**: rama corta y PR en borrador.

## Verificación

```bash
MIDGAROR_RAIZ=/ruta/a/midgaror python3 -m unittest discover -s tests
ruff check .
```

Cuando gjallarhorn sea submódulo, esto se encadena en **`python3
scripts/verificar.py`** desde la raíz de midgaror, que es la verificación real.
Hasta entonces se corre a mano, y **una comprobación saltada no es una
comprobación pasada**.

La CI de la cuenta **no arranca** desde el 2026-09-04 por un cobro rechazado.
Un check en rojo en GitHub no dice nada del código: sale en segundos, sin
runner y con los logs en 404. El detalle está en `docs/infra/estado-ci.md` de
midgaror.

## Lo que NO hay que hacer aquí

- Escribir en el diario por un camino que no sea `escribir_entrada`.
- Mandar audio a una API de terceros, por cómodo que sea.
- Empezar la telefonía antes de que exista su ADR.
- Dar por bueno nada sin correr `verificar.py` desde midgaror.
