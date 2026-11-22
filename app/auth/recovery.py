"""Recuperação da senha do administrador por código assinado pela VOXEL (Ed25519).

O equipamento guarda só chaves PÚBLICAS (config/recovery_public_keys.json). O operador gera um
pedido na tela de login e o envia por e-mail ao suporte; a VOXEL confere a identidade, assina o
pedido com a chave privada que nunca sai da VOXEL e devolve o código de resposta. O código só vale
para este Router, este usuário e este pedido, uma única vez e até expirar.
"""

from __future__ import annotations

import base64
import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.auth.service import AuthenticationService
from app.config.settings import PROJECT_ROOT
from app.core.database import Database

RECOVERY_EMAIL = "admin@voxelpacs.com.br"
PUBLIC_KEYS_PATH = PROJECT_ROOT / "config" / "recovery_public_keys.json"
REQUEST_PREFIX = "VXRR1"
RESPONSE_PREFIX = "VXRS1"
REQUEST_TTL_HOURS = 24
MAX_OPEN_REQUESTS = 3
MAX_FAILED_COMPLETIONS = 5
FAILED_WINDOW_MINUTES = 60
ATTEMPT_KEY = "__password_recovery__"


class RecoveryError(ValueError):
    pass


class RecoveryUnavailableError(RecoveryError):
    pass


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def signed_message(request_code: str) -> bytes:
    return f"VOXEL-ROUTER-RECOVERY-v1|{request_code}".encode("utf-8")


def parse_request_code(request_code: str) -> dict[str, Any]:
    parts = request_code.strip().split(".")
    if len(parts) != 5 or parts[0] != REQUEST_PREFIX or not parts[4].isdigit():
        raise RecoveryError("Código de pedido inválido")
    return {"router_id": parts[1], "username": parts[2], "request_id": parts[3], "expires_at": int(parts[4])}


def sign_request(private_key: Ed25519PrivateKey, request_code: str) -> str:
    """Usado só pela ferramenta da VOXEL (scripts/voxel_recovery_tool.py)."""
    parse_request_code(request_code)
    return f"{RESPONSE_PREFIX}.{_b64encode(private_key.sign(signed_message(request_code.strip())))}"


def public_key_to_text(public_key: Ed25519PublicKey) -> str:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    return _b64encode(public_key.public_bytes(Encoding.Raw, PublicFormat.Raw))


def load_public_keys(path: Path = PUBLIC_KEYS_PATH) -> list[Ed25519PublicKey]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    keys = []
    for entry in data.get("keys", []):
        raw = _b64decode(str(entry.get("public_key", "")))
        if len(raw) == 32:
            keys.append(Ed25519PublicKey.from_public_bytes(raw))
    return keys


