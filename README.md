# gjallarhorn

Un recepcionista telefónico: atiende la llamada, informa de tarifas y toma la
cita. **Proyecto independiente, sin dependencias de ningún otro repo.**

> **Estado: funciona de punta a punta por texto y por voz.** Falta la telefonía
> —que una llamada de verdad entre— y eso es lo único que puede tumbarlo.

## Qué hace

```
audio → voz.escuchar → recepcion.atender → voz.hablar → audio
                              ↓
                        avisos.registrar
```

Cuatro intenciones: **precio**, **cita**, **horario** y **recado**. Y una regla
por encima de todas:

> **Un precio sale de la tabla o no sale.** Nunca aproximado, nunca una
> horquilla. Si el servicio no está, dice que no lo sabe y toma el recado.
> Cantar un precio equivocado por teléfono cuesta dinero y credibilidad.

Eso no depende del modelo que se use: la consulta la resuelve una tabla, no un
generativo. Un LLM podrá redactar mejor la frase, **el número no lo pone él**.

## Independiente

Nada de esto importa otro repo. Lo que necesita, lo tiene:

| | |
|---|---|
| `fechas.py` | cuándo quiere la cita, **siempre hacia delante** |
| `almacen.py` | JSON con versión de esquema y escritura atómica |
| `voz.py` | Whisper y Piper, las dos **en local** |

Lo de `fechas.py` no es solo independencia: un parser de diario resuelve hacia
**atrás** —«el lunes» es el que pasó— y un recepcionista siempre mira hacia
delante. Nadie reserva cita para el martes pasado.

## Dar de alta un negocio: copiar una carpeta

```bash
cp -r negocios/peluqueria negocios/mi-negocio
```

Cambias `nombre` en `negocio.toml`, la tabla de `tarifas.md` y el texto de
`faq.md`. **No se toca código.** Quien lleva el negocio tiene que poder cambiar
un precio sin llamar a nadie, y eso solo es cierto si no hay que abrir un `.py`.

`negocio.toml` es opcional: una carpeta con los dos Markdown ya es un negocio.

```bash
python3 recepcion.py --negocio mi-negocio                        # por teclado
python3 recepcion.py --negocio mi-negocio --audio llamada.ogg --hablar
```

### El aviso de que es automático no se puede quitar

Puedes poner tu propio saludo. Si **no** dice que se habla con un sistema
automático, se le añade al cargarlo:

```
saludo = "Hola, ha llamado a la peluquería."
   ↓
"Hola, ha llamado a la peluquería. Le atiende un asistente automático."
```

No es un descuido que se pueda cometer editando un fichero de texto.

## La voz, de punta a punta

```
audio → Whisper → recepcion.atender → Piper → audio
```

Las dos **locales**, y por el mismo motivo: por ahí pasa lo que se le dice a un
cliente y lo que el cliente cuenta. Las dos detrás de una interfaz de una
función, para poder probar todo lo de encima sin descargar modelos de cientos
de megas.

En la máquina donde corra: `pip install faster-whisper piper-tts`. Los dos
**descargan su modelo la primera vez**, así que ese arranque es lento y necesita
salida a internet. Después ya no.

Si la síntesis revienta, **la llamada sigue registrada**. Perder la
contestación es malo; perder el rastro de que alguien llamó preguntando un
precio, peor.

## Estructura

```
gjallarhorn/
├─ recepcion.py            quién atiende: precio, cita, horario, recado
├─ negocio.py              un negocio = una carpeta
├─ conocimiento.py         tarifas y FAQ, sin RAG (y por qué)
├─ voz.py                  la oreja (Whisper) y la boca (Piper), las dos locales
├─ avisos.py               el rastro de las llamadas, ordenado
├─ fechas.py               cuándo quiere la cita, siempre hacia delante
├─ almacen.py              los JSON, con escritura atómica
├─ medir_voz.py            cuánto tarda en contestar, sin teléfono ni tarjeta
├─ negocios/peluqueria/    ejemplo copiable
└─ conocimiento/           en blanco a propósito
```

## Dónde guarda sus datos

- `GJALLARHORN_DATOS` para los avisos; `GJALLARHORN_CONOCIMIENTO` para las
  tarifas. Sin ellas, dentro del repo.
