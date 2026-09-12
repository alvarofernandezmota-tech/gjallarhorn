# Tarifas

<!--
  ESTE ES EL FICHERO QUE LEE EL AGENTE. De aquí, y solo de aquí, salen los
  precios que le dice a quien llama: exactamente lo que ponga en la tabla,
  ni un céntimo más ni menos. Lo que no esté aquí, no lo sabe y lo dice.

  Para cambiar un precio: edita la fila y reinicia el servidor. Para añadir un
  servicio: una fila más. Sin tocar código.

  LA COLUMNA DURACIÓN ES LO QUE OCUPA EN LA AGENDA, no el plazo de entrega.
  El agente la dice («unos 90 min») y, sobre todo, la usa para reservar: con
  ella comprueba que el hueco existe. Es opcional.

  Poner ahí un plazo —«48 h», pensando en cuánto se tarda en tener listo un
  encargo— hace que el bot intente reservar una cita de cuarenta y ocho
  horas. No cabe en ningún horario, y **todas las reservas acaban en "no me
  queda ningún hueco"** sin que nada apunte a la tabla. Pasó el 2026-09-12 y
  costó tres conversaciones enteras verlo. Desde entonces «make revisar» lo
  caza y lo dice. Los plazos de entrega van en faq.md.

  NOMBRES CORTOS, Y NO ES COSMÉTICO. El agente cuenta cuántas palabras
  comparte lo que dice el cliente con el nombre del servicio, y pide pasar de
  la mitad. Un nombre largo obliga a acertar más palabras:

      «Tarta personalizada mediana, 12 raciones»  → 4 palabras: hacen falta 3,
          y nadie dice eso por teléfono
      «Tarta mediana»                             → 2 palabras: con decir
          «tarta mediana» ya entra

  Medido el 2026-09-12 en una pastelería de prueba: con los nombres largos,
  «quiero encargar unos cupcakes» no encontraba los cupcakes. Acortando la
  tabla se arregló solo, sin tocar código.

  Escribe el nombre **como lo diría un cliente**, no como lo pondrías en un
  catálogo. Los detalles —raciones, qué incluye— van en faq.md.

  Este bloque de ayuda no lo lee nadie: puedes borrarlo.
-->

| Servicio | Precio | Duración |
|---|---|---|
| Corte de caballero | 14 € | 30 min |
| Corte de señora | 20 € | 45 min |
| Lavar y peinar | 15 € | 30 min |
| Tinte | 45 € | 90 min |
| Mechas | 65 € | 120 min |
| Corte y tinte | 60 € | 120 min |
| Recogido | 40 € | 60 min |
| Tratamiento de keratina | 80 € | 120 min |
| Corte infantil | 10 € | 20 min |
