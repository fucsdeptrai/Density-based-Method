#!/usr/bin/env bash
# Tải dữ liệu Uber NYC (FiveThirtyEight) về data/raw/
# Nguồn: https://github.com/fivethirtyeight/uber-tlc-foil-response/tree/master/uber-trip-data
set -euo pipefail

BASE="https://raw.githubusercontent.com/fivethirtyeight/uber-tlc-foil-response/master/uber-trip-data"
DEST="${1:-data/raw}"
mkdir -p "$DEST"

echo "==> Tải taxi-zone-lookup.csv"
curl -fsSL -o "$DEST/taxi-zone-lookup.csv" "$BASE/taxi-zone-lookup.csv"

for m in apr14 may14 jun14 jul14 aug14 sep14; do
  echo "==> Tải uber-raw-data-$m.csv"
  curl -fsSL -o "$DEST/$m.csv" "$BASE/uber-raw-data-$m.csv"
done

echo "==> Tải uber-raw-data-janjune-15.csv.zip (~70MB) và giải nén"
TMP="$(mktemp -d)"
curl -fsSL -o "$TMP/janjune.zip" "$BASE/uber-raw-data-janjune-15.csv.zip"
unzip -o -q "$TMP/janjune.zip" -d "$DEST"
rm -rf "$TMP" "$DEST/__MACOSX"

echo
echo "Xong. Kiểm tra:"
wc -l "$DEST"/*.csv