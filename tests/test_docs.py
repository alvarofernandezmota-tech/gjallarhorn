"""Que la documentación siga las convenciones, comprobado en cada `make pruebas`.

Esto en midgaror es un script (`validar-frontmatter.py`, `auditoria-repo.py`)
porque allí el contenido **es** documentación y no hay suite que lo sujete.
Aquí el contenido es código, así que va donde va todo lo demás: en las
pruebas. La diferencia no es de estilo.

Un script se corre cuando alguien se acuerda. El 2026-09-12 se descubrió que
`verificar.py` de midgaror **no encadenaba** `actualizar-agents-context.py`, y
por eso el ADR-017 y el ADR-019 pasaron sin quedar registrados en el mapa del
repo. Los dos días salió «todo en verde».

Una prueba no se puede olvidar de correr.
"""

import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: E402,F401

# Los `.md` de la RAÍZ no llevan frontmatter y los de `docs/` lo llevan todos.
# No es un capricho: es lo que hace midgaror, medido el 2026-09-12 contra su
# propio árbol, y estos repos siguen sus convenciones.
OBLIGATORIOS = ("tipo", "fecha", "repo")
TIPOS = ("readme", "changelog", "decision", "procedimiento", "estandar",
         "auditoria", "infra", "issue", "plantilla", "ecosistema", "sesion")


def docs() -> list[Path]:
    return sorted((RAIZ / "docs").rglob("*.md"))


def frontmatter(fichero: Path) -> dict[str, str] | None:
    """El bloque YAML de cabecera, o None si no lo tiene."""
    texto = fichero.read_text(encoding="utf-8")
    if not texto.startswith("---\n"):
        return None
    fin = texto.find("\n---\n", 4)
    if fin == -1:
        return None
    campos = {}
    for linea in texto[4:fin].splitlines():
        if ":" in linea and not linea.startswith(" "):
            clave, valor = linea.split(":", 1)
            campos[clave.strip()] = valor.strip()
    return campos


class TestFrontmatter(unittest.TestCase):
    def test_todo_md_de_docs_lo_lleva(self):
        for fichero in docs():
            with self.subTest(fichero=fichero.name):
                self.assertIsNotNone(
                    frontmatter(fichero),
                    f"docs/{fichero.relative_to(RAIZ / 'docs')} sin frontmatter")

    def test_con_los_tres_campos_obligatorios(self):
        for fichero in docs():
            campos = frontmatter(fichero) or {}
            for campo in OBLIGATORIOS:
                with self.subTest(fichero=fichero.name, campo=campo):
                    self.assertIn(campo, campos)

    def test_el_repo_es_este(self):
        # Copiar un documento de otro repo y dejarle su `repo:` es el error
        # fácil, y hace que el indexado lo cuelgue del sitio equivocado.
        for fichero in docs():
            campos = frontmatter(fichero) or {}
            with self.subTest(fichero=fichero.name):
                self.assertEqual(campos.get("repo"), "gjallarhorn")

    def test_la_fecha_tiene_forma_de_fecha(self):
        for fichero in docs():
            campos = frontmatter(fichero) or {}
            with self.subTest(fichero=fichero.name):
                self.assertRegex(campos.get("fecha", ""), r"^\d{4}-\d{2}-\d{2}$")

    def test_el_tipo_es_uno_de_los_de_la_casa(self):
        for fichero in docs():
            campos = frontmatter(fichero) or {}
            with self.subTest(fichero=fichero.name):
                self.assertIn(campos.get("tipo"), TIPOS)

    def test_los_de_la_raiz_NO_lo_llevan(self):
        # README, AGENTS, CONTEXT y CLAUDE se leen con los ojos, no se indexan.
        # En midgaror ninguno lo lleva; aquí tampoco, y que no se cuele.
        for fichero in sorted(RAIZ.glob("*.md")):
            with self.subTest(fichero=fichero.name):
                self.assertIsNone(
                    frontmatter(fichero),
                    f"{fichero.name} está en la raíz y no lleva frontmatter")


class TestElIndiceNoMiente(unittest.TestCase):
    """Un documento que no está en el índice es un documento que nadie encuentra."""

    def indice(self) -> str:
        return (RAIZ / "docs" / "README.md").read_text(encoding="utf-8")

    def test_cada_doc_esta_enlazado_en_el_indice(self):
        indice = self.indice()
        for fichero in docs():
            if fichero.name == "README.md":
                continue
            nombre = fichero.relative_to(RAIZ / "docs").as_posix()
            with self.subTest(fichero=nombre):
                self.assertIn(f"({nombre})", indice,
                              f"{nombre} existe y no está en docs/README.md")

    def test_el_indice_no_enlaza_a_lo_que_no_existe(self):
        # El otro lado del mismo problema, y el que más cuesta ver: se borra un
        # fichero y el enlace se queda. En midgaror eso lo caza
        # `auditoria-enlaces.py`; aquí, esto.
        for enlace in re.findall(r"\]\(([^)#:]+\.md)\)", self.indice()):
            if enlace.startswith("http"):
                continue
            with self.subTest(enlace=enlace):
                self.assertTrue((RAIZ / "docs" / enlace).resolve().exists()
                                or (RAIZ / "docs" / enlace).exists(),
                                f"docs/README.md enlaza a {enlace} y no existe")


class TestLaRaizNoSeLlena(unittest.TestCase):
    """La raíz corta es el patrón de bulletyroulet, y se deshace sola."""

    PERMITIDOS = {
        "README.md", "AGENTS.md", "CONTEXT.md", "CLAUDE.md",
        "Makefile", "ruff.toml", ".gitignore", ".gitmodules", ".env.example",
    }

    def test_no_aparecen_ficheros_nuevos_sin_decidirlo(self):
        # Cada fichero suelto en la raíz es una decisión. Las cinco plantillas
        # de systemd estuvieron ahí hasta el 2026-09-12 y nadie lo decidió:
        # se fueron poniendo.
        sueltos = {f.name for f in RAIZ.iterdir()
                   if f.is_file() and not f.name.startswith(".venv")}
        de_mas = sueltos - self.PERMITIDOS
        self.assertEqual(
            de_mas, set(),
            "esto está suelto en la raíz; si tiene que estar, añádelo a "
            "PERMITIDOS en esta prueba y así queda decidido a propósito")


if __name__ == "__main__":
    unittest.main()
