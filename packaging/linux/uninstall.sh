#!/usr/bin/env bash
# Remove o serviço e o programa. Dados (/var/lib/voxel-router) e configuração (/etc/voxel-router) ficam.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Execute como root."; exit 1; }
systemctl disable --now voxel-router 2>/dev/null || true
rm -f /etc/systemd/system/voxel-router.service
systemctl daemon-reload
rm -rf /opt/voxel-router
echo "VOXEL Router removido. Dados preservados em /var/lib/voxel-router e /etc/voxel-router."
