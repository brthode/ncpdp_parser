from __future__ import annotations

import pathlib
from abc import ABC
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field, PrivateAttr, StringConstraints, field_validator, model_validator

HEADER_LENGTH = 31
FIELD_SEPARATOR = chr(28)  # File Separator <FS> / <0x1c>
GROUP_SEPARATOR = chr(29)  # Group Separator <GS> / <0x1d>
SEGMENT_SEPARATOR = chr(30)  # Record Separator <RS> / <0x1e>


class TransactionCode(StrEnum):
    """Valid transaction codes for EMI headers."""

    SUBMISSION = "B1"
    REVERSAL = "B2"


class Version(StrEnum):
    """Valid version codes for EMI headers."""

    D0 = "D0"
    V51 = "51"


class Format(BaseModel):
    """Represents a field's position and length in the EMI header."""

    start: int
    end: int | None

    def __init__(self, start: int, end: int | None = None):
        super().__init__(start=start, end=end)

    @model_validator(mode="after")
    def validate_bounds(self) -> Format:
        if self.end is not None and self.start > self.end:
            raise ValueError("Start position cannot be greater than end position")
        return self


class EMIHeader(BaseModel):
    """
    Represents an EMI header with strict format requirements.

    Format:
    DDDDDD = RXBin (6 digits) Issuer Identification Number / Bank Identification Number
    AA = Version (D0 or 51)
    BN = Transaction Code (B1 or B2)
    DDDDDDDDDD = Processor Control # (10 digits)
    DDD = Count (3 digits, 001-999)
    YYYYMMDD = Date
    """

    rxbin: Annotated[str, StringConstraints(pattern=r"^\d{6}$")] = Field(description="6-digit BIN number")
    version: Version = Field(description="Version code (D0 or 51)")
    transaction_code: TransactionCode = Field(description="Transaction type (B1 for submission, B2 for reversal)")
    processor_control: Annotated[str, StringConstraints(pattern=r"^\d{10}$")] = Field(
        description="10-digit processor control number"
    )
    count: Annotated[str, StringConstraints(pattern=r"^(?:0\d{2}|[1-9]\d{2})$")] = Field(
        description="3-digit count between 001 and 999"
    )
    date: datetime = Field(description="Date in YYYYMMDD format")

    @field_validator("date", mode="before")
    @classmethod
    def validate_date_format(cls, v: Any) -> datetime:
        """Validates and converts the date string to datetime."""
        if isinstance(v, datetime):
            return v
        if not isinstance(v, str):
            raise ValueError("Date must be a string")
        try:
            return datetime.strptime(v, "%Y%m%d")
        except ValueError as err:
            raise ValueError("Date must be in YYYYMMDD format") from err

    @field_validator("count")
    @classmethod
    def validate_count_range(cls, v: str) -> str:
        """Ensures count is between 001 and 999."""
        count_int = int(v)
        if not 1 <= count_int <= 999:
            raise ValueError("Count must be between 001 and 999")
        return v

    def to_emi_string(self) -> str:
        """Converts the header to its EMI string representation."""
        return (
            f"{self.rxbin:<6}"
            f"{self.version:>2}"
            f"{self.transaction_code:>2}"
            f"{self.processor_control:<10}"
            f"{self.count:>3}"
            f"{self.date.strftime('%Y%m%d')}"
        )

    @classmethod
    def from_emi_string(cls, emi_string: str) -> EMIHeader:
        """Creates an EMIHeader instance from an EMI string."""
        if len(emi_string) < 31:  # Minimum length for all required fields
            raise ValueError("EMI string too short")

        return cls(
            rxbin=emi_string[0:6].strip(),
            version=emi_string[6:8].strip(),
            transaction_code=emi_string[8:10].strip(),
            processor_control=emi_string[10:20].strip(),
            count=emi_string[20:23].strip(),
            date=emi_string[23:31].strip(),
        )


class SegmentBase(ABC, BaseModel):
    """Abstract base class for all segments."""

    @classmethod
    def get_key_mapping(cls) -> dict[str, str]:
        return cls._key_mapping


def map_values_to_keys(segment_mapping: dict[str, str], values: list[str]) -> dict[str, str]:
    return {segment_mapping[prefix]: value[2:] for value in values if (prefix := value[:2]) in segment_mapping}


class InsuranceSegment(SegmentBase):
    segment_id: str = "AM04"

    first_name: str
    last_name: str
    person_code: str
    cardholder_id: str
    internal_control_number: str

    _key_mapping: dict[str, str] = PrivateAttr(
        default={
            "C1": "first_name",
            "C2": "internal_control_number",
            "C3": "person_code",
            "A6": "cardholder_id",
            "A7": "last_name",
        }
    )


class PatientSegment(SegmentBase):
    segment_id: str = "AM01"

    a: str
    b: str
    c: str
    d: str
    e: str

    _key_mapping: dict[str, str] = PrivateAttr(
        default={
            "C4": "a",
            "C5": "b",
            "CA": "c",
            "CB": "d",
            "CP": "e",
        }
    )


@staticmethod
def parse_segment(
    raw_segment: str,
) -> InsuranceSegment | None:
    if not raw_segment or len(raw_segment) == 0:
        return None

    segment_id, *values = raw_segment.split(FIELD_SEPARATOR)

    segment_classes = [InsuranceSegment, PatientSegment]

    for segment_class in segment_classes:
        if segment_class.model_fields.get("segment_id").default == segment_id:
            result = map_values_to_keys(segment_class.get_key_mapping().default, values)
            return segment_class(**result)
    return None


class ClaimSegment(SegmentBase):
    segment_id: str = "AM07"


class PricingSegment(SegmentBase):
    segment_id: str = "AM11"


class PrescriberSegment(SegmentBase):
    segment_id: str = "AM03"


class PharmacyProviderSegment(SegmentBase):
    segment_id: str = "AM06"


class ClinicalSegment(SegmentBase):
    segment_id: str = "AM08"


class ClaimModel(BaseModel):
    header: EMIHeader
    insurance: InsuranceSegment | None = None
    patient: PatientSegment | None = None

    @classmethod
    def from_segments(cls, header: EMIHeader, segments: list[SegmentBase]) -> ClaimModel:
        claim_data = {"header": header}
        for segment in segments:
            if isinstance(segment, InsuranceSegment):
                claim_data["insurance"] = segment
            elif isinstance(segment, PatientSegment):
                claim_data["patient"] = segment
        return cls(**claim_data)


def main():
    raw_claim_data = pathlib.Path("RAW_Claim_Data.txt").read_text(encoding="utf-8")

    raw_header, *raw_segments = raw_claim_data.split(SEGMENT_SEPARATOR)
    header = "".join(raw_header.split())
    emi_header = EMIHeader.from_emi_string(header)

    segments = [parse_segment(segment.strip()) for segment in raw_segments]
    claim = ClaimModel.from_segments(emi_header, segments)

    print(claim)


if __name__ == "__main__":
    main()
