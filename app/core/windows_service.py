"""Entrada comum dos serviços Windows empacotados com PyInstaller."""

from __future__ import annotations

import sys
from typing import Any


def handle_service_command_line(service_class: Any, argv: list[str] | None = None) -> int:
    """Despacha para o SCM ou trata install/remove/start/stop; devolve código de saída.

    Executável congelado iniciado pelo SCM chega sem argumentos: precisa do dispatcher do
    servicemanager (o HandleCommandLine só imprime a ajuda e o serviço não sobe). Nos comandos,
    o código de erro do pywin32 vira exit code para o instalador detectar a falha.
    """
    import servicemanager  # type: ignore[import-not-found]
    import win32serviceutil  # type: ignore[import-not-found]

    args = list(sys.argv if argv is None else argv)
    if len(args) == 1 and getattr(sys, "frozen", False):
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(service_class)
        servicemanager.StartServiceCtrlDispatcher()
        return 0
    result = win32serviceutil.HandleCommandLine(service_class, argv=args)
    return int(result or 0)
