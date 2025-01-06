from __future__ import annotations

import pathlib
from enum import Enum, StrEnum

from pydantic import BaseModel, Field

HEADER_LENGTH = 31
FIELD_SEPARATOR = chr(28)  # File Separator <FS> / <0x1c>
GROUP_SEPARATOR = chr(29)  # Group Separator <GS> / <0x1d>
SEGMENT_SEPARATOR = chr(30)  # Record Separator <RS> / <0x1e>


class InsuranceSegment(BaseModel):
    segment_id: str = "AM04"


class PatientSegment(BaseModel):
    segment_id: str = "AM01"


class ClaimSegment(BaseModel):
    segment_id: str = "AM07"


class PricingSegment(BaseModel):
    segment_id: str = "AM11"


class PrescriberSegment(BaseModel):  # AM03
    segment_id: str = "AM03"
    prescriber_id: str
    prescriber_name: str | None = None
    contact_information: str | None = None


class PharmacyProviderSegment(BaseModel):  # AM06
    segment_id: str = "AM06"
    pharmacy_id: str
    pharmacy_name: str | None = None
    address: str | None = None


class ClinicalSegment(BaseModel):  # AM08
    segment_id: str = "AM08"
    prior_authorization_number: str | None = None
    drug_utilization_review: dict[str, str] | None = None
    clinical_codes: list[str] | None = None


class Segments(StrEnum):
    INSURANCE_SEGMENT = "AM04"
    PATIENT_SEGMENT = "AM01"
    CLAIM_SEGMENT = "AM07"
    PRICING_SEGMENT = "AM11"


class AMStatus(Enum):
    ACTIVE = "101"
    INACTIVE = "102"


class ABStatus(Enum):
    PENDING = "202"
    COMPLETED = "203"


# Base Pydantic model for parsed values
class ParsedValue(BaseModel):
    raw_value: str
    parsed_value: str

    @classmethod
    def parse_prefix(cls, value: str, prefix: str) -> str:
        if not value.startswith(prefix):
            raise ValueError(f"Value must start with prefix {prefix}")
        return value[len(prefix) :]


# Specific models for each prefix type
class ProviderID(ParsedValue):
    prefix: str = Field(default="C2", Literal=True)
    status: AMStatus | None = None

    @classmethod
    def from_raw(cls, value: str) -> ProviderID:
        parsed = cls.parse_prefix(value, "C2")
        status = AMStatus(parsed) if parsed in [e.value for e in AMStatus] else None
        return cls(raw_value=value, parsed_value=parsed, status=status)


class ProviderQualifier(ParsedValue):
    prefix: str = Field(default="C1", Literal=True)
    status: ABStatus | None = None

    @classmethod
    def from_raw(cls, value: str) -> ProviderQualifier:
        parsed = cls.parse_prefix(value, "C1")
        status = ABStatus(parsed) if parsed in [e.value for e in ABStatus] else None  # Only for enum values
        return cls(raw_value=value, parsed_value=parsed, status=status)


# Parser factory
class ValueParser:
    parsers = {"C2": ProviderID, "C1": ProviderQualifier}
    # parsers: dict[str, type[ParsedValue]] = {ProviderQualifier.prefix():
    # ProviderQualifier, ProviderID.prefix(): ProviderID}

    @classmethod
    def parse(cls, value: str) -> ParsedValue | None:
        prefix = value[0:2]
        parser = cls.parsers.get(prefix)
        if parser:
            return parser.from_raw(value)
        return None


def parse_claim(raw_claim: str):
    row: str = raw_claim.split(SEGMENT_SEPARATOR)[1]
    for segment in Segments:
        row = row.replace(segment, "")
    return [s for s in row.split(FIELD_SEPARATOR) if s]


def identify_segments(segments: list[str]) -> tuple[ClaimSegment, InsuranceSegment, PatientSegment, PricingSegment]:
    # TODO - Implement this function
    pass


def parse_header_values(input_string: str) -> tuple[str, str, str, str, str, str]:
    header_length: int = 31
    if len(input_string) != header_length:
        raise ValueError(f"Input string must be exactly {header_length} characters long.")

    rxbin = input_string[:6]
    version = input_string[6:8]
    transaction_code = input_string[8:10]
    processor_control = input_string[10:20]
    count = input_string[21:24]
    date = input_string[23:]

    return (rxbin, version, transaction_code, processor_control, count, date)


if __name__ == "__main__":
    values = pathlib.Path("RAW_Claim_Data.txt").read_text(encoding="utf-8")

    claim = values.split(SEGMENT_SEPARATOR)
    raw_header = "".join(claim[0].split())  #  We're mixing up claim and header variable names here.
    header = parse_header_values(raw_header)

    raw_segments = claim[1:]

    claim_seg: list[str] = raw_segments[1].strip().split(FIELD_SEPARATOR)
    segments = [segment.strip().split(SEGMENT_SEPARATOR) for segment in raw_segments]

    patient_info = parse_claim(values)

    for v in patient_info:
        p = ValueParser.parse(v)
        if p:
            print(f"Raw: {p.raw_value}")
            print(f"Parsed: {p.parsed_value}")
            print(f"Status: {p.status}")
            print("---")
