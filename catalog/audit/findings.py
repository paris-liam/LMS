"""One audit finding = one problem with one field of one product."""

from dataclasses import asdict, dataclass

AUTO_FIX = "auto-fix"
PICKER = "picker"
MANUAL = "manual"

FINDING_COLUMNS = ["handle", "title", "type", "rule", "field", "current_value",
                   "proposed_value", "bucket", "detail"]


@dataclass(frozen=True)
class Finding:
    handle: str
    title: str
    type: str
    rule: str
    field: str
    current_value: str
    proposed_value: str
    bucket: str
    detail: str = ""

    def as_row(self) -> dict:
        return asdict(self)
