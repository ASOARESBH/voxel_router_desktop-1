"""Ferramenta do suporte VOXEL para a recuperação de senha do VOXEL Router.

NÃO vai no instalador do cliente. A chave privada fica só com a VOXEL, cifrada por senha, fora de
qualquer repositório.

    python scripts/voxel_recovery_tool.py gerar-chave --saida D:\\cofre\\voxel-router-recovery.pem
    python scripts/voxel_recovery_tool.py assinar --chave D:\\cofre\\voxel-router-recovery.pem --pedido "VXRR1...."

Antes de assinar, confirme a identidade de quem pediu (ligar para o contato cadastrado da clínica).
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, Encoding, PrivateFormat, load_pem_private_key

from app.auth.recovery import parse_request_code, public_key_to_text, sign_request


def generate_key(output: Path) -> int:
    if output.exists():
        print(f"{output} já existe; nada foi alterado.", file=sys.stderr)
        return 2
    passphrase = getpass.getpass("Senha para proteger a chave privada (mín. 16 caracteres): ")
    if len(passphrase) < 16 or passphrase != getpass.getpass("Confirme a senha: "):
        print("Senha curta ou não confere; nada foi gerado.", file=sys.stderr)
        return 2
    key = Ed25519PrivateKey.generate()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, BestAvailableEncryption(passphrase.encode("utf-8"))))
    entry = {"id": f"voxel-{datetime.now(UTC):%Y%m%d}", "public_key": public_key_to_text(key.public_key())}
    print(f"Chave privada salva (cifrada) em {output}. Guarde backup offline; nunca envie nem faça commit.")
    print("Adicione esta entrada em config/recovery_public_keys.json (lista \"keys\"):")
    print(json.dumps(entry, ensure_ascii=False))
    return 0


def sign(key_path: Path, request_code: str) -> int:
    request = parse_request_code(request_code)
    expires = datetime.fromtimestamp(request["expires_at"], UTC)
    if expires <= datetime.now(UTC):
        print("Pedido expirado; peça um novo na tela do Router.", file=sys.stderr)
        return 2
    print(f"Router ID: {request['router_id']}\nUsuário:   {request['username']}\nPedido:    {request['request_id']}\nExpira:    {expires.astimezone():%d/%m/%Y %H:%M}")
    if input("Identidade do solicitante confirmada? Digite SIM para assinar: ").strip() != "SIM":
        print("Assinatura cancelada.")
        return 1
    passphrase = getpass.getpass("Senha da chave privada: ").encode("utf-8")
    key = load_pem_private_key(key_path.read_bytes(), password=passphrase)
    if not isinstance(key, Ed25519PrivateKey):
        print("A chave informada não é Ed25519.", file=sys.stderr)
        return 2
    print("\nCódigo de resposta (enviar ao solicitante):")
    print(sign_request(key, request_code))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recuperação de senha do VOXEL Router — uso exclusivo do suporte VOXEL")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("gerar-chave", help="Gera o par de chaves Ed25519 (uma vez)")
    generate.add_argument("--saida", required=True, type=Path)
    signer = commands.add_parser("assinar", help="Assina um pedido recebido por e-mail")
    signer.add_argument("--chave", required=True, type=Path)
    signer.add_argument("--pedido", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "gerar-chave":
            return generate_key(args.saida)
        return sign(args.chave, args.pedido)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
