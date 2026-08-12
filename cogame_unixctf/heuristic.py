"""Graded heuristic shell solvers.

These are hand-written "competent Unix user" policies at three skill tiers. They
are NOT the paper's trained models (which need a GPU trainer we don't run here);
they exist to produce real, differentiated race transcripts — a novice that
knows only the obvious decoders, a journeyman that handles compression/archives/
configs, and an expert that also cracks metadata, databases, certs and text
transforms. Each is a stateful ``policy(observation) -> command`` callable.

A real LLM policy drops into exactly the same slot: same signature, same env.
"""

from __future__ import annotations

import re
import shlex
from random import Random

# Shell snippet: pull every long base64-looking run out of a file, decode each,
# and print only the ones that decode to a flag. This is the idiomatic "grep for
# base64 and decode" move a competent operator reaches for.
_B64_DECODE_LOOP = (
    "while IFS= read -r b; do d=$(printf '%s' \"$b\" | base64 -d 2>/dev/null); "
    "case \"$d\" in flag\\{*\\}) printf '%s\\n' \"$d\";; esac; done"
)


def _b64_sweep(path: str) -> str:
    f = shlex.quote(path)
    return f"grep -aoE '[A-Za-z0-9+/=]{{16,}}' {f} 2>/dev/null | " + _B64_DECODE_LOOP


def _b64_sweep_stdin() -> str:
    return "grep -aoE '[A-Za-z0-9+/=]{16,}' 2>/dev/null | " + _B64_DECODE_LOOP


# Try the common reversible text transforms on a file; print whichever yields a flag.
def _text_battery(path: str) -> str:
    f = shlex.quote(path)
    return (
        "for c in "
        f"\"rev {f}\" "
        f"\"tr 'A-Za-z' 'N-ZA-Mn-za-m' < {f}\" "
        f"\"sed 's/\\(.\\)./\\1/g' {f}\" "
        f"\"awk '{{print \\$2}}' {f} | tr -d '\\n'\""
        "; do r=$(eval \"$c\" 2>/dev/null); case \"$r\" in flag\\{*\\}*) printf '%s\\n' \"$r\"; break;; esac; done"
    )


FLAGDIR = re.compile(r"/\d{4}_[a-z_]+/")


def _file_command(path: str) -> tuple[int, str] | None:
    """The recovery this file invites, as ``(min_skill, command)`` — the lowest
    tier that would recognize and crack it — or None if nothing obvious fits."""
    f = shlex.quote(path)
    low = path.lower()
    base = path.rsplit("/", 1)[-1]

    # Tier 1: blatantly-labelled encodings.
    if low.endswith(".b64"):
        return 1, f"base64 -d < {f}"
    if low.endswith(".hex"):
        return 1, f"xxd -r -p {f}"

    # Tier 2: compression, archives, and base64 sitting in text/config/logs.
    if low.endswith(".gz.gz"):
        return 2, f"gzip -dc {f} | gzip -dc | base64 -d"
    if low.endswith(".tar.gz"):
        return 2, f'tar xzOf {f} "$(tar tzf {f} | head -1)" | base64 -d'
    if low.endswith(".gz"):
        return 2, f"gzip -dc {f} | base64 -d"
    if low.endswith(".tar"):
        return 2, f'tar xOf {f} "$(tar tf {f} | head -1)" | base64 -d'
    if low.endswith(".bz2"):
        return 2, f"bzip2 -dc {f} | base64 -d"
    if low.endswith(".xz"):
        return 2, f"xz -dc {f} | base64 -d"
    if low.endswith(".zip"):
        return 2, f"unzip -p {f} | base64 -d"
    if low.endswith((".conf", ".json", ".log", ".http", ".dat")) or base.startswith(("passwd", ".netrc")):
        return 2, _b64_sweep(path)

    # Tier 3: databases, certs, sourced shell state, and reversible text transforms.
    if low.endswith(".sqlite"):
        return 3, f"sqlite3 {f} .dump 2>/dev/null | " + _b64_sweep_stdin()
    if low.endswith(".pem"):
        return 3, (
            f"openssl x509 -in {f} -noout -subject -nameopt multiline 2>/dev/null "
            f"| awk '/commonName/{{print $NF}}' | base64 -d"
        )
    if low.endswith(".sh"):
        return 3, (
            f"bash -c 'source {f} 2>/dev/null; "
            f'for fn in $(declare -F | awk "{{print \\$3}}"); do $fn 2>/dev/null; done\''
        )
    if low.endswith(".txt"):
        return 3, _text_battery(path)

    return None


