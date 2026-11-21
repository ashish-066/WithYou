"""Brains package for dual-brain architecture."""

from brain.brains.fast_brain import (
    create_fast_brain_subgraph,
    fast_brain_node,
)
from brain.brains.router import (
    BrainRouter,
    DFATransition,
    brain_router_node,
    classify_input,
    input_processor_node,
    route_to_brain,
)
from brain.brains.slow_brain import (
    create_slow_brain_subgraph,
    slow_brain_node,
)

__all__ = [
    # Router
    "BrainRouter",
    "DFATransition",
    "classify_input",
    "route_to_brain",
    "input_processor_node",
    "brain_router_node",
    # Fast brain
    "fast_brain_node",
    "create_fast_brain_subgraph",
    # Slow brain
    "slow_brain_node",
    "create_slow_brain_subgraph",
]
