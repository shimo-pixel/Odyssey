"""Knowledge-base grounded branch simulation.

The engine plans grounded events from the user's knowledge base, forks the KB
into one workspace per response strategy, and then walks the timeline: for each
event every branch retrieves from its own KB, picks a strategy, and has its
predicted next state written back into that KB (replacing the previous
snapshot, graph included). The recorded trace is what the UI renders.
"""

from prds.kbsim.orchestrator import KbSimOrchestrator

__all__ = ["KbSimOrchestrator"]
