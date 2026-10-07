#!/usr/bin/env bash
# Tải dữ liệu Uber NYC (FiveThirtyEight) về data/raw/
# Nguồn: https://github.com/fivethirtyeight/uber-tlc-foil-response/tree/master/uber-trip-data
set -euo pipefail

BASE="https://raw.githubusercontent.com/fivethirtyeight/uber-tlc-foil-response/master/uber-trip-data"
DEST="${1:-data/raw}"
mkdir -p "$DEST"

echo "==> Tai nyc_boroughs.geojson (ranh gioi hanh chinh 5 quan)"
# Endpoint chinh thuc cua NYC Open Data tra 403, nen dung ban mirror nay.
# 5 quan, 95 vong, 68.677 dinh — dung cho quy tac vung hop le.
curl -fL --retry 3 --retry-delay 2 -o "$DEST/nyc_boroughs.geojson" \
  "https://raw.githubusercontent.com/dwillis/nyc-maps/master/boroughs.geojson"

download_month() {
  month="$1"
  expected_rows="$2"
  target="$DEST/$month.csv"
  temporary="$target.part"

  trap 'rm -f "$temporary"' EXIT
  echo "==> Tai uber-raw-data-$month.csv"
  curl -fL --retry 3 --retry-delay 2 -o "$temporary" "$BASE/uber-raw-data-$month.csv"

  actual_rows="$(($(wc -l < "$temporary") - 1))"
  if [ "$actual_rows" -ne "$expected_rows" ]; then
    echo "Loi: $month.csv co $actual_rows dong, can $expected_rows dong." >&2
    exit 1
  fi

  mv "$temporary" "$target"
  trap - EXIT
}

while read -r month expected_rows; do
  download_month "$month" "$expected_rows"
done <<'EOF'
apr14 564516
may14 652435
jun14 663844
jul14 796121
aug14 829275
sep14 1028136
EOF

echo
echo "Xong. Kiểm tra:"
wc -l "$DEST"/*14.csv
