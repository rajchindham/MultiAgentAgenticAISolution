from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Ask(Strict):
    question: str = Field(min_length=3, max_length=1500)
    application: str = Field(min_length=1, max_length=100)
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    previous_period: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    scorecard: Literal["maturity", "product_quality"]

class Plan(Strict):
    query: str
    need_metrics: bool
    need_documents: bool
    need_trends: bool

class Claim(Strict):
    text: str
    evidence_ids: list[str]

class Report(Strict):
    observations: list[Claim]
    recommendations: list[Claim]
    limitations: list[str]
