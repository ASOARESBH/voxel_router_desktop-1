from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.auth import recovery as recovery_module
from app.auth.recovery import PasswordRecoveryService, RecoveryError, RecoveryUnavailableError, load_public_keys, public_key_to_text, sign_request
from app.auth.service import AuthenticationError, AuthenticationService
from app.core.engine import RouterEngine

VOXEL_KEY = Ed25519PrivateKey.generate()


@pytest.fixture
def auth(database):
    service = AuthenticationService(database)
    service.provision_administrator("voxeladmin", "SenhaInicial@2026")
    return service


@pytest.fixture
def recovery(database, auth):
    return PasswordRecoveryService(database, auth, "VR-TESTE01", [VOXEL_KEY.public_key()])


def test_signed_response_resets_password_once(database, auth, recovery):
    request = recovery.create_request("voxeladmin", "127.0.0.1")
    assert request["email"] == "admin@voxelpacs.com.br"
    assert "VR-TESTE01" in request["request_code"] and request["mailto"].startswith("mailto:admin@voxelpacs.com.br?")
    response = sign_request(VOXEL_KEY, request["request_code"])

    assert recovery.complete(response, "SenhaRecuperada@2026", "127.0.0.1") == "voxeladmin"
    assert auth.login("voxeladmin", "SenhaRecuperada@2026")["must_change_password"] is True
    with pytest.raises(RecoveryError):
        recovery.complete(response, "OutraSenha@20266", "127.0.0.1")
    actions = [row["action"] for row in database.query_all("SELECT action FROM audit_logs ORDER BY id")]
    assert "PASSWORD_RECOVERY_REQUEST" in actions and "RESET_PASSWORD_RECOVERY" in actions


def test_response_from_other_key_or_router_is_rejected(database, auth, recovery):
    request = recovery.create_request("voxeladmin", "127.0.0.1")
    forged = sign_request(Ed25519PrivateKey.generate(), request["request_code"])
    with pytest.raises(RecoveryError):
        recovery.complete(forged, "SenhaRecuperada@2026", "127.0.0.1")

    other_router = PasswordRecoveryService(database, auth, "VR-OUTRO", [VOXEL_KEY.public_key()])
    other_code = request["request_code"].replace("VR-TESTE01", "VR-OUTRO")
    with pytest.raises(RecoveryError):
        other_router.complete(sign_request(VOXEL_KEY, other_code), "SenhaRecuperada@2026", "127.0.0.1")
    with pytest.raises(AuthenticationError):
        auth.login("voxeladmin", "SenhaRecuperada@2026")


def test_weak_password_does_not_consume_request_and_failures_are_limited(recovery):
    request = recovery.create_request("voxeladmin", "127.0.0.1")
    response = sign_request(VOXEL_KEY, request["request_code"])
    with pytest.raises(ValueError):
        recovery.complete(response, "fraca", "127.0.0.1")
    for _ in range(5):
        with pytest.raises(RecoveryError):
            recovery.complete("VXRS1.invalido", "SenhaRecuperada@2026", "127.0.0.1")
    with pytest.raises(RecoveryError, match="Muitas tentativas"):
        recovery.complete(response, "SenhaRecuperada@2026", "127.0.0.1")


def test_open_requests_are_limited_and_unknown_user_rejected(recovery):
    with pytest.raises(RecoveryError):
        recovery.create_request("ninguem", "127.0.0.1")
    for _ in range(3):
        recovery.create_request("voxeladmin", "127.0.0.1")
    with pytest.raises(RecoveryError):
        recovery.create_request("voxeladmin", "127.0.0.1")


def test_without_public_key_recovery_is_unavailable(database, auth):
    service = PasswordRecoveryService(database, auth, "VR-TESTE01", [])
    assert service.configured is False
    with pytest.raises(RecoveryUnavailableError):
        service.create_request("voxeladmin", "127.0.0.1")


def test_versioned_key_file_has_only_public_keys():
    data = json.loads(recovery_module.PUBLIC_KEYS_PATH.read_text(encoding="utf-8"))
    assert all(set(entry) <= {"id", "public_key"} for entry in data["keys"])
    assert "PRIVATE" not in recovery_module.PUBLIC_KEYS_PATH.read_text(encoding="utf-8")


def test_api_flow(settings, database, tmp_path, monkeypatch):
    keys_file = tmp_path / "keys.json"
    keys_file.write_text(json.dumps({"keys": [{"id": "t", "public_key": public_key_to_text(VOXEL_KEY.public_key())}]}), encoding="utf-8")
    monkeypatch.setattr(recovery_module, "PUBLIC_KEYS_PATH", keys_file)
    monkeypatch.setattr("app.api.server.load_public_keys", lambda: load_public_keys(keys_file))
    settings.update("orthanc", {"enabled": False})
    with TestClient(create_app(RouterEngine(settings, database), start_engine=False)) as client:
        client.post("/api/auth/provision", json={"username": "voxeladmin", "password": "SenhaInicial@2026"})
        assert client.get("/api/auth/recovery").json() == {"configured": True}
        created = client.post("/api/auth/recovery/request", json={"username": "voxeladmin"})
        assert created.status_code == 201
        response = sign_request(VOXEL_KEY, created.json()["request_code"])
        done = client.post("/api/auth/recovery/complete", json={"response_code": response, "new_password": "SenhaRecuperada@2026"})
        assert done.status_code == 200 and done.json()["username"] == "voxeladmin"
        bad = client.post("/api/auth/recovery/complete", json={"response_code": response, "new_password": "SenhaRecuperada@2026"})
        assert bad.status_code == 400
        assert client.post("/api/auth/login", json={"username": "voxeladmin", "password": "SenhaRecuperada@2026"}).status_code == 200
