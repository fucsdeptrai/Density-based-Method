#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p data/maps
target=data/maps/nyc.pmtiles
if [[ -s "$target" ]]; then
  echo "Đã có $target. Xóa file này nếu muốn tải lại."
  exit 0
fi

version=1.31.2
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) asset="go-pmtiles-${version}_Darwin_arm64.zip" ;;
  Darwin-x86_64) asset="go-pmtiles-${version}_Darwin_x86_64.zip" ;;
  Linux-aarch64) asset="go-pmtiles_${version}_Linux_arm64.tar.gz" ;;
  Linux-x86_64) asset="go-pmtiles_${version}_Linux_x86_64.tar.gz" ;;
  *) echo "Hệ điều hành hoặc CPU chưa được hỗ trợ: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

tool_dir=$(mktemp -d)
trap 'rm -rf "$tool_dir"; rm -f "$target.partial"' EXIT
curl -fL --retry 3 "https://github.com/protomaps/go-pmtiles/releases/download/v${version}/${asset}" -o "$tool_dir/$asset"
if [[ "$asset" == *.zip ]]; then
  unzip -q "$tool_dir/$asset" -d "$tool_dir"
else
  tar -xzf "$tool_dir/$asset" -C "$tool_dir"
fi
chmod +x "$tool_dir/pmtiles"

"$tool_dir/pmtiles" extract \
  https://data.source.coop/protomaps/openstreetmap/v4.pmtiles \
  "$target.partial" --bbox=-74.34,40.49,-73.66,40.95 --maxzoom=15
"$tool_dir/pmtiles" verify "$target.partial"
mv "$target.partial" "$target"
echo "Bản đồ offline đã sẵn sàng: $target"
