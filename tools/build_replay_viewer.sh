#!/usr/bin/env bash
# Build the Unix-CTF replay viewer: compile the Nim decoder to wasm (emscripten)
# and assemble a self-contained static bundle. Mirrors the coworld cogame
# replay-viewer build convention (cf. cogame-parley/tools/build_replay_viewer.sh).
#
#   ./tools/build_replay_viewer.sh [output_dir]
#
# With no argument it builds in place under replay-viewer/dist and leaves the
# page runnable from replay-viewer/index.html.
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rv="${repo_dir}/replay-viewer"

command -v nim  >/dev/null || { echo "nim not found on PATH" >&2; exit 1; }
command -v emcc >/dev/null || { echo "emcc not found on PATH (activate emsdk)" >&2; exit 1; }

echo "==> compiling unixctf_replay.nim -> wasm"
(cd "${repo_dir}" && nim c --hints:off -d:emscripten "${rv}/unixctf_replay.nim")

dist="${rv}/dist"
test -s "${dist}/unixctf_replay.wasm"
test -s "${dist}/unixctf_replay.js"

# In-place run uses replay-viewer/{index.html,renderer.js,static_replay.js} + dist/.
# Symlink the wasm outputs next to index.html so it works without a bundle step.
ln -sf "dist/unixctf_replay.js"   "${rv}/unixctf_replay.js"
ln -sf "dist/unixctf_replay.wasm" "${rv}/unixctf_replay.wasm"

if [[ "$#" -ge 1 ]]; then
  out="$1"
  [[ "${out}" == /* ]] || { echo "output dir must be absolute: ${out}" >&2; exit 1; }
  rm -rf "${out}"; mkdir -p "${out}"
  cp "${dist}/unixctf_replay.js" "${dist}/unixctf_replay.wasm" \
     "${rv}/index.html" "${rv}/renderer.js" "${rv}/static_replay.js" "${out}/"
  test -f "${out}/index.html"
  grep -q 'data-replay' "${out}/static_replay.js"
  echo "unixctf replay viewer bundle: ${out}"
else
  echo "built in place — open ${rv}/index.html (serve over http for wasm)"
fi
