#!/usr/bin/env bash
# Instalação do VOXEL Router em Linux (Ubuntu 24.04+ / Debian 13+; Python >= 3.12). Executar como root
# a partir da pasta extraída do pacote voxel-router-linux-<versão>.tar.gz.
# Estado: EXPERIMENTAL / homologação pendente. Diferenças do Windows:
#   - Orthanc local desligado (o Router guarda os objetos no próprio storage);
#   - VOXEL VPN pela página do Router não é suportada: use wg-quick (veja voxelvpn.conf.example);
#   - segredos cifrados com chave em /etc/voxel-router/secret.key (0600, dono voxel-router).
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Execute como root (sudo ./install.sh)."; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
VERSION="$(cat "$HERE/VERSION")"
PREFIX=/opt/voxel-router
DATA=/var/lib/voxel-router
ETC=/etc/voxel-router

command -v python3 >/dev/null || { echo "python3 ausente."; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || { echo "Requer Python >= 3.12."; exit 1; }
python3 -m venv --help >/dev/null 2>&1 || { echo "Instale python3-venv (apt install python3-venv)."; exit 1; }

if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE '[:.]4242$' && ! systemctl is-active --quiet voxel-router; then
  echo "A porta 4242/TCP já está em uso por outro programa. Libere a porta e execute de novo."; exit 1
fi

id voxel-router >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin voxel-router
install -d -m 0750 -o voxel-router -g voxel-router "$DATA"
install -d -m 0750 -o root -g voxel-router "$ETC"

echo "==> Ambiente Python ($PREFIX/venv)"
python3 -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/pip" install --quiet --upgrade pip
rm -rf "$PREFIX/src"; cp -a "$HERE/src" "$PREFIX/src"; chown -R root:root "$PREFIX/src"
# Dependências com versões exatas; o código roda de $PREFIX/src (inclui frontend e config padrão).
"$PREFIX/venv/bin/pip" install --quiet -c "$HERE/requirements-build.txt" "$PREFIX/src"

if [[ ! -s "$ETC/secret.key" ]]; then
  echo "==> Chave do cofre de segredos"
  (cd "$PREFIX/src" && "$PREFIX/venv/bin/python" -c 'from app.security.secrets import create_development_key as k; print(k())') > "$ETC/secret.key"
fi
chown voxel-router:voxel-router "$ETC/secret.key"; chmod 0600 "$ETC/secret.key"

cat > "$ETC/router.env" <<ENV
VOXEL_ROUTER_DATA_DIR=$DATA
VOXEL_ROUTER_SECRET_KEY_FILE=$ETC/secret.key
ENV
chmod 0640 "$ETC/router.env"; chown root:voxel-router "$ETC/router.env"

echo "==> Configuração inicial (Orthanc local desligado no Linux)"
(cd "$PREFIX/src" && runuser -u voxel-router -- env VOXEL_ROUTER_DATA_DIR="$DATA" VOXEL_ROUTER_SECRET_KEY_FILE="$ETC/secret.key" \
  "$PREFIX/venv/bin/python" -c 'from app.config.settings import Settings; Settings().update("orthanc", {"enabled": False})')

install -m 0644 "$HERE/voxel-router.service" /etc/systemd/system/voxel-router.service
systemctl daemon-reload
systemctl enable --now voxel-router
sleep 3
systemctl is-active --quiet voxel-router || { journalctl -u voxel-router -n 50 --no-pager; echo "Serviço não subiu."; exit 1; }

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow 4242/tcp comment 'VOXEL Router DICOM' >/dev/null
fi

echo
echo "VOXEL Router $VERSION instalado. Painel: http://127.0.0.1:8765 (só nesta máquina; use túnel SSH para acesso remoto)."
echo "DICOM: porta 4242/TCP. Dados: $DATA. Logs: journalctl -u voxel-router"
