from __future__ import annotations

import pathlib
from abc import ABC
from enum import Enum, StrEnum
from typing import Any

from pydantic import BaseModel, Field

HEADER_LENGTH = 31
FIELD_SEPARATOR = chr(28)  # File Separator <FS> / <0x1c>
GROUP_SEPARATOR = chr(29)  # Group Separator <GS> / <0x1d>
SEGMENT_SEPARATOR = chr(30)  # Record Separator <RS> / <0x1e>


class AbstractSegment(ABC):
    @property
    def values(self) -> dict[str, str]:
        raise NotImplementedError("Subclasses must implement values property")

    def __init__(self, values: dict[str, str]):
        self._values = values

    @classmethod
    def parse(cls, data: dict[str, str]) -> AbstractSegment:
        return cls(values=data)


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
    first_name: str | None = None
    last_name: str | None = None

    # Define a mapping of external keys to model attributes
    key_mapping: dict[str, str] = {
        "C1": "prior_authorization_number",
        "C2": "first_name",
        "C3": "last_name",
        "C4": "clinical_codes",
        "C5": "drug_utilization_review",
    }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClinicalSegment:
        """
        Creates an instance of ClinicalSegment from a dictionary,
        mapping external keys to the model's attributes.
        """
        mapped_data = {}
        for key, value in data.items():
            attribute_name = cls.key_mapping.get(key)
            if attribute_name:
                # Handle type casting for list and dict attributes
                if attribute_name == "clinical_codes" and isinstance(value, str):
                    mapped_data[attribute_name] = value.split(",")  # Assuming comma-separated codes
                elif attribute_name == "drug_utilization_review" and isinstance(value, str):
                    mapped_data[attribute_name] = {
                        k.strip(): v.strip() for k, v in (item.split(":") for item in value.split(","))
                    }
                else:
                    mapped_data[attribute_name] = value

        return cls(**mapped_data)

    @classmethod
    def from_list(cls, data: list[str]) -> ClinicalSegment:
        """
        Creates an instance of ClinicalSegment from a list of strings,
        where each string consists of a two-character key followed by the value.
        """
        # Use `cls.__fields__` to ensure compatibility
        field_mapping = cls.key_mapping
        mapped_data = {}
        for item in data:
            if len(item) < 3:  # Ensure there's at least a key and some value
                continue
            key = item[:2]  # Extract the two-character key
            value = item[2:]  # Extract the value
            attribute_name = field_mapping.get(key)
            if attribute_name:
                # Handle type casting for list and dict attributes
                if attribute_name == "clinical_codes":
                    mapped_data[attribute_name] = value.split(",")  # Assuming comma-separated codes
                elif attribute_name == "drug_utilization_review":
                    mapped_data[attribute_name] = {
                        k.strip(): v.strip() for k, v in (item.split(":") for item in value.split(","))
                    }
                else:
                    mapped_data[attribute_name] = value

        return cls(**mapped_data)


class SegmentCollection(BaseModel):
    insurance_segment: InsuranceSegment
    patient_segment: PatientSegment
    claim_segment: ClaimSegment
    pricing_segment: PricingSegment
    prescriber_segment: PrescriberSegment
    pharmacy_provider_segment: PharmacyProviderSegment
    clinical_segment: ClinicalSegment


class Claim(BaseModel):
    segment_collection: SegmentCollection


@staticmethod
def parse_segment(
    raw_segment: str,
) -> (
    PatientSegment
    | InsuranceSegment
    | ClaimSegment
    | PricingSegment
    | PrescriberSegment
    | PharmacyProviderSegment
    | ClinicalSegment
    | None
):
    if not raw_segment or len(raw_segment) == 0:
        return None

    segment_id = raw_segment.split(FIELD_SEPARATOR)[0]
    values = raw_segment.split(FIELD_SEPARATOR)[1:]

    segment_classes = [
        PatientSegment,
        InsuranceSegment,
        ClaimSegment,
        PricingSegment,
        PrescriberSegment,
        PharmacyProviderSegment,
        ClinicalSegment,
    ]

    for segment_class in segment_classes:
        if segment_class.__fields__["segment_id"].default == segment_id:
            if segment_class == PrescriberSegment:
                return segment_class(prescriber_id=raw_segment[1])
            elif segment_class == PharmacyProviderSegment:
                return segment_class(pharmacy_id=raw_segment[1])
            else:
                return segment_class().from_list(values)
    return None


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
    raw_header = "".join(claim[0].split())
    header = parse_header_values(raw_header)

    raw_segments = claim[1:]

    claim_seg: list[str] = raw_segments[1].strip().split(FIELD_SEPARATOR)
    segments = [segment.strip() for segment in raw_segments]

    patient_info = parse_claim(values)

    z1 = parse_segment(segments[6])  # InsuranceSegment
    print(type(z1))

    for v in patient_info:
        p = ValueParser.parse(v)
        if p:
            print(f"Raw: {p.raw_value}")
            print(f"Parsed: {p.parsed_value}")
            print(f"Status: {p.status}")
            print("---")
