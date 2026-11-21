#!/usr/bin/env bash
# Gera dist/voxel-router-linux-<versão>.tar.gz a partir do git (versão no arquivo VERSION).
# Uso: ./scripts/build_linux.sh [--release]   (--release exige árvore limpa e tag v<versão> no HEAD)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
VERSION="$(tr -d '[:space:]' < VERSION)"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "VERSION inválido"; exit 1; }
SHA="$(git rev-parse --short=12 HEAD)"
DIRTY=false; [[ -n "$(git status --porcelain --untracked-files=no)" ]] && DIRTY=true
if [[ "${1:-}" == "--release" ]]; then
  [[ "$DIRTY" == false ]] || { echo "Release exige árvore limpa."; exit 1; }
  [[ "$(git describe --tags --exact-match HEAD 2>/dev/null)" == "v$VERSION" ]] || { echo "Release exige a tag v$VERSION no HEAD."; exit 1; }
fi
OUT="dist/voxel-router-linux-$VERSION"
rm -rf "$OUT" "$OUT.tar.gz"; mkdir -p "$OUT"
# Código exatamente do commit (git archive): app, config e frontend juntos, como no Windows.
mkdir -p "$OUT/src"
git archive HEAD app config frontend pyproject.toml VERSION README.md | tar -x -C "$OUT/src"
cp VERSION requirements-build.txt packaging/linux/install.sh packaging/linux/uninstall.sh \
   packaging/linux/voxel-router.service packaging/linux/voxelvpn.conf.example "$OUT/"
chmod +x "$OUT/install.sh" "$OUT/uninstall.sh"
printf 'versao=%s\ncommit=%s\nalteracoes_locais=%s\ngerado_em=%s\n' "$VERSION" "$SHA" "$DIRTY" "$(date -Iseconds)" > "$OUT/build-info.txt"
tar -C dist -czf "$OUT.tar.gz" "voxel-router-linux-$VERSION"
sha256sum "$OUT.tar.gz" | tee "$OUT.tar.gz.sha256"
echo "Pacote: $OUT.tar.gz"
