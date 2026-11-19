@echo off
REM VOXEL Router - build e verificacao local (gerado pelo Claude). Nao precisa de administrador.
cd /d "%~dp0"
if not exist logs-local mkdir logs-local
set LOG=logs-local\pre-check.log
echo ==== Pre-check %date% %time% ==== > %LOG%
echo [servicos] >> %LOG%
for %%S in (VOXELRouter VOXELOrthanc Orthanc OrthancService "WireGuardTunnel$VOXELVPN") do (sc query %%S >> %LOG% 2>&1)
echo [portas 4242 8042 8765 11112 104] >> %LOG%
netstat -ano | findstr /R /C:":4242 " /C:":8042 " /C:":8765 " /C:":11112 " /C:":104 " >> %LOG% 2>&1
echo [git] >> %LOG%
git fetch origin >> %LOG% 2>&1
git checkout -f feature/router-fases-5-8 >> %LOG% 2>&1
git pull --ff-only >> %LOG% 2>&1
git log --oneline -1 >> %LOG% 2>&1
echo Pre-check gravado em %LOG%
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_local_test.ps1 -Yes
echo.
echo Fim. Exit code: %ERRORLEVEL%
echo %ERRORLEVEL% > logs-local\build-exit-code.txt
pause
