from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Metadata:
    title: str | None = None
    primary_text: str | None = None
    thesis: str | None = None
    outline: str | None = None
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
    paragraphs: list[dict[str, Any]] = field(
        default_factory=list
    )  # [{'index': int, 'original': str, 'edited': str | None, 'critique': str | None, 'evaluation_score': int | None}]
    manuscript: str | None = None
    manuscript_is_failure: bool = False
    manuscript_failure_reason: str | None = None
    manuscript_score: int | None = None
    manuscript_eval: str | None = None
    failed_formatting_attempts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobData":
        # Initialize Metadata with defaults, then update with provided data
        meta_data_dict = data.get("metadata", {})
        meta_fields = {
            k: v
            for k, v in meta_data_dict.items()
            if k in Metadata.__dataclass_fields__
        }
        metadata = Metadata(**meta_fields)

        # Initialize JobData fields with defaults
        job_instance = cls(metadata=metadata)

        # Update with provided data for valid fields
        for k, v in data.items():
            if k in JobData.__dataclass_fields__ and k != "metadata":
                setattr(job_instance, k, v)

        return job_instance
