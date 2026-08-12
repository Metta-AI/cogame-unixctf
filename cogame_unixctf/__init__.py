"""cogame-unixctf — procedural Unix capture-the-flag environments for RL.

A faithful, self-contained implementation of the mechanics in "Unix-CTF:
Procedural Environments for Unix Competence Reinforcement Learning": a technique
library, an eight-flag environment builder with server-role dressing, the
validation funnel, and a gym-style shell RL environment with verifiable reward.
"""

from __future__ import annotations

from .environment import Environment, PlantedFlag
from .rl_env import UnixCTFEnv
from .techniques import (
    FAMILIES,
    all_techniques,
    available_techniques,
    current_platform,
)
from .verifier import validate_library, validate_technique

__version__ = "0.1.0"

__all__ = [
    "Environment",
    "PlantedFlag",
    "UnixCTFEnv",
    "FAMILIES",
    "all_techniques",
    "available_techniques",
    "current_platform",
    "validate_library",
    "validate_technique",
    "__version__",
]
