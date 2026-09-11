# Contexto y decisiones de arquitectura

## Propósito

gjallarhorn convierte voz en entradas del diario de midgaror.

## Decisiones

### 1. Proyecto aparte, no una fase de bifrost

**Decisión**: repo propio y submódulo de midgaror, como bifrost.

**Razón**: bifrost está en producción escribiendo el diario. La voz es otro
oficio, con otro ciclo de vida —prueba y error durante semanas frente a un
bot que se toca poco y con miedo—, y un fallo aquí no puede dejarlo mudo.

Decidido por Álvaro el 2026-09-11 (ADR-017 de midgaror). La propuesta
anterior era meter la transcripción dentro de bifrost y crear este repo solo
si no bastaba; quedó descartada.

### 2. Un solo camino de escritura al diario

**Decisión**: se escribe por `bifrost_bridge.escribir_entrada` (ADR-009 de
midgaror). No se abre otro.

**Razón**: es lo que mantiene `organizar_diario.py` como único sitio por el
que entra texto en el diario. Cada arreglo que se haga allí vale aquí sin
tocar nada.

### 3. La transcripción es local

**Decisión**: el audio se transcribe en el servidor de casa. No se manda a
una API de terceros.

**Razón**: es el diario personal. Sacarlo de casa contradice lo decidido en
el ADR-016 sobre dónde viven estos datos. El audio original no se guarda
salvo decisión explícita: es dato personal y pesa.

### 4. La telefonía no se empieza sin su ADR

**Decisión**: nada de telefonía hasta que exista un ADR que resuelva cómo
entra un webhook sin contradecir el ADR-015.

**Razón**: el ADR-015 decidió que en el router no se abre nada. Separar este
repo no cambia el router. Las salidas plausibles —un relé en la nube, o
Tailscale Funnel— modifican esa decisión, y eso se escribe antes, no después.

## Relación con midgaror

- Submódulo en `proyectos/`, igual que bifrost.
- Necesita el `diario/` de midgaror disponible para importarlo.
- Respeta `MIDGAROR_DATOS` (ADR-016) sin saber nada de él.

## Estado actual

✅ **El agente funciona**: audio (o texto) → cerebro → acción → una frase. 43
pruebas contra los módulos reales de midgaror, con las rutas en temporales.

Pendiente: instalar Whisper en la máquina donde corra, y decidir si el cerebro
de reglas se sustituye por un LLM (ADR-018).
