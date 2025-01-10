from __future__ import annotations

import pathlib
import random
from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Annotated, NamedTuple, Self

from polyfactory.factories.pydantic_factory import ModelFactory
from pydantic import BaseModel, Field, PrivateAttr, StringConstraints, field_validator

NCPDP_HEADER_LENGTH = 56
FIELD_SEPARATOR = chr(28)  # File Separator <FS> / <0x1c>
GROUP_SEPARATOR = chr(29)  # Group Separator <GS> / <0x1d>
SEGMENT_SEPARATOR = chr(30)  # Record Separator <RS> / <0x1e>


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
    """Valid transaction codes."""

    SUBMISSION = "B1"
    REVERSAL = "B2"


class Gender(StrEnum):
    UNKNOWN = "0"
    MALE = "1"
    FEMALE = "2"


class Version(StrEnum):
    """Valid version codes for claim headers."""

    MODERN = "D0"  # Current version code
    LEGACY = "51"  # Legacy version code


class PaddingDirection(StrEnum):
    """Direction to apply padding for fixed width fields"""

    LEFT = "left"
    RIGHT = "right"


class NCPDPPosition(NamedTuple):
    """Position and length for NCPDP fixed width fields"""

    start: int
    length: int
    padding: PaddingDirection = PaddingDirection.LEFT

    @property
    def end(self) -> int:
        """Calculate end position based on start and length"""
        return self.start + self.length

    def slice(self, data: str) -> str:
        """Extract field from string using position"""
        return data[self.start : self.end].strip()

    def pad(self, value: str | None) -> str:
        """Pad value to required length with proper alignment"""
        if value is None:
            value = ""
        if len(value) > self.length:
            raise ValueError(f"Value '{value}' exceeds maximum length of {self.length}")

        if self.padding == PaddingDirection.LEFT:
            return value.rjust(self.length)
        return value.ljust(self.length)


class NCPDPFormat:
    """NCPDP fixed width format field positions and lengths"""

    IIN = NCPDPPosition(0, 6, PaddingDirection.RIGHT)
    VERSION = NCPDPPosition(6, 2)
    TRANSACTION_CODE = NCPDPPosition(8, 2)
    PCN = NCPDPPosition(10, 10, PaddingDirection.RIGHT)
    TRANSACTION_COUNT = NCPDPPosition(20, 1)
    SERVICE_PROVIDER_ID_QUAL = NCPDPPosition(21, 2)
    SERVICE_PROVIDER_ID = NCPDPPosition(23, 15, PaddingDirection.RIGHT)
    SERVICE_DATE = NCPDPPosition(38, 8)
    CERTIFICATION_ID = NCPDPPosition(46, 10, PaddingDirection.RIGHT)

    @classmethod
    def total_width(cls) -> int:
        """Calculate total width of all fields"""
        return max(
            pos.end
            for pos in [
                cls.IIN,
                cls.VERSION,
                cls.TRANSACTION_CODE,
                cls.PCN,
                cls.TRANSACTION_COUNT,
                cls.SERVICE_PROVIDER_ID_QUAL,
                cls.SERVICE_PROVIDER_ID,
                cls.SERVICE_DATE,
                cls.CERTIFICATION_ID,
            ]
        )


