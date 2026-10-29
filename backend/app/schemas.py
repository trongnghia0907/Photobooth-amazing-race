from typing import Literal
from pydantic import BaseModel, ConfigDict


class CreateSession(BaseModel):
    model_config = ConfigDict(extra='forbid')
    layout: Literal['grid2x3', 'grid3x2', 'landscape_4'] = 'grid2x3'
    slot_count: Literal[4, 6] = 6


class CompleteSession(BaseModel):
    model_config = ConfigDict(extra='forbid')
    composite_id: str
