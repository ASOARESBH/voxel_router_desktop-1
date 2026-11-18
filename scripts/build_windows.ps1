# Requires: Windows PowerShell 5.1+, Python 3.12 x64, Inno Setup 6.
# Componentes de terceiros homologados (nunca baixados pelo build):
#   vendor\orthanc\Orthanc.exe (+ plugins)           -> -OrthancSha256 <sha256 do Orthanc.exe>
#   vendor\wireguard\wireguard-installer.msi (amd64)  -> -WireGuardSha256 <sha256 do MSI>
# Uso: powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1 -OrthancSha256 <hash> -WireGuardSha256 <hash> [-Version 1.1.0]
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$OrthancSha256,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$WireGuardSha256,
    [ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version = '1.1.0',
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# Comandos nativos não disparam exceção no PowerShell: todo exit code diferente de 0 interrompe o build.
function Invoke-Checked {
    param([Parameter(Mandatory = $true)][string]$Step, [Parameter(Mandatory = $true)][scriptblock]$Command)
    Write-Host "==> $Step"
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Step falhou (exit code $LASTEXITCODE)" }
}

function Assert-Sha256 {
    param([string]$Path, [string]$Expected, [string]$Name)
    if (-not (Test-Path $Path -PathType Leaf)) { throw "$Name não encontrado em $Path" }
    $actual = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash
    if ($actual -ne $Expected.ToUpperInvariant()) { throw "$Name com SHA-256 diferente do homologado. Esperado $Expected, obtido $actual" }
    Write-Host "$Name SHA-256 OK: $actual"
}

if ((Get-Command py -ErrorAction SilentlyContinue) -eq $null) { throw 'Python Launcher não encontrado. Instale Python 3.12 x64 no ambiente de build.' }

$OrthancExe = Join-Path $Root 'vendor\orthanc\Orthanc.exe'
$WireGuardMsi = Join-Path $Root 'vendor\wireguard\wireguard-installer.msi'
Assert-Sha256 -Path $OrthancExe -Expected $OrthancSha256 -Name 'Orthanc.exe'
Assert-Sha256 -Path $WireGuardMsi -Expected $WireGuardSha256 -Name 'WireGuard MSI'
$signature = Get-AuthenticodeSignature -FilePath $WireGuardMsi
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'WireGuard') {
    throw "Assinatura Authenticode do WireGuard MSI inválida ($($signature.Status); $($signature.SignerCertificate.Subject))"
}
Write-Host "WireGuard MSI assinado por: $($signature.SignerCertificate.Subject)"

# Nunca reaproveitar artefato antigo.
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path dist | Out-Null

Invoke-Checked 'Atualizar pip' { py -3.12 -m pip install --upgrade pip }
Invoke-Checked 'Instalar dependências (constraints exatas)' { py -3.12 -m pip install -c requirements-build.txt . pyinstaller pillow }
Invoke-Checked 'Registrar dependências efetivas' { py -3.12 -m pip freeze | Out-File -Encoding utf8 dist\build-freeze.txt }
Invoke-Checked 'Gerar ícones e imagens' { py -3.12 scripts\generate_assets.py }

# O orthanc.json e o segredo interno são criados no computador de destino, em ProgramData,
# antes de registrar/iniciar os serviços. Nunca gerar credenciais de produção no ambiente de build.
Invoke-Checked 'PyInstaller VOXELRouter' { py -3.12 -m PyInstaller --noconfirm --clean --name VOXELRouter --icon frontend\static\img\router.ico --add-data "frontend;frontend" --add-data "config;config" app\main.py }
Invoke-Checked 'PyInstaller VOXELRouterService' { py -3.12 -m PyInstaller --noconfirm --clean --name VOXELRouterService --icon frontend\static\img\router.ico --add-data "frontend;frontend" --add-data "config;config" app\service_main.py }
Invoke-Checked 'PyInstaller VOXELOrthancService' { py -3.12 -m PyInstaller --noconfirm --clean --name VOXELOrthancService --icon frontend\static\img\router.ico --add-data "config;config" app\orthanc\service_main.py }
Invoke-Checked 'PyInstaller VOXELDiagnostics' { py -3.12 -m PyInstaller --noconfirm --clean --name VOXELDiagnostics --icon frontend\static\img\router.ico --add-data "config;config" scripts\diagnose_install.py }

if ($SkipInstaller) { Write-Host 'Instalador não gerado (-SkipInstaller).'; exit 0 }

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "${env:ProgramFiles}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw 'Inno Setup 6 não encontrado.' }
Invoke-Checked 'Inno Setup' { & $iscc "/DAppVersion=$Version" installer\VOXEL_ROUTER_SETUP.iss }

$setup = Join-Path $Root 'dist\VOXEL_ROUTER_SETUP.exe'
if (-not (Test-Path $setup -PathType Leaf)) { throw 'dist\VOXEL_ROUTER_SETUP.exe não foi gerado.' }
$hash = (Get-FileHash -Algorithm SHA256 -Path $setup).Hash
"$hash  VOXEL_ROUTER_SETUP.exe  versão $Version" | Out-File -Encoding ascii dist\VOXEL_ROUTER_SETUP.exe.sha256
Write-Host "Build concluído: $setup"
Write-Host "SHA-256: $hash"
Write-Host 'Setup NÃO assinado: uso restrito a laboratório/piloto (SmartScreen vai alertar).'
