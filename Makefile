# Operar gjallarhorn con un comando. `make` a secas lista lo que hay.
#
# Todo pasa por el .venv del repo: en Arch y Debian el pip del sistema esta
# bloqueado (externally-managed) y un `pip install` a pelo acaba donde el
# interprete que falla no mira. Es la causa numero uno de «lo instale y dice
# que falta», y esto la quita de en medio.

VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
NEGOCIO ?= peluqueria
# Dos puertos, y la diferencia importa: el de la demo NO se publica nunca
# —sirve la pagina, /hablar y /colgar—; el del telefono sirve solo el webhook
# del proveedor y es el unico que sale a internet.
PUERTO  ?= 8080
PUERTO_TELEFONO ?= 8081
SERVICIO := gjallarhorn
UNIDAD   := $(HOME)/.config/systemd/user/$(SERVICIO).service

.DEFAULT_GOAL := ayuda

ayuda:  ## esta lista
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## */\t/' | column -t -s "$$(printf '\t')"

$(PY):
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip >/dev/null
	@# ruff es el lint del repo: sin el, `make pruebas` moria con un
	@# "command not found" en un clon recien hecho. Si no hay red, se avisa
	@# y se sigue: las pruebas no lo necesitan.
	@$(PIP) install ruff >/dev/null 2>&1 || \
	  echo "⚠️  no he podido instalar ruff (¿sin red?). Las pruebas van igual."

instalar: $(PY)  ## venv + dependencias + modelos de voz, de una vez
	$(PIP) install faster-whisper piper-tts anthropic
	$(PY) -m telefono.voz

nuevo:  ## dar de alta otro negocio: make nuevo NEGOCIO=mi-negocio
	@test -n "$(NEGOCIO)" -a "$(NEGOCIO)" != peluqueria || { echo "❌ di el nombre: make nuevo NEGOCIO=mi-negocio"; exit 1; }
	@test ! -e negocios/$(NEGOCIO) || { echo "❌ negocios/$(NEGOCIO) ya existe"; exit 1; }
	cp -r negocios/peluqueria negocios/$(NEGOCIO)
	@echo "→ negocios/$(NEGOCIO)/: edita negocio.toml (nombre, saludo, horario), tarifas.md y faq.md."
	@echo "  Arrancar con el:  make servidor NEGOCIO=$(NEGOCIO)   o   make arrancar NEGOCIO=$(NEGOCIO)"

voz: $(PY)  ## ¿oye y habla esta maquina? versiones y milisegundos
	$(PY) -m telefono.voz

MODELO  ?= small

medir: $(PY)  ## cuanto tarda en contestar. Prueba MODELO=base y MODELO=tiny
	$(PY) -m dueno.medir_voz --negocio $(NEGOCIO) --modelo $(MODELO)

probar: $(PY)  ## el recepcionista por teclado, con memoria y agenda
	$(PY) -m telefono.demo --negocio $(NEGOCIO)

servidor: $(PY)  ## el MVP en primer plano (Ctrl+C para parar)
	$(PY) -m telefono.servidor --negocio $(NEGOCIO) --puerto $(PUERTO) --puerto-telefono $(PUERTO_TELEFONO)

serve: $(PY)  ## la demo, visible solo en tu tailnet (para el movil)
	tailscale serve --bg $(PUERTO)
	@tailscale serve status

cerebro: $(PY)  ## ¿que entiende el LLM de una frase? (FRASE="...")
	$(PY) -m hugin.mente.cerebro "$(FRASE)" --negocio $(NEGOCIO)

buscar: $(PY)  ## ¿que encuentra en el conocimiento? (FRASE="...")
	$(PY) -m hugin.mente.rag "$(FRASE)" --negocio $(NEGOCIO)

panel: $(PY)  ## el dia del dueño en la terminal (en el movil: /panel)
	$(PY) -m dueno.panel --negocio $(NEGOCIO)

aprender: $(PY)  ## que te preguntan y no supo contestar
	$(PY) -m dueno.aprender --negocio $(NEGOCIO)

frases: $(PY)  ## todo lo que dice tu bot, y si trata de tu o de usted
	$(PY) -m hugin.negocio.frases --negocio $(NEGOCIO)

lanzar: $(PY)  ## de aqui a la primera llamada, paso a paso
	@$(PY) -m dueno.lanzar --negocio $(NEGOCIO) --puerto $(PUERTO_TELEFONO)

revisar: $(PY)  ## ¿esta el bot listo para coger llamadas? (sale 1 si no)
	$(PY) -m dueno.revisar --negocio $(NEGOCIO)

