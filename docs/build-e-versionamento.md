# Build e versionamento do instalador (Windows `.exe` e pacote Linux)

O instalador de cada cliente é gerado **a partir do git**. A versão vive num único arquivo, `VERSION`,
conferido por teste contra `pyproject.toml`, `APP_VERSION` e o `.iss`.

## Gerar o `.exe` (Windows, PowerShell)

Na máquina de build (Python 3.12 x64 + Inno Setup 6):

```powershell
cd C:\xampp\htdocs\dashboard\voxel_router_desktop-1
git fetch origin
git checkout -f -B feature/router-fases-5-8 origin/feature/router-fases-5-8
powershell -ExecutionPolicy Bypass -File .\scripts\build_local_test.ps1 -Yes
```

Saída em `dist\`:

| Arquivo | Conteúdo |
|---|---|
| `VOXEL_ROUTER_SETUP_<versão>.exe` | instalador único do cliente (Router + Orthanc local + WireGuard) |
| `VOXEL_ROUTER_SETUP_<versão>.exe.sha256` | hash para conferir na máquina do cliente |
| `build-info.txt` | versão, commit, se havia alterações locais, hashes do Orthanc/WireGuard e do setup |

## Release (o `.exe` que vai para os clientes)

1. Atualize `VERSION`, `pyproject.toml`, `APP_VERSION` (`app/config/settings.py`) e o `#define AppVersion` do `.iss` (o teste falha se divergirem).
2. Commit e tag: `git tag v<versão>` e `git push origin v<versão>`.
3. Build com `-Release` (recusa árvore suja ou tag diferente):
   `powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1 -OrthancSha256 <hash> -WireGuardSha256 <hash> -Release`
4. Guarde o `.exe`, o `.sha256` e o `build-info.txt` juntos (ex.: anexos da release no GitHub).

## Pacote Linux (experimental)

```bash
./scripts/build_linux.sh            # ou --release
# dist/voxel-router-linux-<versão>.tar.gz (+ .sha256)
```

O pacote leva o código do commit (`git archive`), `install.sh`, `uninstall.sh`, a unidade systemd e um
modelo de túnel `wg-quick`. No cliente (Ubuntu 24.04+/Debian 13+, Python ≥ 3.12):

```bash
tar xzf voxel-router-linux-<versão>.tar.gz && cd voxel-router-linux-<versão> && sudo ./install.sh
```

Diferenças em relação ao Windows (homologação pendente):
- Orthanc local desligado: o Router guarda os objetos no próprio storage (`/var/lib/voxel-router`).
- VOXEL VPN pela página do Router não é suportada: configure `wg-quick@voxelvpn` com `voxelvpn.conf.example`.
- Segredos cifrados com chave em `/etc/voxel-router/secret.key` (0600, usuário `voxel-router`).
- Painel só em `127.0.0.1:8765`; acesso remoto por túnel SSH.
