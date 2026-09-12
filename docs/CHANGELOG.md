---
tipo: changelog
fecha: 2026-09-12
repo: hugin
etiquetas: [cambios, historial]
---

# Cambios

El repo nació el **2026-09-12**, sacado de
[gjallarhorn](https://github.com/alvarofernandezmota-tech/gjallarhorn). La
historia anterior de estos ficheros está allí: 109 commits del 2026-09-11.

Sin versiones numeradas todavía: no hay nada desplegado de cara al público.

---

## 2026-09-12 — el corte

### Nace el repo

`mente/`, `negocio/` y `guardado/` salen de gjallarhorn. El corte estaba
**medido, no supuesto**: los tres paquetes solo se importaban entre ellos.

Antes hubo que romper dos dependencias que iban al revés sin que nadie lo
hubiera decidido: `recepcion.py` importaba `telefono/voz.py` por su `main()`
de pruebas, y `cerebro.py` importaba `dueno/avisar.py` entero solo para
preguntar si había una clave de LLM puesta.

### Las carpetas de la aplicación no salen de `__file__`

**El fallo que casi se cuela.** `Path(__file__).parent.parent / "datos"`
apuntaba a la raíz del repo mientras esto vivía dentro de la aplicación.
Sacado a librería apunta **aquí dentro**: la agenda, el conocimiento y los
negocios se habrían escrito dentro del submódulo —datos de clientes en una
carpeta que no es de nadie— y el bot habría seguido diciendo que no hay citas.

Los tres se resuelven desde el directorio de trabajo. La prueba que lo sujeta
lee el árbol de sintaxis y no el texto: los comentarios de aquí **explican**
por qué no se usa `__file__`, y buscando la cadena a pelo saltaría la propia
documentación de la regla.

### `apuntar_nota()` no tenía ni una prueba

La escribe el dueño, no el cliente, así que ninguna conversación la
ejercitaba. En una auditoría salía como función muerta; no lo está, estaba
sin red. Seis pruebas.

### Dos preguntas que se contestaban mal con toda seguridad

Salieron metiendo llamadas de verdad en lote, no leyendo código.

**«¿Cuánto tarda un corte?» decía «no tengo ese servicio»**, teniendo cuatro.
Una sola palabra: «cuesta» es palabra vacía y se tira, «tarda» no, así que
`buscar()` exigía encontrar «tarda» en el nombre del servicio. Los verbos de
duración pasan a ser relleno.

**«¿Se puede ir sin cita?» contestaba la política de anulación.** Medido: la
pregunta son tres palabras —ir (idf 1.99), sin (1.48), cita (0.69)— y el
título equivocado comparte las dos que más pesan. El título bueno, «¿Hace
falta cita?», se queda en una palabra al quitar las vacías y pesa un 75%.

Lo que las separa es que **«sin cita» sale tal cual, palabra tras palabra**.
Se añadió la señal de pares consecutivos: 0.30 → 0.47, y adelanta a la mala
(0.43). Todavía no gana por el margen que exige `VENTAJA`, así que toma recado
en vez de contestar otra cosa —que ya es mejor— pero el orden es el correcto.

---

### «Quiero encargar una tarta» no encontraba ninguna tarta

La frase con la que empieza casi cualquier llamada de encargo. Medido, y la
causa es de fondo: **`buscar()` intersecta** — exige que cada palabra
significativa esté en el nombre del servicio, así que una sola que no esté en
ninguno vacía el resultado entero.

```
'tarta'                → 4 servicios
'encargar una tarta'   → 0            ← un verbo de más
```

Parcheado metiendo los verbos de encargar en la lista de relleno. **Es la
segunda vez hoy que se arregla el mismo síntoma** —la primera fue con
«tarda»— y eso ya dice lo que hay: mientras `buscar()` intersecte, la lista de
palabras vacías nunca va a estar completa.

---

## Lo que se sabe que falta

### El umbral del 50 % de `buscar()`, y por qué no se toca

> **Corrección del 2026-09-12.** Antes aquí ponía que `buscar()` «intersecta»
> y «exige que cada palabra esté en el nombre del servicio». **Es falso**, y
> se escribió sin haber leído la función. Lo que hace es medir cobertura por
> los dos lados —lo preguntado cubierto por el servicio, o al revés— y pedir
> que alguno pase del 50 %.

El problema real es más fino: los casos que fallan caen **exactamente en
0.50**, rechazados por un pelo.

```
«quiero encargar unos cupcakes»
    {unos, cupcakes} vs {cupcakes, decorados, docena}
    max(1/2, 1/3) = 0.50  → fuera

«¿cuántas raciones tiene la mediana?»
    2 de 4 por los dos lados = 0.50  → fuera
```

Y **el umbral no se puede bajar**: el caso que justifica la regla —«cambio de
parabrisas» contra «Cambio de aceite», que le cantaba a un cliente el precio
de un servicio que no existe— da 0.50 también, y tiene que seguir fuera.

Se probó quitar de en medio las palabras que inflan la cuenta («unos»,
«cuántas», «tiene»). **Arregló dos casos y rompió uno que funcionaba**: «¿con
cuánta antelación hay que encargar?» se quedaba sin palabras suficientes y
pasaba a recado. Se revirtió.

Lo que queda claro y sirve para la próxima vez: **nombres de servicio cortos
funcionan mucho mejor con esta regla**. «Cupcakes decorados, docena» son tres
palabras y hace falta acertar dos para pasar del 50 %; «Cupcakes» sola
bastaría con una. Antes de tocar el umbral, mirar los nombres de la tabla.

### La FAQ que nombra el catálogo entero gana a la tabla

«Quiero encargar unos cupcakes» y «¿cuántas raciones tiene la mediana?» se
llevan la respuesta de la antelación, porque su cuerpo nombra tartas,
galletas, cupcakes, bombones y mesas dulces. Es exactamente el riesgo del que
avisa el comentario de `PESO_TITULO`, visto desde el otro lado: allí el
peligro era que un bloque que nombra medio catálogo se llevara las preguntas
de precio; aquí se las lleva igual porque el peso del título no basta cuando
el título se queda en una palabra.


- **«¿Tenéis algo sin gluten?» abre una cita.** «tenéis algo» está en el
  intento de disponibilidad. El arreglo se intentó, **rompió una prueba
  legítima** («¿tenéis algo el jueves por la mañana?» sí es disponibilidad) y
  se revirtió. Necesita un arreglo mejor pensado.
- «¿Se puede ir sin cita?» ordena bien pero no supera el margen de `VENTAJA`.
- No hay `LICENSE` ni `SECURITY.md`.
