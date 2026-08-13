import std/[os, strformat, strutils]

# Mirrors the coworld cogame replay-viewer build convention (cf. cogame-parley):
# compile the Nim replay decoder to a wasm module via emscripten. The module
# ingests a raw race transcript and emits a normalized, per-tick frame stream
# that the JS renderer draws to a single fixed canvas.

let rootDir = currentSourcePath().parentDir().parentDir()
let distDir = rootDir / "replay-viewer" / "dist"

if not dirExists(distDir):
  mkDir(distDir)

switch("nimcache", distDir / "nimcache")
switch("threads", "off")
--os:linux
--cpu:wasm32
--cc:clang
--clang.exe:emcc
--clang.linkerexe:emcc
--clang.cpp.exe:emcc
--clang.cpp.linkerexe:emcc
--mm:arc
--exceptions:goto
--define:noSignalHandler
--define:release
# Route allocations through emscripten's malloc; with Nim's own allocator a bad
# free silently poisons the freelists — dlmalloc traps loudly instead. Also the
# safe pairing for the "Nim main-exit frees all globals" wasm UAF: the payload
# buffers are C-malloc'd, not GC seqs, so they survive main returning.
--define:useMalloc

switch(
  "passL",
  (&"""
  -o {distDir / "unixctf_replay.js"}
  -O2
  -s ALLOW_MEMORY_GROWTH
  -s ABORTING_MALLOC=1
  -s ENVIRONMENT=web
  -s MODULARIZE=1
  -s EXPORT_NAME=UnixctfReplayModule
  -s EXPORTED_RUNTIME_METHODS=HEAPU8,ccall
  -s EXPORTED_FUNCTIONS=_main,_malloc,_free,_uc_load_replay,_uc_payload_ptr,_uc_payload_len,_uc_error_ptr,_uc_error_len
  """).replace("\n", " ")
)
