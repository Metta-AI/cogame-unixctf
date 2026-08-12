"""Every available technique must clear the validation funnel.

This is the library's core guarantee (the paper's mechanical validation): the
raw token is never plaintext on disk, and the recovery command reproduces it in
a freshly seeded directory. A failure here is a real defect in a technique.
"""

from __future__ import annotations

import pytest

from cogame_unixctf.techniques import all_techniques
from cogame_unixctf.verifier import validate_technique

AVAILABLE = [t for t in all_techniques() if t.available()]


@pytest.mark.parametrize("spec", AVAILABLE, ids=[t.id for t in AVAILABLE])
def test_technique_passes_funnel(spec):
    result = validate_technique(spec, trials=2)
    assert result.ok, f"{spec.id}: {result.reason}"


def test_library_covers_many_families():
    families = {t.family for t in AVAILABLE}
    assert len(families) >= 10, f"only {len(families)} families available: {families}"


def test_no_duplicate_ids():
    ids = [t.id for t in all_techniques()]
    assert len(ids) == len(set(ids))
