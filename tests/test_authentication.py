from __future__ import annotations

import pytest

from app.auth.service import AccountLockedError, AuthenticationError, AuthenticationService


@pytest.fixture
def auth(database):
    return AuthenticationService(database, session_minutes=30)


def test_bootstrap_requires_password_change_and_never_stores_plaintext(database, auth):
    user_id = auth.provision_administrator("voxeladmin", "SenhaInicial@2026")
    response = auth.login("voxeladmin", "SenhaInicial@2026")

    assert user_id > 0
    assert response["must_change_password"] is True
    assert auth.current_user(response["token"])["username"] == "voxeladmin"
    stored = database.query_one("SELECT password_hash FROM users WHERE id = ?", (user_id,))
    assert stored["password_hash"] != "SenhaInicial@2026"
    assert stored["password_hash"].startswith("$argon2")


def test_password_change_revokes_existing_session(auth):
    user_id = auth.provision_administrator("voxeladmin", "SenhaInicial@2026")
    session = auth.login("voxeladmin", "SenhaInicial@2026")

    auth.change_password(user_id, "SenhaInicial@2026", "SenhaDefinitiva@2026")

    assert auth.current_user(session["token"]) is None
    next_session = auth.login("voxeladmin", "SenhaDefinitiva@2026")
    assert next_session["must_change_password"] is False


def test_failed_logins_are_limited(auth):
    auth.provision_administrator("voxeladmin", "SenhaInicial@2026")
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            auth.login("voxeladmin", "SenhaErrada@2026", "127.0.0.1")
    with pytest.raises(AccountLockedError):
        auth.login("voxeladmin", "SenhaInicial@2026", "127.0.0.1")


def test_local_reset_unlocks_revokes_sessions_and_requires_change(database, auth):
    user_id = auth.provision_administrator("voxeladmin", "SenhaInicial@2026")
    auth.change_password(user_id, "SenhaInicial@2026", "SenhaEsquecida@2026")
    old_session = auth.login("voxeladmin", "SenhaEsquecida@2026")
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            auth.login("voxeladmin", "SenhaErrada@2026")

    auth.reset_password_local("VoxelAdmin", "SenhaRecuperada@2026")

    assert auth.current_user(old_session["token"]) is None
    session = auth.login("voxeladmin", "SenhaRecuperada@2026")
    assert session["must_change_password"] is True
    audit = database.query_one("SELECT action, source_ip FROM audit_logs WHERE action = 'RESET_PASSWORD_LOCAL'")
    assert audit["source_ip"] == "local-console"


def test_local_reset_rejects_unknown_user_and_weak_password(auth):
    auth.provision_administrator("voxeladmin", "SenhaInicial@2026")
    with pytest.raises(ValueError):
        auth.reset_password_local("outro", "SenhaRecuperada@2026")
    with pytest.raises(ValueError):
        auth.reset_password_local("voxeladmin", "fraca")
    assert [user["username"] for user in auth.list_usernames()] == ["voxeladmin"]
