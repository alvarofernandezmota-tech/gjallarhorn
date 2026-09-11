# gjallarhorn

Entrada por voz al diario de **midgaror**. El cuerno que se hace sonar.

> **Estado: recién creado, sin implementar.** Aquí solo hay estructura. La
> decisión que lo justifica es el **ADR-017 de midgaror**, aceptado el
> 2026-09-11.

## Qué es

Un proyecto aparte —no una parte de bifrost— para apuntar en el diario
**hablando** en vez de tecleando.

Hace una cosa: **audio → texto → el diario**. El último tramo no lo inventa:
usa el mismo contrato que ya usa el bot de Telegram, `escribir_entrada`
(ADR-009 de midgaror), para que siga habiendo **un solo camino de escritura**
al diario.

## Por qué no vive dentro de bifrost

bifrost es el bot de Telegram y está en producción escribiendo el diario.
Tres motivos, en orden de peso:

1. **Un fallo en la voz no puede dejar mudo al bot que ya funciona.** Colgarle
   transcripción —y más adelante un servidor HTTP— amplía su superficie justo
   donde menos conviene.
2. **Son dos entradas distintas al mismo sitio**, no una capa de la otra.
   Compartir destino no las hace el mismo programa.
3. **El ciclo de vida no coincide.** bifrost se toca poco y con miedo, porque
   escribe. La voz va a ser prueba y error durante semanas.

## El orden previsto

Aparte no significa empezar por lo caro.

| | Qué | Estado |
|---|---|---|
| 1 | **Transcripción local.** Audio → texto con Whisper o equivalente, sobre el hardware de casa. El audio del diario no sale de casa | sin empezar |
| 2 | **Telefonía.** Llamar y dictar, sin datos y sin desbloquear el móvil | **bloqueado**, ver abajo |

### Por qué el paso 2 está bloqueado

Un proveedor de telefonía trabaja con **webhooks entrantes**: llama a una URL
pública cuando entra la llamada. Y el ADR-015 de midgaror decidió, con su
motivo escrito, que **en el router no se abre nada**.

Que gjallarhorn sea un repo aparte **no resuelve eso**: el router es el mismo.
Hace falta un ADR que diga cómo entra ese webhook —relé en la nube, Tailscale
Funnel, u otra cosa— antes de escribir una línea de telefonía.

## Dos reglas que no se negocian

- **El audio no sale de casa.** La transcripción es local. Mandar el diario
  hablado a una API de terceros va en contra de todo lo decidido sobre dónde
  viven estos datos (ADR-016 de midgaror).
- **No se abre un segundo camino de escritura.** Todo entra por
  `escribir_entrada`. Es lo que hace que los arreglos del diario —el reloj
  único, el JSON legible— valgan aquí sin tocarlos.

## Estructura

```
gjallarhorn/
├─ AGENTS.md               # instrucciones para sesiones de IA
├─ CONTEXT.md              # propósito y decisiones de arquitectura
├─ README.md               # esto
├─ ruff.toml               # las mismas reglas de lint que midgaror y bifrost
├─ docs/
│  └─ procedimientos/      # un .md por procedimiento (ADR-004)
└─ scripts/                # un script por procedimiento, mismo nombre base
```

## Relación con el ecosistema

- Submódulo de **midgaror**, en `proyectos/`, igual que bifrost.
- Escribe por `bifrost_bridge.escribir_entrada` (ADR-009).
- Respeta `MIDGAROR_DATOS` (ADR-016) sin saber nada de él: eso lo resuelve
  midgaror.