copia: $(PY)  ## copia de hoy de las citas, los clientes y los avisos
	$(PY) -m hugin.guardado.copias --negocio $(NEGOCIO)

copias: $(PY)  ## que copias hay guardadas
	$(PY) -m hugin.guardado.copias --negocio $(NEGOCIO) --listar

agentes: $(PY)  ## lo que trabaja fuera de la llamada: recordatorios, resumen, revision
	$(PY) -m dueno.agentes --negocio $(NEGOCIO)

agentes-seco: $(PY)  ## lo mismo, pero solo enseñarlo: no registra ningun aviso
	$(PY) -m dueno.agentes --negocio $(NEGOCIO) --seco

agentes-diarios: $(AGENTES) $(AGENTES_TIMER)  ## que corran solos cada mañana a las 8
	systemctl --user enable --now gjallarhorn-agentes.timer
	@echo "→ cada mañana a las 8:00: los agentes dejan sus avisos y se mandan al movil."
	@echo "  Ver: systemctl --user list-timers | grep agentes"

sin-agentes-diarios:  ## dejar de correrlos solos
	systemctl --user disable --now gjallarhorn-agentes.timer 2>/dev/null || true

clientes: $(PY)  ## las fichas de quien ha llamado (esto SI lleva nombres)
	$(PY) -m hugin.mente.memoria

olvidar: $(PY)  ## borrar la ficha de un numero: make olvidar TELEFONO=+34600...
	@test -n "$(TELEFONO)" || { echo "Falta el numero: make olvidar TELEFONO=+34600000000"; exit 1; }
	$(PY) -m hugin.mente.memoria --olvidar "$(TELEFONO)"

funnel: $(PY)  ## publicar SOLO el webhook del telefono en internet
	@$(PY) -c "import telefonia, sys; c = telefonia.configuracion(); \
	  sys.exit(0 if c and telefonia.proveedores(c) else 1)" || \
	  { echo "❌ sin nada valido en .env con que comprobar la firma no hay webhook que publicar."; \
	    echo "   Publicar esto ahora solo abriria la demo a internet. Mira «make revisar»."; \
	    exit 1; }
	tailscale funnel --bg $(PUERTO_TELEFONO)
	@echo
	@echo "Se ha publicado el puerto $(PUERTO_TELEFONO), que sirve SOLO /telefono/*."
	@echo "El $(PUERTO) (la pagina, /hablar, /colgar) sigue sin salir de tu tailnet."
	@echo
	@$(PY) -m telefono.urlpublica --para-el-proveedor

sin-funnel:  ## dejar de publicar: nada sale a internet
	tailscale funnel --https=443 off
	@tailscale funnel status 2>/dev/null || true

avisar: $(PY)  ## mandar al movil los avisos pendientes (Telegram)
	$(PY) -m dueno.avisar

telefono-prueba: $(PY)  ## una llamada por teclado, como la veria el proveedor
	$(PY) -m telefono.telefonia --simular --negocio $(NEGOCIO) --puerto $(PUERTO_TELEFONO)

telegram-prueba: $(PY)  ## ¿llega un mensaje al movil? comprueba token y chat
	$(PY) -m dueno.avisar --prueba

pruebas: $(PY)  ## las pruebas (las de aqui y las de hugin) y el lint
	$(PY) -m unittest discover -s tests
	@# El cerebro vive en el submodulo hugin y tiene su propia suite.
	@# Sin ella, «make pruebas» pasa en verde con el cerebro roto: aqui
	@# ya no queda ni una prueba de fechas, de agenda ni de reglas.
	@if [ -f hugin/tests/entorno.py ]; then \
	   cd hugin && python3 -m unittest discover -s tests; \
	 else echo "❌ hugin/ está vacío: el submódulo no está inicializado y"; \
	      echo "   sus pruebas NO se han corrido.  git submodule update --init"; \
	      exit 1; fi
	@# Una comprobacion saltada NO es una comprobacion pasada: si no hay
	@# ruff se dice con todas las letras en vez de morir con un
	@# "command not found" que parece que el codigo esta mal.
	@if [ -x $(VENV)/bin/ruff ]; then $(VENV)/bin/ruff check .; \
	 elif command -v ruff >/dev/null 2>&1; then ruff check .; \
	 else echo "⚠️  SIN RUFF: las pruebas han pasado pero el lint NO se ha corrido."; \
	      echo "   Para tenerlo:  .venv/bin/pip install ruff"; fi

# ---- como servicio: arranca con la maquina, se reinicia si cae, con log ----

