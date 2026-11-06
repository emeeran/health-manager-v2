from pydantic import BaseModel, Field


class FilenameCheckRequest(BaseModel):
    filenames: list[str] = Field(min_length=1, max_length=50)


class FilenameMatch(BaseModel):
    record_id: str
    record_type: str
    record_date: str
    filename: str


class FilenameCheckResponse(BaseModel):
    matches: list[FilenameMatch]
