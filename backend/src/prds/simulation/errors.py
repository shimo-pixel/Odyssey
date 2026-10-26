"""Public simulation failures never include provider responses or credentials."""
from prds.models.domain import SimulationIssue


class SimulationFailure(RuntimeError):
    def __init__(self, stage: str, *, branch_id: str | None = None,
                 event_index: int | None = None, code: str = "stage_failed"):
        self.issue = SimulationIssue(code=code, stage=stage, branch_id=branch_id,
                                     event_index=event_index)
        context = f" [{branch_id}]" if branch_id else ""
        context += f" (event {event_index})" if event_index else ""
        super().__init__(f"Simulation failed at {stage}{context}. Check configuration and retry.")