$(UNIDAD): gjallarhorn.service.in
	mkdir -p $(dir $(UNIDAD))
	sed -e 's|@RAIZ@|$(CURDIR)|g' -e 's|@NEGOCIO@|$(NEGOCIO)|g' -e 's|@PUERTO@|$(PUERTO)|g' \
	    -e 's|@PUERTO_TELEFONO@|$(PUERTO_TELEFONO)|g' \
	    gjallarhorn.service.in > $(UNIDAD)
	systemctl --user daemon-reload

arrancar: $(PY) $(UNIDAD)  ## servicio systemd: siempre encendido, se reinicia si cae
	systemctl --user enable --now $(SERVICIO)
	@echo "→ http://localhost:$(PUERTO)   (log: make log)"
	@loginctl show-user $$USER 2>/dev/null | grep -q 'Linger=yes' || \
	  echo "⚠️  para que arranque sin que inicies sesion:  sudo loginctl enable-linger $$USER"

TIMER := $(HOME)/.config/systemd/user/gjallarhorn-actualizar.timer
ACTUALIZAR := $(HOME)/.config/systemd/user/gjallarhorn-actualizar.service

AGENTES       := $(HOME)/.config/systemd/user/gjallarhorn-agentes.service
AGENTES_TIMER := $(HOME)/.config/systemd/user/gjallarhorn-agentes.timer

$(AGENTES): gjallarhorn-agentes.service.in
	mkdir -p $(dir $(AGENTES))
	sed -e 's|@RAIZ@|$(CURDIR)|g' -e 's|@PYTHON@|$(PY)|g' -e 's|@NEGOCIO@|$(NEGOCIO)|g' \
		gjallarhorn-agentes.service.in > $(AGENTES)
	systemctl --user daemon-reload

$(AGENTES_TIMER): gjallarhorn-agentes.timer.in
	mkdir -p $(dir $(AGENTES_TIMER))
	cp gjallarhorn-agentes.timer.in $(AGENTES_TIMER)
	systemctl --user daemon-reload

$(ACTUALIZAR): gjallarhorn-actualizar.service.in
	mkdir -p $(dir $(ACTUALIZAR))
	sed -e 's|@RAIZ@|$(CURDIR)|g' gjallarhorn-actualizar.service.in > $(ACTUALIZAR)
	systemctl --user daemon-reload

$(TIMER): gjallarhorn-actualizar.timer.in
	mkdir -p $(dir $(TIMER))
	cp gjallarhorn-actualizar.timer.in $(TIMER)
	systemctl --user daemon-reload

auto: $(ACTUALIZAR) $(TIMER)  ## que Madre se actualice sola: git pull cada 5 min y reinicia si cambio
	systemctl --user enable --now gjallarhorn-actualizar.timer
	@echo "→ cada 5 minutos: git pull --ff-only; si hay commits nuevos, make reiniciar."
	@echo "  Con esto, fusionar en GitHub basta. Ver: systemctl --user list-timers"

sin-auto:  ## dejar de actualizar sola
	systemctl --user disable --now gjallarhorn-actualizar.timer 2>/dev/null || true

parar:  ## parar el servicio
	systemctl --user disable --now $(SERVICIO) 2>/dev/null || true

# Depende de la unidad a proposito: un `git pull` puede traer una plantilla
# nueva —puertos, argumentos— y reiniciar sin regenerarla deja el servicio
# arrancando con los argumentos viejos, sin decirlo. Make ya sabe si hay que
# rehacerla: si no ha cambiado, esto no hace nada.
reiniciar: $(UNIDAD)  ## tras un git pull o editar el negocio
	systemctl --user restart $(SERVICIO)

log:  ## el log del servicio, en vivo
	journalctl --user -u $(SERVICIO) -f -n 50

estado: $(PY)  ## ¿vivo? ¿que modelo? ultimas citas y avisos
	@systemctl --user is-active $(SERVICIO) >/dev/null 2>&1 && echo "servicio: activo" || echo "servicio: parado"
	@test -f $(UNIDAD) -a gjallarhorn.service.in -nt $(UNIDAD) && \
	  echo "⚠️  la unidad de systemd se quedo atras: make reiniciar" || true
	@$(PY) -m dueno.diagnostico --corto

diagnostico: $(PY)  ## el informe entero, para pegarlo de una vez
	@$(PY) -m dueno.diagnostico

.PHONY: ayuda nuevo instalar voz medir probar servidor serve pruebas cerebro telefono-prueba funnel sin-funnel auto sin-auto avisar telegram-prueba arrancar parar reiniciar log estado diagnostico
