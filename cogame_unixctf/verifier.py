"""The validation funnel.

Reproduces the paper's mechanical checks that turn a candidate technique into a
trusted, portable library entry:

1. **Plaintext-absence** — the planted token must not appear as plaintext in any
   file's bytes. (If it did, ``grep -r`` would trivialise the task.)
2. **Recovery-success** — the recovery command must print the token and exit 0.
3. **Fresh-directory portability** — replant and re-recover in a second, freshly
   seeded directory; this catches hardcoded paths or tokens that only work once.
4. **Dedup** — surviving variants are keyed by canonical technique id.

The paper reports an 87.5% end-to-end yield through this funnel; here every
shipped technique is expected to pass, so a failure is a real defect.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from random import Random

from .flags import make_token
from .techniques import PlantContext, TechniqueSpec, all_techniques


@dataclass
class TrialResult:
    ok: bool
    plaintext_absent: bool
    recovered: bool
    recovered_value: str
    reason: str = ""


@dataclass
class ValidationResult:
    technique_id: str
    family: str
    ok: bool
    trials: list[TrialResult]
    skipped: bool = False
    skip_reason: str = ""

    @property
    def reason(self) -> str:
        if self.skipped:
            return f"skipped ({self.skip_reason})"
        for t in self.trials:
            if not t.ok:
                return t.reason
        return "ok"


def _scan_plaintext(root: Path, token: str) -> bool:
    """Return True if the raw token is absent from every file's bytes."""
    needle = token.encode()
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            p = Path(dirpath) / fn
            if p.is_symlink() or not p.is_file():
                continue
            try:
                if needle in p.read_bytes():
                    return False
            except OSError:
                continue
    return True


def _one_trial(spec: TechniqueSpec, seed: int, timeout: float) -> TrialResult:
    workdir = Path(tempfile.mkdtemp(prefix="unixctf_val_"))
    procs: list = []
    try:
        token = make_token(Random(seed))
        ctx = PlantContext(workdir=workdir, token=token, rng=Random(seed), procs=procs)
        result = spec.plant(ctx)

        plaintext_absent = _scan_plaintext(workdir, token)

        try:
            proc = subprocess.run(
                ["bash", "--noprofile", "--norc", "-c", result.recovery_cmd],
                cwd=workdir,
                capture_output=True,
                timeout=timeout,
            )
            recovered_value = proc.stdout.decode(errors="replace").strip()
            recovered = proc.returncode == 0 and recovered_value == token
            rec_reason = ""
            if not recovered:
                if proc.returncode != 0:
                    rec_reason = f"recovery exit={proc.returncode}: {proc.stderr.decode(errors='replace')[:120]}"
                else:
                    rec_reason = f"recovered {recovered_value!r} != token"
        except subprocess.TimeoutExpired:
            recovered_value, recovered, rec_reason = "", False, "recovery timed out"

        reasons = []
        if not plaintext_absent:
            reasons.append("token present as plaintext on disk")
        if not recovered:
            reasons.append(rec_reason)
        ok = plaintext_absent and recovered
        return TrialResult(ok, plaintext_absent, recovered, recovered_value, "; ".join(reasons))
    finally:
        for p in procs:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        shutil.rmtree(workdir, ignore_errors=True)


def validate_technique(spec: TechniqueSpec, trials: int = 2, timeout: float = 15.0) -> ValidationResult:
    if not spec.available():
        return ValidationResult(spec.id, spec.family, False, [], skipped=True, skip_reason=spec.unavailable_reason())
    results = [_one_trial(spec, seed=1000 + i * 7919, timeout=timeout) for i in range(trials)]
    ok = all(t.ok for t in results)
    return ValidationResult(spec.id, spec.family, ok, results)


def validate_library(include_live: bool = False, trials: int = 2) -> list[ValidationResult]:
    out = []
    for spec in all_techniques():
        if spec.live and not include_live:
            out.append(ValidationResult(spec.id, spec.family, False, [], skipped=True, skip_reason="live (use --live)"))
            continue
        out.append(validate_technique(spec, trials=trials))
    return out