class NCPDPClaimHeader(BaseModel):
    """NCPDP header fields with parsing and serialization"""

    iin: Annotated[str, StringConstraints(pattern=r"^\d{6}$")] = Field(
        description="6-digit BIN number"
    )  # Issuer Identification Number
    version: str  # Version Number
    transaction_code: str  # Transaction Code
    pcn: str | None = Field(default=None, max_length=10)
    #     description="10-character processor control number that can be spaces and/or digits",
    #     min_length=10,
    #     max_length=10,
    # )
    transaction_count: Annotated[str, StringConstraints(pattern=r"^[1-9]$")]  # Transaction Count
    service_provider_id_qual: Annotated[
        str, StringConstraints(pattern=r"^[0-9][0-9]?$")
    ]  # Service Provider ID Qualifier
    service_provider_id: str | None = Field(default=None, max_length=15)  # Service Provider ID
    service_date: Annotated[str, StringConstraints(pattern=r"^\d{4}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$")]
    # Service Date
    certification_id: str = Field(default=None, max_length=10)  # Certification ID (Can be empty)

    @classmethod
    def parse(cls, emi_string: str) -> Self:
        """Parse EMI string into NCPDP header fields"""
        format = NCPDPFormat
        if len(emi_string) < format.total_width():
            raise ValueError(f"Input string too short. Expected at least {format.total_width()} characters")

        return cls(
            iin=format.IIN.slice(emi_string),
            version=format.VERSION.slice(emi_string),
            transaction_code=format.TRANSACTION_CODE.slice(emi_string),
            pcn=format.PCN.slice(emi_string),
            transaction_count=format.TRANSACTION_COUNT.slice(emi_string),
            service_provider_id_qual=format.SERVICE_PROVIDER_ID_QUAL.slice(emi_string),
            service_provider_id=format.SERVICE_PROVIDER_ID.slice(emi_string),
            service_date=format.SERVICE_DATE.slice(emi_string),
            certification_id=format.CERTIFICATION_ID.slice(emi_string),
        )

    def serialize(self) -> str:
        """Convert header fields back to fixed-width format string"""
        format = NCPDPFormat
        return (
            format.IIN.pad(self.iin)
            + format.VERSION.pad(self.version)
            + format.TRANSACTION_CODE.pad(self.transaction_code)
            + format.PCN.pad(self.pcn)
            + format.TRANSACTION_COUNT.pad(self.transaction_count)
            + format.SERVICE_PROVIDER_ID_QUAL.pad(self.service_provider_id_qual)
            + format.SERVICE_PROVIDER_ID.pad(self.service_provider_id)
            + format.SERVICE_DATE.pad(self.service_date)
            + format.CERTIFICATION_ID.pad(self.certification_id)
        )

    # @model_validator(mode="after")
    def validate_pcn_format(self) -> NCPDPClaimHeader:
        """Validates PCN after all fields are populated."""
        # If PCN was an empty string (from stripping whitespace),
        # restore it to 10 spaces
        if not self.pcn:
            self.pcn = " " * 10
            return self

        # For non-empty strings, validate length and content
        if len(self.pcn) != 10:
            raise ValueError("PCN must be exactly 10 characters")

        if not all(c.isspace() or c.isdigit() for c in self.pcn):
            raise ValueError("PCN must contain only spaces and digits")

        return self


class SegmentBase(ABC, BaseModel):
    """Abstract base class for all segments."""

    @classmethod
    def get_key_mapping(cls) -> dict[str, str]:
        return cls._key_mapping

    @abstractmethod
    def serialize(self) -> str:
        raise NotImplementedError


def map_values_to_keys(segment_mapping: dict[str, str], values: list[str]) -> dict[str, str]:
    return {segment_mapping[prefix]: value[2:] for value in values if (prefix := value[:2]) in segment_mapping}


class InsuranceSegment(SegmentBase):
    def serialize(self) -> str:
        """Serializes the InsuranceSegment to a string."""
        values = [
            self.segment_id,
            f"C2{self.internal_control_number}",
            f"C1{self.first_name}",
            f"C3{self.person_code}",
            f"A6{self.cardholder_id}",
            f"A7{self.last_name}",
        ]
        return FIELD_SEPARATOR + FIELD_SEPARATOR.join(values)

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

    def serialize(self) -> str:
        """Serializes the PatientSegment to a string."""
        values = [
            self.segment_id,
            f"C4{self.dob.strftime('%Y%m%d')}",
            f"C5{self.patient_gender}",
            f"CA{self.last_name}",
            f"CB{self.first_name}",
            f"CP{self.patient_zip}",
        ]
        return FIELD_SEPARATOR + FIELD_SEPARATOR.join(values)

    @field_validator("dob", mode="before")
    @classmethod
    def parse_date(cls, value: str) -> datetime:
        if isinstance(value, datetime):
            return value
        date_format = "%Y%m%d"  # Specify the format "YYYYMMDD"
        try:
            return datetime.strptime(value, date_format)
        except ValueError as exc:
            raise ValueError(f"Date must be in the format {date_format}") from exc


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
            return segment_class(**result)  # TODO: dob is still 1950 here
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

    def serialize(self) -> str:
        """Serializes the ClaimSegment to a string."""
        values = [
            self.segment_id,
            f"EM{self.prescription_service_reference_number_qualifier}",
            f"D2{self.prescription_service_reference_number}",
            f"E1{self.product_service_id_qualifier}",
            f"D7{self.product_service_id}",
            f"SE{self.quantity_dispensed}",
            f"E7{self.days_supply}",
            f"D3{self.daw_product_selection_code}",
            f"D5{self.date_written}",
            f"D6{self.refills_authorized}",
            f"D8{self.refill_number}",
            f"DE{self.dateof_service}",
            f"DF{self.levelof_service}",
            f"DJ{self.prescription_origin_code}",
            f"DT{self.submission_clarification_code}",
            f"EB{self.other_coverage_code}",
        ]
        return FIELD_SEPARATOR + FIELD_SEPARATOR.join(values)


