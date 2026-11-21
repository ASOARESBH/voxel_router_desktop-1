"""Entrada dos serviços Windows congelados (pywin32 simulado)."""

from __future__ import annotations

import sys
import types

from app.core.windows_service import handle_service_command_line


def fake_pywin32(monkeypatch, result=None):
    calls: list[tuple] = []
    servicemanager = types.SimpleNamespace(
        Initialize=lambda: calls.append(("Initialize",)),
        PrepareToHostSingle=lambda cls: calls.append(("PrepareToHostSingle", cls)),
        StartServiceCtrlDispatcher=lambda: calls.append(("StartServiceCtrlDispatcher",)),
    )
    serviceutil = types.SimpleNamespace(HandleCommandLine=lambda cls, argv: calls.append(("HandleCommandLine", tuple(argv))) or result)
    monkeypatch.setitem(sys.modules, "servicemanager", servicemanager)
    monkeypatch.setitem(sys.modules, "win32serviceutil", serviceutil)
    return calls


def test_frozen_exe_started_by_scm_uses_dispatcher(monkeypatch):
    calls = fake_pywin32(monkeypatch)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert handle_service_command_line(object, ["VOXELOrthancService.exe"]) == 0
    assert [call[0] for call in calls] == ["Initialize", "PrepareToHostSingle", "StartServiceCtrlDispatcher"]


def test_install_failure_becomes_nonzero_exit_code(monkeypatch):
    calls = fake_pywin32(monkeypatch, result=1073)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert handle_service_command_line(object, ["svc.exe", "--startup", "auto", "install"]) == 1073
    assert calls == [("HandleCommandLine", ("svc.exe", "--startup", "auto", "install"))]


def test_successful_command_returns_zero(monkeypatch):
    fake_pywin32(monkeypatch, result=None)
    assert handle_service_command_line(object, ["svc.exe", "start"]) == 0
