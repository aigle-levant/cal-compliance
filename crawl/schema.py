from pydantic import BaseModel
from typing import Optional, List


class DIRRecord(BaseModel):
    title_number: Optional[str] = None
    title_name: Optional[str] = None

    division: Optional[str] = None
    chapter: Optional[str] = None
    subchapter: Optional[str] = None

    section_number: Optional[str] = None

    section_heading: str

    citation: Optional[str] = None

    breadcrumb_path: Optional[str] = None

    source_url: str

    content_markdown: str

    retrieved_at: str

class ExtractedMetadata(BaseModel):
    division: str
    topic: str
    industries: List[str]
    summary: str