from typing import Literal

from pydantic import BaseModel, Field


class ExpertReviewRequest(BaseModel):
    """A demo viewer's expert-gate decision, persisted as an append-only audit row.

    ``decision`` mirrors the expert tab's three radios (agree / doubt / cannot);
    ``schema_gap_type`` is only meaningful when ``decision == "cannot"``.
    """

    case_id: str = Field(min_length=1, max_length=200)
    decision: Literal["agree", "doubt", "cannot"]
    schema_gap_type: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
