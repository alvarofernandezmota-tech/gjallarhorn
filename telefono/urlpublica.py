"""La URL publica de esta maquina, la de verdad, no un hueco que rellenar.

`make funnel` imprimia
`https://<esta-maquina>.<tailnet>.ts.net/telefono/entrada`, y eso hay que
traducirlo a mano antes de pegarlo en el proveedor. Se ha visto pegar el
`<...>` tal cual mas de una vez, y no es torpeza: una linea lista para
copiar y una con un hueco dentro se parecen mucho a las dos de la
madrugada. Aqui se pregunta a tailscale como se llama esta maquina y se
imprime la URL entera.

Si tailscale no esta, no contesta o dice otra cosa, se vuelve al texto con
huecos: es peor, pero no es mentira.
"""

import json
import subprocess

PUERTO_TELEFONO = 8081
GENERICA = "https://<esta-maquina>.<tailnet>.ts.net"


def nombre_de_esta_maquina(tiempo: float = 5.0) -> str | None:
    """El DNS de esta maquina en el tailnet, o None si no se puede saber."""
    try:
        salida = subprocess.run(["tailscale", "status", "--json"],
                                capture_output=True, timeout=tiempo, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if salida.returncode != 0:
        return None
    try:
        estado = json.loads(salida.stdout)
    except json.JSONDecodeError:
        return None
    nombre = ((estado.get("Self") or {}).get("DNSName") or "").strip().rstrip(".")
    return nombre or None


def base() -> str:
    """`https://algo.tailnet.ts.net`, o el texto con huecos si no se sabe."""
    nombre = nombre_de_esta_maquina()
    return f"https://{nombre}" if nombre else GENERICA


def main(argumentos: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="La URL publica de esta maquina")
    parser.add_argument("--para-el-proveedor", action="store_true",
                        help="las dos URLs que se pegan en el panel del proveedor")
    args = parser.parse_args(argumentos)

    raiz = base()
    if not args.para_el_proveedor:
        print(raiz)
        return 0

    print(f"→ en el proveedor, webhook de voz:  {raiz}/telefono/entrada")
    print(f"  y status callback:                {raiz}/telefono/fin")
    if raiz == GENERICA:
        print()
        print("  (No he podido preguntarle a tailscale como se llama esta maquina.")
        print("   Cambia los <...> por lo que diga «tailscale status»; son huecos,")
        print("   no parte de la URL.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
