"""The technique library. Importing this package registers every technique."""

from __future__ import annotations

from . import lib_encoding, lib_metadata, lib_system  # noqa: F401  (registration side-effects)
from .base import (  # noqa: F401
    FAMILIES,
    PlantContext,
    PlantResult,
    TechniqueSpec,
    all_techniques,
    available_techniques,
    current_platform,
    technique,
)

__all__ = [
    "FAMILIES",
    "PlantContext",
    "PlantResult",
    "TechniqueSpec",
    "all_techniques",
    "available_techniques",
    "current_platform",
    "technique",
]
