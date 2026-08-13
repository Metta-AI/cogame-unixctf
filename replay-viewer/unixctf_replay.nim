## Unix-CTF replay decoder (compiled to wasm).
##
## Ingests a raw race transcript (the JSON emitted by `cogame_unixctf race
## --json`) and emits a normalized, per-tick frame stream: for every tick, the
## cumulative claim owner of each flag, each agent's running score, and that
## tick's move (command, trimmed output, exit, claimed flag indices). The JS
## renderer consumes the normalized stream and draws it to a single fixed
## canvas. Doing the decode/normalize in wasm is the piece that matches the
## coworld cogame replay-viewer convention.

import std/[json, strutils]

# --- payload buffers ---------------------------------------------------------
# C-malloc'd (not GC seqs) so they survive `main` returning: emscripten keeps
# the runtime alive but Nim/ARC would otherwise free module globals at exit,
# a known wasm use-after-free for these viewers.
proc c_malloc(size: csize_t): pointer {.importc: "malloc", header: "<stdlib.h>".}
proc c_free(p: pointer) {.importc: "free", header: "<stdlib.h>".}

var payloadPtr: pointer = nil
var payloadLen: cint = 0
var errPtr: pointer = nil
var errLen: cint = 0

proc setBuf(s: string, p: var pointer, l: var cint) =
  if p != nil:
    c_free(p)
    p = nil
    l = 0
  if s.len > 0:
    p = c_malloc(csize_t(s.len))
    copyMem(p, unsafeAddr s[0], s.len)
    l = cint(s.len)

proc trimOutput(s: string, maxLines = 6, maxLen = 800): string =
  var lines: seq[string]
  for ln in s.splitLines():
    if ln.len == 0:
      continue
    lines.add(ln)
    if lines.len >= maxLines:
      break
  result = lines.join("\n")
  if result.len > maxLen:
    result = result[0 ..< maxLen] & " …"

proc normalize(raw: string): string =
  let j = parseJson(raw)
  let ticks = j["ticks"]
  let nFlags = j["n_flags"].getInt()
  let nAgents = j["agents"].len

  # First-claim owner per flag across the whole run.
  var firstTick = newSeq[int](nFlags)
  var firstOwner = newSeq[int](nFlags)
  var token = newSeq[string](nFlags)
  for i in 0 ..< nFlags:
    firstTick[i] = -1
    firstOwner[i] = -1
    token[i] = ""
  for tk in ticks:
    let t = tk["t"].getInt()
    for mv in tk["moves"]:
      let ag = mv["agent"].getInt()
      for c in mv["claims"]:
        let idx = c["index"].getInt()
        if firstTick[idx] < 0:
          firstTick[idx] = t
          firstOwner[idx] = ag
          token[idx] = c["token"].getStr()

  var frames = newJArray()
  for tk in ticks:
    let t = tk["t"].getInt()
    # cumulative claim owners + scores as of tick t
    var owners = newJArray()
    var scores = newSeq[int](nAgents)
    for i in 0 ..< nFlags:
      let own = (if firstTick[i] >= 0 and firstTick[i] <= t: firstOwner[i] else: -1)
      owners.add(%own)
      if own >= 0:
        inc scores[own]
    var scoreArr = newJArray()
    for s in scores:
      scoreArr.add(%s)

    var moves = newJArray()
    for mv in tk["moves"]:
      var claimIdx = newJArray()
      for c in mv["claims"]:
        claimIdx.add(%c["index"].getInt())
      moves.add(%*{
        "agent": mv["agent"].getInt(),
        "cmd": mv["cmd"].getStr(),
        "cwd": (if mv.hasKey("cwd"): mv["cwd"].getStr() else: "."),
        "exit": mv["exit"].getInt(),
        "out": trimOutput(mv["output"].getStr()),
        "claims": claimIdx,
      })

    frames.add(%*{
      "t": t,
      "owners": owners,
      "scores": scoreArr,
      "moves": moves,
    })

  var flags = newJArray()
  var fi = 0
  for f in j["flags"]:
    flags.add(%*{"family": f["family"].getStr(), "technique": f["technique_id"].getStr(), "token": token[fi]})
    inc fi
  var agents = newJArray()
  for a in j["agents"]:
    agents.add(%*{"name": a["name"].getStr(), "color": a["color"].getStr()})

  let outp = %*{
    "seed": j["seed"].getInt(),
    "role": j["role"].getStr(),
    "hostname": j["hostname"].getStr(),
    "nFlags": nFlags,
    "turnBudget": j["turn_budget"].getInt(),
    "winner": (if j.hasKey("winner"): j["winner"].getStr() else: ""),
    "agents": agents,
    "flags": flags,
    "frames": frames,
  }
  result = $outp

# --- exported C ABI ----------------------------------------------------------
proc uc_load_replay(inptr: pointer, inlen: cint): cint {.exportc, cdecl.} =
  try:
    var s = newString(inlen)
    if inlen > 0:
      copyMem(addr s[0], inptr, inlen)
    let norm = normalize(s)
    setBuf(norm, payloadPtr, payloadLen)
    setBuf("", errPtr, errLen)
    return 0
  except CatchableError as e:
    setBuf(e.msg, errPtr, errLen)
    setBuf("", payloadPtr, payloadLen)
    return 1

proc uc_payload_ptr(): pointer {.exportc, cdecl.} = payloadPtr
proc uc_payload_len(): cint {.exportc, cdecl.} = payloadLen
proc uc_error_ptr(): pointer {.exportc, cdecl.} = errPtr
proc uc_error_len(): cint {.exportc, cdecl.} = errLen

proc main() =
  discard

main()
