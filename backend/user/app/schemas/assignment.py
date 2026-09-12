from pydantic import BaseModel, Field


class AssignmentPlan(BaseModel):
    position_quotas: dict[str, int | dict[str, int]]
    branch_order: list[str] = Field(default_factory=lambda: ["육군", "해군", "해병대", "공군"])
    allow_branch_merge: bool = True