class PricingSegment(SegmentBase):
    segment_id: str = "AM11"

    # Implied decimle point
    # TODO: We should display this as flaots

    ingredient_cost_submitted: Annotated[str, StringConstraints(pattern=r"^\d+[A-IJ-R{}]$")] = Field(
        description="Ingredient cost in Overpunch format"
    )

    dispensing_fee_submitted: Annotated[str, StringConstraints(pattern=r"^\d+[A-IJ-R{}]$")] = Field(
        description="Dispensing fee in Overpunch format"
    )

    professional_service_fee_submitted: Annotated[str, StringConstraints(pattern=r"^\d+[A-IJ-R{}]$")] = Field(
        description="Professional service fee in Overpunch format"
    )

    gross_amount_due: Annotated[str, StringConstraints(pattern=r"^\d+[A-IJ-R{}]$")] = Field(
        description="Gross amount due in Overpunch format"
    )

    other_amount_claimed: Annotated[str, StringConstraints(pattern=r"^\d+[A-IJ-R{}]$")] = Field(
        description="Other amount claimed in Overpunch format"
    )

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
        if mapped is None:  # Invalid overpunch character
            return None  # TODO: Raise error?

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

    def serialize(self) -> str:
        """Serializes the PricingSegment to a string."""
        values = [
            self.segment_id,
            f"D9{self.ingredient_cost_submitted}",
            f"DC{self.dispensing_fee_submitted}",
            f"E3{self.professional_service_fee_submitted}",
            f"DQ{self.gross_amount_due}",
            f"DU{self.other_amount_claimed}",
        ]
        return FIELD_SEPARATOR + FIELD_SEPARATOR.join(values)


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

    def serialize(self) -> str:
        """Serializes the PrescriberSegment to a string."""
        values = [
            self.segment_id,
            f"EZ{self.prescriber_id_qualifier}",
            f"DB{self.prescriber_id}",
        ]
        return FIELD_SEPARATOR + FIELD_SEPARATOR.join(values)


class PharmacyProviderSegment(SegmentBase):
    segment_id: str = "AM06"

    group_id: str

    _key_mapping: dict[str, str] = PrivateAttr(
        default={
            "DZ": "group_id",
        }
    )

    def serialize(self) -> str:
        """Serializes the PharmacyProviderSegment to a string."""
        values = [
            self.segment_id,
            f"DZ{self.group_id}",
        ]
        return FIELD_SEPARATOR + FIELD_SEPARATOR.join(values)


class ClinicalSegment(SegmentBase):
    segment_id: str = "AM08"

    other_payer_coverage_type: str
    other_payer_id_qualifier: str

    _key_mapping: dict[str, str] = PrivateAttr(
        default={"7E": "other_payer_coverage_type", "E5": "other_payer_id_qualifier"}
    )

    def serialize(self) -> str:
        """Serializes the ClinicalSegment to a string."""
        values = [
            self.segment_id,
            f"7E{self.other_payer_coverage_type}",
            f"E5{self.other_payer_id_qualifier}",
        ]
        return FIELD_SEPARATOR + FIELD_SEPARATOR.join(values)


