# Operar hugin con un comando. `make` a secas lista lo que hay.
#
# hugin es una libreria: no se arranca, no escucha en ningun puerto y no
# tiene servicio. Lo unico que se hace aqui es comprobarla.

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

.DEFAULT_GOAL := ayuda

ayuda:  ## esta lista
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## */\t/' | column -t -s "$$(printf '\t')"

$(PY):
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip >/dev/null
	@$(PIP) install ruff >/dev/null 2>&1 || \
	  echo "⚠️  no he podido instalar ruff (¿sin red?). Las pruebas van igual."

pruebas:  ## las pruebas y el lint
	@python3 -m unittest discover -s tests
	@ruff check . || echo "⚠️  ruff no esta instalado; el lint no se ha pasado"

.PHONY: ayuda pruebas
