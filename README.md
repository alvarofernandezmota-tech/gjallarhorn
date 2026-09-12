# hugin

El cerebro de un bot que atiende a gente: entiende lo que le dicen, decide
que contestar y guarda lo que hay que guardar. **No sabe por donde le
hablan.**

De los dos cuervos de Odin —Hugin, el pensamiento; Munin, la memoria— este
es el que piensa.

## Que hay aqui

| Paquete | Para que es |
|---|---|
| `mente/` | Entender y decidir: reglas, buscador del conocimiento, LLM opcional, memoria de quien llama |
| `negocio/` | De que negocio se habla: sus datos, sus frases y su agenda |
| `guardado/` | Donde se escribe y como: ajustes, almacen, avisos, copias |

## Que **no** hay

Ni un solo import de un canal. Una llamada de telefono, un chat o una
ventana web son la misma conversacion vista por sitios distintos, y aqui
entra texto y sale texto. El dia que un modulo de este repo necesite saber
que hay un telefono al otro lado, el corte esta mal hecho: lo que se mueve
es la decision, no el import.

Eso no es un buen proposito, es una prueba: `tests/test_libreria.py` lee
el arbol de sintaxis de cada modulo y se cae si aparece uno.

## Como se usa

**El repositorio es el paquete.** La carpeta se llama `hugin` y lo que hay
que tener en el `sys.path` es la carpeta que la contiene. Montado como
submodulo en la raiz de la aplicacion, los imports salen solos:

```python
from hugin.mente import recepcion
from hugin.negocio import negocio as negocios
```

Para engancharlo:

```bash
git submodule add https://github.com/alvarofernandezmota-tech/hugin.git hugin
```

Y en un clon que ya lo tenga:

```bash
git submodule update --init --recursive
```

## Comprobarlo

```bash
make pruebas        # 349 pruebas y el lint
```

Solo Python de la biblioteca estandar. `anthropic` es opcional y solo para
el LLM: sin la libreria y sin clave, el cerebro tira de reglas y lo dice.

## Configuracion

Se lee del entorno, y `guardado/ajustes.py` carga el `.env` del
**directorio de trabajo** —el de la aplicacion que despliega, no el de esta
libreria—. Se puede decir a mano con `GJALLARHORN_ENV`.

| Variable | Para que |
|---|---|
| `GJALLARHORN_NEGOCIOS` | carpeta con los negocios dados de alta |
| `GJALLARHORN_DATOS` | donde se escriben agenda, avisos y memoria |
| `GJALLARHORN_CONOCIMIENTO` | carpeta del conocimiento del negocio |
| `GJALLARHORN_LLM` / `GJALLARHORN_LLM_MODELO` | que modelo se usa, si se usa |
| `ANTHROPIC_API_KEY` | clave del LLM; sin ella se va con reglas |

El prefijo `GJALLARHORN_` es herencia de la unica aplicacion que usa esto
hoy. Se queda tal cual mientras siga siendo la unica: renombrarlo obliga a
tocar el `.env` y las unidades de systemd de un bot que esta funcionando, y
eso se hace cuando haya una segunda aplicacion, no antes.

## De donde sale

Esto vivia dentro de
[gjallarhorn](https://github.com/alvarofernandezmota-tech/gjallarhorn) y se
saco de ahi en el commit `cf000df`. La historia anterior de estos ficheros
esta en aquel repositorio.
