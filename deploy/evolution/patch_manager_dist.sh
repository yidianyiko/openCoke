#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <source-dist-dir> <output-dist-dir> [manager-prefix] [assets-prefix] [api-prefix]" >&2
  exit 1
fi

source_dir="$1"
output_dir="$2"
manager_prefix="${3:-/evolution-api/manager}"
assets_prefix="${4:-/evolution-api/manager-assets}"
api_prefix="${5:-/evolution-api}"

if [[ ! -d "$source_dir" ]]; then
  echo "source dist directory not found: $source_dir" >&2
  exit 1
fi

mkdir -p "$output_dir"
find "$output_dir" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -R "$source_dir"/. "$output_dir"/

index_html="$output_dir/index.html"
if [[ ! -f "$index_html" ]]; then
  echo "index.html not found in output dist: $index_html" >&2
  exit 1
fi

js_bundle="$(find "$output_dir/assets" -maxdepth 1 -type f -name 'index-*.js' | head -n 1)"
if [[ -z "$js_bundle" || ! -f "$js_bundle" ]]; then
  echo "manager js bundle not found under: $output_dir/assets" >&2
  exit 1
fi

python3 - "$index_html" "$js_bundle" "$manager_prefix" "$assets_prefix" "$api_prefix" <<'PY'
from pathlib import Path
import sys

index_path = Path(sys.argv[1])
js_path = Path(sys.argv[2])
manager_prefix = sys.argv[3].rstrip("/")
assets_prefix = sys.argv[4].rstrip("/")
api_prefix = sys.argv[5].rstrip("/")

index_content = index_path.read_text()
index_content = index_content.replace('src="/assets/', f'src="{assets_prefix}/')
index_content = index_content.replace('href="/assets/', f'href="{assets_prefix}/')
index_path.write_text(index_content)

js_content = js_path.read_text()
replacements = [
    ('basename:void 0', f'basename:"{manager_prefix}"'),
    (
        'window.location.protocol+"//"+window.location.host',
        f'window.location.protocol+"//"+window.location.host+"{api_prefix}"',
    ),
    ('"/manager/', '"/'),
    ('`/manager/', '`/'),
    ('\"/manager\"', '\"/\"'),
    ("'/manager'", "'/'"),
    ('n=()=>{e("/")}', 'n=()=>{e("/login")}'),
    ('[{path:"/",element:i.jsx(Fse,{})},{path:"/login"', '[{path:"/welcome",element:i.jsx(Fse,{})},{path:"/login"'),
]

for old, new in replacements:
    js_content = js_content.replace(old, new)

js_path.write_text(js_content)
PY

if ! grep -q "${assets_prefix}/" "$index_html"; then
  echo "index.html patch verification failed: assets prefix missing" >&2
  exit 1
fi

if ! grep -q "basename:\"${manager_prefix}\"" "$js_bundle"; then
  echo "manager js patch verification failed: basename missing" >&2
  exit 1
fi

if ! grep -q "window.location.protocol+\"//\"+window.location.host+\"${api_prefix}\"" "$js_bundle"; then
  echo "manager js patch verification failed: api prefix missing" >&2
  exit 1
fi

echo "patched manager dist written to $output_dir"
