from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Metadata:
    title: str | None = None
    thesis: str | None = None
    tone: str | None = None
    summary: str | None = None
    keywords: list[str] = field(default_factory=list)
    quotes: list[str] = field(default_factory=list)
    audience: str | None = None
    takeaways: list[str] = field(default_factory=list)


@dataclass
class JobData:
    transcript_txt: str | None = None
    formatted_txt: str | None = None
    metadata: Metadata = field(default_factory=Metadata)
    paragraphs: list[str] = field(default_factory=list)
    manuscript: str | None = None
    manuscript_score: int | None = None
    manuscript_eval: str | None = None
    failed_formatting_attempts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobData":
        # Handle nested metadata
        meta_data_dict = data.get("metadata", {})
        # Filter keys to match Metadata dataclass
        meta_fields = {
            k: v
            for k, v in meta_data_dict.items()
            if k in Metadata.__dataclass_fields__
        }
        metadata = Metadata(**meta_fields)

        # Filter keys for JobData
        job_fields = {
            k: v
            for k, v in data.items()
            if k in JobData.__dataclass_fields__ and k != "metadata"
        }
        return cls(**job_fields, metadata=metadata)