class ClaimModel(BaseModel):
    header: NCPDPClaimHeader  # Transaction Header Segment
    insurance: InsuranceSegment  # Insurance Segment
    patient: PatientSegment | None = None  # Patient Segment
    claim: ClaimSegment  # Claim Segment
    pricing: PricingSegment  # Pricing Segment
    prescriber: PrescriberSegment | None = None
    pharmacy_provider: PharmacyProviderSegment | None = None
    clinical: ClinicalSegment | None = None

    # Future segments
    # DUR/PPS Segment - Basic clinical information
    # Compound Segment

    # --- Optional Segments ---
    # Pharmacy Provider Segment
    # Prescriber Segment
    # Coordination of Benefits/Other Payments Segment
    # Workers’ Compensation Segment
    # Clinical Segment
    # Additional Documentation Segment
    # Facility Segment
    # Narrative Segment
    # Intermediary Segment

    @classmethod
    def from_segments(cls, header: NCPDPClaimHeader, segments: list[SegmentBase]) -> ClaimModel:
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

    def serialize(self) -> str:
        """Serializes the ClaimModel to a string."""
        segments = [
            self.header.serialize(),
            self.insurance.serialize(),
            self.patient.serialize() + GROUP_SEPARATOR,  # Separates Patient and Claim segments
            self.claim.serialize(),
            self.pricing.serialize(),
            self.prescriber.serialize(),
            self.pharmacy_provider.serialize(),
            self.clinical.serialize(),
        ]
        return SEGMENT_SEPARATOR.join(segments)


class NCPDPClaimHeaderFactory(ModelFactory[NCPDPClaimHeader]):
    """Factory for generating test NCPDPHeader instances."""

    __model__ = NCPDPClaimHeader

    version = Version.MODERN  # Use modern version
    transaction_code = TransactionCode.SUBMISSION  # Use submission transaction code
    service_date = datetime.now().strftime("%Y%m%d")

    @classmethod
    def pcn(cls) -> str:
        """Generate a valid PCN with varying combinations of spaces and digits."""

        # Define possible PCN patterns:
        patterns = [
            " " * 10,  # All spaces
            "1" + " " * 9,  # One digit, rest spaces
            "12" + " " * 8,  # Two digits, rest spaces
            "123" + " " * 7,  # Three digits, rest spaces
            "1234567890",  # All digits
        ]
        return random.choice(patterns)


class InsuranceSegmentFactory(ModelFactory[InsuranceSegment]):
    """Factory for generating test InsuranceSegment instances."""

    __model__ = InsuranceSegment
    segment_id = "AM04"

    # first_name = "John"
    # last_name = "Doe"
    # person_code = "01"
    # cardholder_id = "1234567890"
    # internal_control_number = "1234567890"


class PatientSegmentFactory(ModelFactory[PatientSegment]):
    """Factory for generating test PatientSegment instances."""

    __model__ = PatientSegment
    segment_id = "AM01"

    @classmethod
    def dob(cls) -> datetime:
        """Generate a date of birth with only year, month, and day."""
        return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


class ClaimSegmentFactory(ModelFactory[ClaimSegment]):
    """Factory for generating test ClaimSegment instances."""

    __model__ = ClaimSegment
    segment_id: str = "AM07"

    # prescription_service_reference_number_qualifier = "EM"
    # prescription_service_reference_number = "1234567890"
    # product_service_id_qualifier = "E1"
    # product_service_id = "1234567890"
    # quantity_dispensed = "1"
    # days_supply = "30"
    # daw_product_selection_code = "0"
    # date_written = "20220101"
    # refills_authorized = "0"
    # refill_number = "0"
    # dateof_service = "20220101"
    # levelof_service = "1"
    # prescription_origin_code = "1"
    # submission_clarification_code = "1"
    # other_coverage_code = "1"


class PricingSegmentFactory(ModelFactory[PricingSegment]):
    """Factory for generating test PricingSegment instances."""

    __model__ = PricingSegment
    segment_id: str = "AM11"

    # ingredient_cost_submitted = "1234567890"
    # dispensing_fee_submitted = "1234567890"
    # professional_service_fee_submitted = "1234567890"
    # gross_amount_due = "1234567890"
    # other_amount_claimed = "1234567890"


class PrescriberSegmentFactory(ModelFactory[PrescriberSegment]):
    """Factory for generating test PrescriberSegment instances."""

    __model__ = PrescriberSegment
    segment_id = "AM03"
    # prescriber_id_qualifier = "EZ"
    # prescriber_id = "1234567890"


class PharmacyProviderSegmentFactory(ModelFactory[PharmacyProviderSegment]):
    """Factory for generating test PharmacyProviderSegment instances."""

    __model__ = PharmacyProviderSegment
    segment_id = "AM06"

    # group_id = "1234567890"


class ClinicalSegmentFactory(ModelFactory[ClinicalSegment]):
    """Factory for generating test ClinicalSegment instances."""

    __model__ = ClinicalSegment
    segment_id = "AM08"

    # other_payer_coverage_type = "7E"
    # other_payer_id_qualifier = "E5"


