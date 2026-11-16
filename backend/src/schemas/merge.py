from pydantic import BaseModel, Field
class SourceBatchInput(BaseModel):
    channel: str = Field(max_length=20)
    stream: str = Field(min_length=2, max_length=80)
    name: str = Field(default='', max_length=160)
    records: list[dict] = Field(min_length=1, max_length=5000)
class ArbitrationInput(BaseModel):
    line: str = Field(min_length=1, max_length=40)
    day: str = Field(max_length=10)
    field: str = Field(max_length=20)
    chosen_value: float
    reason: str = Field(min_length=2, max_length=300)
class PublishInput(BaseModel):
    line: str = Field(min_length=1, max_length=40)
