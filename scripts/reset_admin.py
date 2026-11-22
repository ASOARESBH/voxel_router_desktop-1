"""Recupera o acesso administrativo local do VOXEL Router.

Uso no equipamento (PowerShell como Administrador):
    VOXELResetAdmin.exe --list
    VOXELResetAdmin.exe --username voxeladmin

A nova senha é digitada sem eco, nunca aparece em log e precisa ser trocada no próximo login.
Exige acesso local de administrador ao Windows (o banco fica em ProgramData com ACL restrita).
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auth.service import AuthenticationService
from app.config.settings import Settings
from app.core.database import Database
from app.core.logging import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recuperação do acesso administrativo local do VOXEL Router")
    parser.add_argument("--list", action="store_true", help="Lista os usuários existentes")
    parser.add_argument("--username", help="Usuário cuja senha será redefinida")
    args = parser.parse_args(argv)
    settings = Settings()
    configure_logging(settings.paths)
    database = Database(settings.paths)
    database.initialize()
    auth = AuthenticationService(database, int(settings.get("api", "session_minutes", default=30)))

    users = auth.list_usernames()
    if args.list or not args.username:
        if not users:
            print("Nenhum usuário provisionado. Abra http://127.0.0.1:8765 para criar o administrador.")
            return 0
        for user in users:
            state = "ativo" if user["is_active"] else "inativo"
            print(f"{user['username']} ({state})")
        if not args.username:
            print("Para redefinir: VOXELResetAdmin.exe --username <usuario>")
        return 0

    password = getpass.getpass("Nova senha (12+ caracteres, maiúscula, minúscula, número e símbolo): ")
    if password != getpass.getpass("Confirme a nova senha: "):
        print("As senhas não coincidem; nada foi alterado.", file=sys.stderr)
        return 2
    try:
        auth.reset_password_local(args.username, password)
    except ValueError as error:
        print(f"{error}; nada foi alterado.", file=sys.stderr)
        return 2
    print("Senha redefinida. Sessões anteriores foram encerradas e a troca será exigida no próximo login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
