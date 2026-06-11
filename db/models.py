from pydantic import BaseModel
from datetime import datetime

class CCRSection(BaseModel):
    title_number: str
    title_name: str

    division: str | None = None
    chapter: str | None = None
    subchapter: str | None = None
    article: str | None = None

    section_number: str
    section_heading: str

    citation: str
    breadcrumb_path: str

    source_url: str

    content_markdown: str

    retrieved_at: datetime