class PasswordRecoveryService:
    def __init__(self, database: Database, auth: AuthenticationService, router_id: str, public_keys: list[Ed25519PublicKey]) -> None:
        self.database = database
        self.auth = auth
        self.router_id = router_id
        self.public_keys = public_keys

    @property
    def configured(self) -> bool:
        return bool(self.public_keys) and bool(self.router_id)

    def create_request(self, username: str, source_ip: str) -> dict[str, Any]:
        if not self.configured:
            raise RecoveryUnavailableError("Recuperação por e-mail ainda não configurada neste equipamento")
        normalized = AuthenticationService._validate_username(username)
        if not self.database.query_one("SELECT 1 FROM users WHERE username = ?", (normalized,)):
            raise RecoveryError("Usuário não localizado")
        now = datetime.now(UTC)
        open_count = self.database.query_one(
            "SELECT COUNT(*) AS count FROM password_recovery_requests WHERE used_at IS NULL AND expires_at > ?",
            (int(now.timestamp()),),
        )
        if open_count and int(open_count["count"]) >= MAX_OPEN_REQUESTS:
            raise RecoveryError("Já existem pedidos de recuperação em aberto; aguarde a resposta da VOXEL")
        request_id = secrets.token_hex(8).upper()
        expires_at = int((now + timedelta(hours=REQUEST_TTL_HOURS)).timestamp())
        code = f"{REQUEST_PREFIX}.{self.router_id}.{normalized}.{request_id}.{expires_at}"
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO password_recovery_requests(request_id, request_code, username, expires_at) VALUES (?, ?, ?, ?)",
                (request_id, code, normalized, expires_at),
            )
        self.auth.audit(None, "PASSWORD_RECOVERY_REQUEST", "USER", normalized, source_ip, "SUCCESS")
        expires_text = datetime.fromtimestamp(expires_at, UTC).astimezone().strftime("%d/%m/%Y %H:%M")
        subject = f"VOXEL Router {self.router_id} - recuperação de senha"
        body = (
            "Pedido de recuperação da senha administrativa do VOXEL Router.\n\n"
            f"Router ID: {self.router_id}\nUsuário: {normalized}\nVálido até: {expires_text}\n\n"
            f"Código do pedido:\n{code}\n\n"
            "Clínica/cliente: \nNome e telefone de quem solicita: \n"
        )
        mailto = f"mailto:{RECOVERY_EMAIL}?subject={quote(subject)}&body={quote(body)}"
        return {"request_code": code, "email": RECOVERY_EMAIL, "mailto": mailto, "expires_at": expires_text}

    def complete(self, response_code: str, new_password: str, source_ip: str) -> str:
        if not self.configured:
            raise RecoveryUnavailableError("Recuperação por e-mail ainda não configurada neste equipamento")
        if self._recent_failures() >= MAX_FAILED_COMPLETIONS:
            raise RecoveryError("Muitas tentativas inválidas; aguarde 1 hora")
        AuthenticationService._validate_password(new_password)
        signature = self._decode_response(response_code)
        now = int(datetime.now(UTC).timestamp())
        rows = self.database.query_all(
            "SELECT request_id, request_code, username FROM password_recovery_requests WHERE used_at IS NULL AND expires_at > ?",
            (now,),
        )
        match = next((row for row in rows if signature and self._verify(row["request_code"], signature)), None)
        if match is None:
            self._record_failure(source_ip)
            raise RecoveryError("Código de resposta inválido, expirado ou já utilizado")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE password_recovery_requests SET used_at = CURRENT_TIMESTAMP WHERE request_id = ? AND used_at IS NULL",
                (match["request_id"],),
            )
            if cursor.rowcount != 1:
                raise RecoveryError("Código de resposta inválido, expirado ou já utilizado")
        self.auth.reset_password_local(match["username"], new_password, action="RESET_PASSWORD_RECOVERY", source_ip=source_ip)
        return str(match["username"])

    @staticmethod
    def _decode_response(response_code: str) -> bytes | None:
        value = "".join(response_code.split())
        if not value.startswith(f"{RESPONSE_PREFIX}."):
            return None
        try:
            raw = _b64decode(value[len(RESPONSE_PREFIX) + 1 :])
        except (ValueError, TypeError):
            return None
        return raw if len(raw) == 64 else None

    def _verify(self, request_code: str, signature: bytes) -> bool:
        message = signed_message(request_code)
        for key in self.public_keys:
            try:
                key.verify(signature, message)
                return True
            except InvalidSignature:
                continue
        return False

    def _recent_failures(self) -> int:
        row = self.database.query_one(
            "SELECT COUNT(*) AS count FROM auth_attempts WHERE username = ? AND success = 0 AND attempted_at >= datetime('now', ?)",
            (ATTEMPT_KEY, f"-{FAILED_WINDOW_MINUTES} minutes"),
        )
        return int(row["count"]) if row else 0

    def _record_failure(self, source_ip: str) -> None:
        with self.database.transaction() as connection:
            connection.execute("INSERT INTO auth_attempts(username, source_ip, success) VALUES (?, ?, 0)", (ATTEMPT_KEY, source_ip))
        self.auth.audit(None, "PASSWORD_RECOVERY_COMPLETE", "USER", None, source_ip, "DENIED")
