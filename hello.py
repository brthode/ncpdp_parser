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


# def decode_overpunch(value: str) -> int:
#     overpunch_map = {
#         "0": "0",
#         "1": "1",
#         "2": "2",
#         "3": "3",
#         "4": "4",
#         "5": "5",
#         "6": "6",
#         "7": "7",
#         "8": "8",
#         "9": "9",
#         "{": "0",
#         "A": "1",
#         "B": "2",
#         "C": "3",
#         "D": "4",
#         "E": "5",
#         "F": "6",
#         "G": "7",
#         "H": "8",
#         "I": "9",
#         "}": "0-",
#         "J": "1-",
#         "K": "2-",
#         "L": "3-",
#         "M": "4-",
#         "N": "5-",
#         "O": "6-",
#         "P": "7-",
#         "Q": "8-",
#         "R": "9-",
#     }

#     if not value:
#         raise ValueError("Value cannot be empty")

#     sign_char = value[-1]
#     number_part = value[:-1]
#     mapped = overpunch_map.get(sign_char.upper())
#     if mapped is None:
#         raise ValueError(f"Invalid overpunch character: {sign_char}")

#     if "-" in mapped:
#         return -int(number_part + mapped[0])
#     return int(number_part + mapped[0])


def encode_overpunch(value: int) -> str:
    overpunch_map = {
        0: "{",
        1: "A",
        2: "B",
        3: "C",
        4: "D",
        5: "E",
        6: "F",
        7: "G",
        8: "H",
        9: "I",
        -0: "}",
        -1: "J",
        -2: "K",
        -3: "L",
        -4: "M",
        -5: "N",
        -6: "O",
        -7: "P",
        -8: "Q",
        -9: "R",
    }

    str_value = str(abs(value))
    last_digit = int(str_value[-1]) * (1 if value >= 0 else -1)
    encoded_char = overpunch_map[last_digit]
    return str_value[:-1] + encoded_char


class TransactionCode(StrEnum):
    """Valid transaction codes for EMI headers."""

    SUBMISSION = "B1"
    REVERSAL = "B2"


class Gender(StrEnum):
    UNKNOWN = "0"
    MALE = "1"
    FEMALE = "2"


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
    def parse(cls, emi_string: str) -> EMIHeader:
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

    dob: datetime
    patient_gender: Gender
    last_name: str
    first_name: str
    patient_zip: str  # Include model validation for ZIP code

    _key_mapping: dict[str, str] = PrivateAttr(
        default={
            "C4": "dob",
            "C5": "patient_gender",
            "CA": "last_name",
            "CB": "first_name",
            "CP": "patient_zip",
        }
    )


@staticmethod
def parse_segment(
    raw_segment: str,
) -> InsuranceSegment | None:
    if not raw_segment or len(raw_segment) == 0:
        return None

    segment_id, *values = raw_segment.split(FIELD_SEPARATOR)

    segment_classes = [
        InsuranceSegment,
        PatientSegment,
        ClaimSegment,
        PricingSegment,
        PrescriberSegment,
        PharmacyProviderSegment,
        ClinicalSegment,
    ]

    for segment_class in segment_classes:
        if segment_class.model_fields.get("segment_id").default == segment_id:
            result = map_values_to_keys(segment_class.get_key_mapping().default, values)
            return segment_class(**result)
    return None


class ClaimSegment(SegmentBase):
    segment_id: str = "AM07"

    prescription_service_reference_number_qualifier: str
    prescription_service_reference_number: str
    product_service_id_qualifier: str
    product_service_id: str
    quantity_dispensed: str
    days_supply: str
    daw_product_selection_code: str
    date_written: str
    refills_authorized: str
    refill_number: str
    dateof_service: str
    levelof_service: str
    prescription_origin_code: str
    submission_clarification_code: str
    other_coverage_code: str

    _key_mapping: dict[str, str] = PrivateAttr(
        default={
            "EM": "prescription_service_reference_number_qualifier",
            "D2": "prescription_service_reference_number",
            "E1": "product_service_id_qualifier",
            "D7": "product_service_id",
            "SE": "quantity_dispensed",
            "E7": "days_supply",
            "D3": "daw_product_selection_code",
            "D5": "date_written",
            "D6": "refills_authorized",
            "D8": "refill_number",
            "DE": "dateof_service",
            "DF": "levelof_service",
            "DJ": "prescription_origin_code",
            "DT": "submission_clarification_code",
            "EB": "other_coverage_code",
        }
    )


