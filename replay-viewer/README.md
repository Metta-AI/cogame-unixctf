# Replay viewer (Nim → wasm)

A single-fixed-view replay viewer for a Unix-CTF race, following the coworld
cogame replay-viewer convention (cf. `cogame-parley/replay-viewer`): the replay
is **decoded and normalized in a Nim → wasm module**, and a JS renderer draws the
per-tick frame stream to one fixed canvas with a scrubber transport.

```
replay-viewer/
  unixctf_replay.nim   # wasm module: parse race transcript -> normalized frames
  config.nims          # emscripten build switches (MODULARIZE, exported C ABI)
  renderer.js          # canvas renderer: header, flag board, lanes, winner overlay
  static_replay.js     # embedded race transcripts (base64) + wasm↔renderer glue
  index.html           # the fixed stage + transport (scrubber / play / speed / seed)
  dist/                # build output (gitignored): unixctf_replay.{js,wasm}
```

## Build & run

Needs `nim` and `emcc` (emscripten) on PATH.

```bash
./tools/build_replay_viewer.sh            # compiles the wasm, links it next to index.html
cd replay-viewer && python3 -m http.server 8791   # wasm must be served over http, not file://
# open http://localhost:8791/index.html
```

`./tools/build_replay_viewer.sh /abs/out/dir` instead assembles a self-contained
static bundle in that directory.

## wasm interface (C ABI)

The module (`EXPORT_NAME=UnixctfReplayModule`, MODULARIZE) exposes:

| export | purpose |
|---|---|
| `uc_load_replay(ptr, len) -> int` | parse a raw race-transcript JSON; 0 = ok |
| `uc_payload_ptr() / uc_payload_len()` | the normalized frames JSON (bytes) |
| `uc_error_ptr() / uc_error_len()` | decode error string on failure |

`static_replay.js` mallocs the input into `HEAPU8`, calls `uc_load_replay`, then
reads the normalized payload back out and hands it to `UnixctfViewer.attach`.

The payload buffers are C-`malloc`'d (not Nim GC seqs) so they survive `main`
returning — the safe pairing with `-d:useMalloc` that avoids the known
"Nim main-exit frees module globals" wasm use-after-free for these viewers.

## Refreshing the embedded replays

```bash
for s in 1 0 3; do python3 -m cogame_unixctf race --seed $s --json /tmp/race_$s.json; done
# then regenerate static_replay.js (embeds base64 of each transcript); see the
# generator in the project README / git history.
```

## Note

This wasm viewer is the repo-native, convention-following viewer. The
`viz/unixctf-race.html` page is a dependency-free HTML/JS variant of the same
race that can be hosted as a static artifact (wasm can't, under a strict CSP).