# Expert-only global sweeps: each cracks a whole off-content family in one turn.
# Each is gated on evidence in the recon listing so the expert doesn't burn a
# turn sweeping for a family that isn't present.
_SWEEP_XATTR = (
    'find . -type f -exec sh -c \'v=$(xattr -p user.flag "$1" 2>/dev/null || getfattr --only-values -n user.flag "$1" 2>/dev/null); '
    '[ -n "$v" ] && printf "%s" "$v" | base64 -d\' _ {} \\; 2>/dev/null'
)
_SWEEP_FILENAME = 'for f in $(find . -name "*.name" 2>/dev/null); do basename "$f" .name; done | xxd -r -p 2>/dev/null'
_SWEEP_SYMLINK = 'for l in $(find . -type l 2>/dev/null); do readlink "$l" | base64 -d 2>/dev/null | grep -a "^flag{"; done'
_SWEEP_ELF = 'for f in $(grep -rla UNIXCTF . 2>/dev/null); do strings "$f" | grep "^UNIXCTF:" | cut -d: -f2 | base64 -d; done'

_LINKS_MARKER = "__LINKS__"
_RECON = f"find . -type f 2>/dev/null; echo {_LINKS_MARKER}; find . -type l 2>/dev/null"


class HeuristicSolver:
    """Stateful policy. Recons once, then works a prioritized queue of recovery
    attempts. Higher skill = knows more families and adds one-shot global sweeps."""

    NAMES = {1: "novice", 2: "journeyman", 3: "expert"}

    def __init__(self, skill: int, seed: int = 0):
        self.skill = skill
        self.name = self.NAMES.get(skill, f"skill{skill}")
        self.rng = Random(seed)
        self.queue: list[str] = []
        self.planned = False

    def __call__(self, observation: str) -> str:
        if not self.planned and not self.queue:
            # First move is always recon.
            if observation and "hidden flags" in observation:
                return _RECON
            self._plan(observation)
            self.planned = True

        if self.queue:
            return self.queue.pop(0)
        return "ls -la"  # idle once the plan is exhausted

    def _plan(self, recon_output: str) -> None:
        files, links = [], []
        bucket = files
        for line in recon_output.splitlines():
            line = line.strip()
            if line == _LINKS_MARKER:
                bucket = links
                continue
            if line.startswith("./"):
                bucket.append(line[2:])

        # Chase the suspicious "<nnnn>_<family>" directories first, but in a
        # per-agent shuffled order so the racers diverge and mostly work
        # different flags — contention becomes occasional (and dramatic) rather
        # than every agent lock-stepping the same file every tick.
        flag_files = [p for p in files if FLAGDIR.search("/" + p + "/")]
        other = [p for p in files if not FLAGDIR.search("/" + p + "/")]
        self.rng.shuffle(flag_files)
        self.rng.shuffle(other)
        files = flag_files + other

        # Bucket by the tier that would crack each file. Every tier's SHARED
        # (<=2) queue is identical in order, so on a contested flag the tiers act
        # on the same tick and the priority tie-break hands it to the stronger
        # one. The expert then works its exclusive (tier-3) families afterward.
        shared, exclusive = [], []
        for p in files:
            r = _file_command(p)
            if not r:
                continue
            min_skill, cmd = r
            if min_skill > self.skill:
                continue
            (shared if min_skill <= 2 else exclusive).append(cmd)

        self.queue.extend(shared)
        self.queue.extend(exclusive)

        # Expert appends evidence-gated one-shot sweeps for the off-content
        # families (xattrs, filename-encoding, symlinks, ELF strings).
        if self.skill >= 3:
            if any(p.endswith(".bin") for p in files):
                self.queue.append(_SWEEP_XATTR)
            if any(p.endswith(".name") for p in files):
                self.queue.append(_SWEEP_FILENAME)
            if links:
                self.queue.append(_SWEEP_SYMLINK)
            if any(p.endswith(".c") for p in files):
                self.queue.append(_SWEEP_ELF)


def make_solver(skill: int, seed: int = 0) -> HeuristicSolver:
    return HeuristicSolver(skill, seed)