class PricingSegment(SegmentBase):
    segment_id: str = "AM11"

    ingredient_cost_submitted: str  # Overpunch
    dispensing_fee_submitted: str  # Overpunch
    professional_service_fee_submitted: str  # Overpunch
    gross_amount_due: str  # Overpunch
    other_amount_claimed: str  # Overpunch

    _key_mapping: dict[str, str] = PrivateAttr(
        default={
            "D9": "ingredient_cost_submitted",
            "DC": "dispensing_fee_submitted",
            "E3": "professional_service_fee_submitted",
            "DQ": "gross_amount_due",
            "DU": "other_amount_claimed",
        }
    )

    def decode_overpunch(self, value: str) -> int | None:
        overpunch_map = {
            "0": "0",
            "1": "1",
            "2": "2",
            "3": "3",
            "4": "4",
            "5": "5",
            "6": "6",
            "7": "7",
            "8": "8",
            "9": "9",
            "{": "0",
            "A": "1",
            "B": "2",
            "C": "3",
            "D": "4",
            "E": "5",
            "F": "6",
            "G": "7",
            "H": "8",
            "I": "9",
            "}": "0-",
            "J": "1-",
            "K": "2-",
            "L": "3-",
            "M": "4-",
            "N": "5-",
            "O": "6-",
            "P": "7-",
            "Q": "8-",
            "R": "9-",
        }

        if not value:
            return None

        sign_char = value[-1]
        number_part = value[:-1]
        mapped = overpunch_map.get(sign_char.upper())
        if mapped is None:
            return None  # Optionally raise an error if invalid Overpunch is unacceptable.

        if "-" in mapped:
            return -int(number_part + mapped[0])
        return int(number_part + mapped[0])

    def _decoded_fields(self) -> dict[str, int | None]:
        """Decode Overpunch fields for representation."""
        return {field: self.decode_overpunch(getattr(self, field)) for field in self._key_mapping.values()}

    def __repr__(self) -> str:
        decoded = self._decoded_fields()
        return (
            f"PricingSegment(segment_id={self.segment_id}, "
            + ", ".join(f"{field}={value}" for field, value in decoded.items())
            + ")"
        )

    def __str__(self) -> str:
        return self.__repr__()


class PrescriberSegment(SegmentBase):
    segment_id: str = "AM03"

    prescriber_id_qualifier: str
    prescriber_id: str

    _key_mapping: dict[str, str] = PrivateAttr(
        default={
            "EZ": "prescriber_id_qualifier",  # Prescriber Identification Qualifier
            "DB": "prescriber_id",  # Prescriber Identification
        }
    )


class PharmacyProviderSegment(SegmentBase):
    segment_id: str = "AM06"

    group_id: str

    _key_mapping: dict[str, str] = PrivateAttr(
        default={
            "DZ": "group_id",
        }
    )


class ClinicalSegment(SegmentBase):
    segment_id: str = "AM08"

    other_payer_coverage_type: str
    other_payer_id_qualifier: str

    _key_mapping: dict[str, str] = PrivateAttr(
        default={"7E": "other_payer_coverage_type", "E5": "other_payer_id_qualifier"}
    )


class ClaimModel(BaseModel):
    header: EMIHeader  # Transaction Header Segment
    insurance: InsuranceSegment  # Insurance Segment
    patient: PatientSegment | None = None  # Patient Segment
    claim: ClaimSegment  # Claim Segment
    pricing: PricingSegment  # Pricing Segment
    prescriber: PrescriberSegment | None = None
    pharmacy_provider: PharmacyProviderSegment | None = None
    clinical: ClinicalSegment | None = None

    # --- Optional Segments ---
    # Pharmacy Provider Segment
    # Prescriber Segment
    # Coordination of Benefits/Other Payments Segment
    # Workers’ Compensation Segment
    # DUR/PPS Segment
    # Compound Segment
    # Clinical Segment
    # Additional Documentation Segment
    # Facility Segment
    # Narrative Segment
    # Intermediary Segment

    @classmethod
    def from_segments(cls, header: EMIHeader, segments: list[SegmentBase]) -> ClaimModel:
        claim_data = {"header": header}
        for segment in segments:
            if isinstance(segment, InsuranceSegment):
                claim_data["insurance"] = segment
            elif isinstance(segment, PatientSegment):
                claim_data["patient"] = segment
            elif isinstance(segment, ClaimSegment):
                claim_data["claim"] = segment
            elif isinstance(segment, PricingSegment):
                claim_data["pricing"] = segment
            elif isinstance(segment, PrescriberSegment):
                claim_data["prescriber"] = segment
            elif isinstance(segment, PharmacyProviderSegment):
                claim_data["pharmacy_provider"] = segment
            elif isinstance(segment, ClinicalSegment):
                claim_data["clinical"] = segment
        return cls(**claim_data)


def main():
    raw_claim_data = pathlib.Path("RAW_Claim_Data.txt").read_text(encoding="utf-8")

    raw_header, *raw_segments = raw_claim_data.split(SEGMENT_SEPARATOR)
    header = "".join(raw_header.split())
    emi_header = EMIHeader.parse(header)

    segments = [parse_segment(segment.strip()) for segment in raw_segments]
    claim = ClaimModel.from_segments(emi_header, segments)

    print(claim)


if __name__ == "__main__":
    main()