class ClaimModelFactory(ModelFactory[ClaimModel]):
    """Factory for generating test ClaimModel instances."""

    __model__ = ClaimModel

    header = NCPDPClaimHeaderFactory.build()
    insurance = InsuranceSegmentFactory.build()
    patient = PatientSegmentFactory.build()
    claim = ClaimSegmentFactory.build()
    pricing = PricingSegmentFactory.build()
    prescriber = PrescriberSegmentFactory.build()
    pharmacy_provider = PharmacyProviderSegmentFactory.build()
    clinical = ClinicalSegmentFactory.build()

    @classmethod
    def build(cls, *args, **kwargs) -> ClaimModel:
        """Builds a ClaimModel instance with all segments."""
        return cls.__model__(
            *args,
            **kwargs,
            header=cls.header,
            insurance=cls.insurance,
            patient=cls.patient,
            claim=cls.claim,
            pricing=cls.pricing,
            prescriber=cls.prescriber,
            pharmacy_provider=cls.pharmacy_provider,
            clinical=cls.clinical,
        )


def parse_claim_file():
    raw_claim_data = pathlib.Path("RAW_Claim_Data.txt").read_text(encoding="utf-8")

    header, *raw_segments = raw_claim_data.split(SEGMENT_SEPARATOR)
    claim_header = NCPDPClaimHeader.parse(header)

    segments = [parse_segment(segment.strip()) for segment in raw_segments]
    claim = ClaimModel.from_segments(claim_header, segments)

    print(claim)


def test_parsed_claim_matches_serialized():
    raw_claim_data = pathlib.Path("RAW_Claim_Data.txt").read_text(encoding="utf-8")

    header, *raw_segments = raw_claim_data.split(SEGMENT_SEPARATOR)
    claim_header = NCPDPClaimHeader.parse(header)

    segments = [parse_segment(segment.strip()) for segment in raw_segments]
    claim = ClaimModel.from_segments(claim_header, segments)

    # TODO
    with open("SER_CLAIM_DATA.txt", "w", encoding="utf-8") as file:
        file.write(claim.serialize())
    assert claim.serialize() == raw_claim_data


def main():
    parse_claim_file()
    test_parsed_claim_matches_serialized()
    breakpoint()

    claim = NCPDPClaimHeaderFactory.build()
    builder_claim = ClaimModelFactory.build()
    print(builder_claim)

    print(claim)

    # Produce a test claim using the factory
    original_claim = ClaimModelFactory.build()
    original_serialized = original_claim.serialize()

    # Then parse the claim back into a model
    header, *raw_segments = original_serialized.split(SEGMENT_SEPARATOR)
    claim_header = NCPDPClaimHeader.parse(header)

    segments: list[SegmentBase] = []
    for segment in raw_segments:
        trimmed_segment = segment.strip()
        if segment_id := trimmed_segment.split(FIELD_SEPARATOR)[0]:
            match segment_id:
                case "AM04":  # Insurance
                    segments.append(parse_segment(trimmed_segment))
                case "AM01":  # Patient
                    segments.append(parse_segment(trimmed_segment))
                case "AM07":  # Claim
                    segments.append(parse_segment(trimmed_segment))
                case "AM11":  # Pricing
                    segments.append(parse_segment(trimmed_segment))
                case "AM03":  # Prescriber
                    segments.append(parse_segment(trimmed_segment))
                case "AM06":  # Pharmacy Provider
                    segments.append(parse_segment(trimmed_segment))
                case "AM08":  # Clinical
                    segments.append(parse_segment(trimmed_segment))
    parsed_claim = ClaimModel.from_segments(claim_header, segments)

    assert original_claim.insurance == parsed_claim.insurance

    assert original_claim.patient == parsed_claim.patient
    assert original_claim.claim == parsed_claim.claim
    assert original_claim.pricing == parsed_claim.pricing
    assert original_claim.prescriber == parsed_claim.prescriber
    assert original_claim.pharmacy_provider == parsed_claim.pharmacy_provider
    assert original_claim.clinical == parsed_claim.clinical

    assert original_claim.header == parsed_claim.header
    assert original_claim == parsed_claim, "Parsed claim does not match original"


if __name__ == "__main__":
    main()
