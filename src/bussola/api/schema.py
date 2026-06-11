from pydantic import BaseModel
from typing import Any


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    sql: str
    result: list[dict[str, Any]]
    answer: str
