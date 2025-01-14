from __future__ import annotations

import pathlib
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Annotated, NamedTuple, Self

from polyfactory.factories.pydantic_factory import ModelFactory
from pydantic import BaseModel, Field, PrivateAttr, StringConstraints, field_validator

NCPDP_HEADER_LENGTH = 56
FIELD_SEPARATOR = chr(28)  # File Separator <FS> / <0x1c>
GROUP_SEPARATOR = chr(29)  # Group Separator <GS> / <0x1d>
SEGMENT_SEPARATOR = chr(30)  # Record Separator <RS> / <0x1e>


class TransactionCode(StrEnum):
    """Valid transaction codes. (A3)"""

    BILLING = "B1"
    REVERSAL = "B2"
    REBILL = "B3"
    CONTROLLED_SUBSTANCE_REPORTING = "C1"
    CONTROLLED_SUBSTANCE_REVERSAL = "C2"
    CONTROLLED_SUBSTANCE_REBILL = "C3"
    PREDETERMINATION_OF_BENEFITS = "D1"
    ELIGIBILITY_VERIFICATION = "E1"
    INFORMATION_REPORTING = "N1"
    INFORMATION_REPORTING_REVERSAL = "N2"
    INFORMATION_REPORTING_REBILL = "N3"
    PA_REQUEST_AND_BILLING = "P1"
    PA_REVERSAL = "P2"
    PA_INQUIRY = "P3"
    PA_REQUEST_ONLY = "P4"
    SERVICE_BILLING = "S1"
    SERVICE_REVERSAL = "S2"
    SERVICE_REBILL = "S3"
    FINANCIAL_INFO_REPORTING_INQUIRY = "F1"
    FINANCIAL_INFO_REPORTING_UPDATE = "F2"
    FINANCIAL_INFO_REPORTING_EXCHANGE = "F3"


class PrescriptionServiceReferenceNumberQualifier(StrEnum):
    RX_BILLING = "01"
    SERVICE_BILLING = "02"
    NON_PRESCRIPTION_PRODUCT = "03"


class ProductServiceIdQualifier(StrEnum):
    """Valid prescription service reference number qualifiers. (E1)"""

    NOT_SPECIFIED = "00"
    UPC = "01"
    HRI = "02"
    NDC = "03"
    HIBCC = "04"
    DUR_PPS = "06"
    CPT_4 = "07"
    CPT5 = "08"
    HCPCS = "09"
    PPAC = "10"
    NAPPI = "11"
    GTIN = "12"
    GCN = "15"
    FDB_MED_NAME_ID = "28"
    FDB_ROUTED_MED_ID = "29"
    FDB_ROUTED_DOSAGE_FORM_MED_ID = "30"
    FDB_MED_ID = "31"
    GCN_SEQNO = "32"
    HICL_SEQNO = "33"
    UPN = "34"
    NDC_36 = "36"
    MPID = "42"
    PROD_ID = "43"
    SPID = "44"
    DI = "45"
    OTHER = "99"


class SpecialPackagingIndicator(StrEnum):
    NOT_SPECIFIED = "0"
    NOT_UNIT_DOSE = "1"
    MANUFACTURER_UNIT_DOSE = "2"
    PHARMACY_UNIT_DOSE = "3"
    PHARMACY_UNIT_DOSE_PATIENT_COMPLIANCE_PACKAGING = "4"
    PHARMACY_MULTI_DRUG_PATIENT_COMPLIANCE_PACKAGING = "5"
    REMOTE_DEVICE_UNIT_DOSE = "6"
    REMOTE_DEVICE_MULTI_DRUG_COMPLIANCE = "7"
    MANUFACTURER_UNIT_OF_USE_PACKAGE = "8"


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

    RXBIN = NCPDPPosition(0, 6, PaddingDirection.RIGHT)
    VERSION = NCPDPPosition(6, 2)
    TRANSACTION_CODE = NCPDPPosition(8, 2)
    PCN = NCPDPPosition(10, 10, PaddingDirection.RIGHT)
    TRANSACTION_COUNT = NCPDPPosition(20, 1)
    SERVICE_PROVIDER_ID_QUAL = NCPDPPosition(21, 2)
    SERVICE_PROVIDER_ID = NCPDPPosition(23, 15, PaddingDirection.RIGHT)
    SERVICE_DATE = NCPDPPosition(38, 8)
    CERTIFICATION_ID = NCPDPPosition(46, 10, PaddingDirection.RIGHT)


class NCPDPClaimHeader(BaseModel):
    """NCPDP header fields with parsing and serialization"""

    rxbin: Annotated[str, StringConstraints(pattern=r"^\d{6}$")] = Field(
        description="6-digit BIN number"
    )  # Issuer Identification Number

    version: Version = Field(description="Version code (D0 or 51)")  # Version Number

    transaction_code: TransactionCode = Field(description="Transaction type (B1 for submission, B2 for reversal)")

    pcn: str | None = Field(default=None, max_length=10)

    transaction_count: Annotated[str, StringConstraints(pattern=r"^[1-9]$")]  # Transaction Count

    service_provider_id_qual: Annotated[
        str, StringConstraints(pattern=r"^[0-9][0-9]?$")
    ]  # Service Provider ID Qualifier
    service_provider_id: str | None = Field(default=None, max_length=15)  # Service Provider ID

    service_date: Annotated[str, StringConstraints(pattern=r"^\d{4}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$")]
    # Service Date

    certification_id: str | None = Field(default=None, max_length=10)  # Certification ID

    @classmethod
    def parse(cls, emi_string: str) -> Self:
        """Parse EMI string into NCPDP header fields"""
        format = NCPDPFormat
        if len(emi_string) < NCPDP_HEADER_LENGTH:
            raise ValueError(f"Input string too short. Expected at least {NCPDP_HEADER_LENGTH} characters")

        pcn = None if format.PCN.slice(emi_string).strip() == "" else format.PCN.slice(emi_string)
        service_provider_id = (
            None
            if format.SERVICE_PROVIDER_ID.slice(emi_string).strip() == ""
            else format.SERVICE_PROVIDER_ID.slice(emi_string)
        )

        certification_id = (
            None
            if format.CERTIFICATION_ID.slice(emi_string).strip() == ""
            else format.CERTIFICATION_ID.slice(emi_string)
        )

        return cls(
            rxbin=format.RXBIN.slice(emi_string),
            version=Version(format.VERSION.slice(emi_string)),
            transaction_code=TransactionCode(format.TRANSACTION_CODE.slice(emi_string)),
            pcn=pcn,
            transaction_count=format.TRANSACTION_COUNT.slice(emi_string),
            service_provider_id_qual=format.SERVICE_PROVIDER_ID_QUAL.slice(emi_string),
            service_provider_id=service_provider_id,
            service_date=format.SERVICE_DATE.slice(emi_string),
            certification_id=certification_id,
        )

    def serialize(self) -> str:
        """Convert header fields back to fixed-width format string"""
        format = NCPDPFormat
        return (
            format.RXBIN.pad(self.rxbin)
            + format.VERSION.pad(self.version)
            + format.TRANSACTION_CODE.pad(self.transaction_code)
            + format.PCN.pad(self.pcn)
            + format.TRANSACTION_COUNT.pad(self.transaction_count)
            + format.SERVICE_PROVIDER_ID_QUAL.pad(self.service_provider_id_qual)
            + format.SERVICE_PROVIDER_ID.pad(self.service_provider_id)
            + format.SERVICE_DATE.pad(self.service_date)
            + format.CERTIFICATION_ID.pad(self.certification_id)
        )


class SegmentBase(ABC, BaseModel):
    """Abstract base class for all segments."""

    _key_mapping: dict[str, str] = {}

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
    patient_zip: str  # TODO: Include field validation for ZIP code

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
        date_format = "%Y%m%d"
        try:
            return datetime.strptime(value, date_format)
        except ValueError as exc:
            raise ValueError(f"Date must be in the format {date_format}") from exc


@staticmethod
def parse_segment(
    raw_segment: str,
) -> SegmentBase | None:
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

    daw_product_selection_code: str
    date_prescription_written: str
    days_supply: str
    other_coverage_code: str | None = None
    prescription_origin_code: str
    procedure_modifiers: str
    procedure_modifiers: Annotated[str, StringConstraints(pattern=r"^.{2}$")] = Field(
        description="2-character procedure modifier code"
    )
    prescription_service_reference_number: Annotated[str, StringConstraints(pattern=r"^\d{12}$")] = Field(
        description="Prescription service reference number as 12-digit unsigned integer"
    )
    prescription_service_reference_number_qualifier: PrescriptionServiceReferenceNumberQualifier
    product_service_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9]{1,19}$")] = Field(
        description="Product Service ID as 19-character alphanumeric"
    )

    product_service_id_qualifier: ProductServiceIdQualifier
    quantity_dispensed: str  # 0000010000 = 10.000 (u7v3)
    refills_authorized: str
    fill_number: str
    number_authorized_refills: str
    special_packaging_indicator: SpecialPackagingIndicator | None = None

    _key_mapping: dict[str, str] = PrivateAttr(
        default={
            "EM": "prescription_service_reference_number_qualifier",
            "D2": "prescription_service_reference_number",
            "E1": "product_service_id_qualifier",
            "D7": "product_service_id",
            "E7": "quantity_dispensed",
            "D3": "fill_number",
            "SE": "procedure_modifiers",
            "D5": "days_supply",
            "D8": "daw_product_selection_code",
            "DE": "date_prescription_written",
            "D6": "refills_authorized",
            "DF": "number_authorized_refills",
            "DJ": "prescription_origin_code",
            "DT": "special_packaging_indicator",
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
            f"SE{self.procedure_modifiers}",
            f"E7{self.quantity_dispensed}",
            f"D3{self.fill_number}",
            f"D5{self.days_supply}",
            f"D6{self.refills_authorized}",
            f"D8{self.daw_product_selection_code}",
            f"DE{self.date_prescription_written}",
            f"DF{self.number_authorized_refills}",
            f"DJ{self.prescription_origin_code}",
            f"DT{self.special_packaging_indicator}",
            f"EB{self.other_coverage_code}",
        ]
        return FIELD_SEPARATOR + FIELD_SEPARATOR.join(values)

    # TODO: Once we are sure we have everything correct, we can move to obtaining the fields instead of hardcoding them.
    # TODO: The downside is our direct serlization to raw claim test will fail because of the change in field ordering.
    # def serialize(self) -> str:
    #     """Serializes the ClaimSegment to a string."""
    #     values = [
    #         self.segment_id,
    #         ]
    #     for key, attr in self._key_mapping.items():
    #         values.append(f"{key}{getattr(self, attr)}")
    #     return FIELD_SEPARATOR + FIELD_SEPARATOR.join(values)

    @field_validator("prescription_service_reference_number_qualifier", mode="before")
    @classmethod
    def normalize_qualifier(cls, value: str | int) -> str:
        # Convert integers to strings with zero-padding
        if isinstance(value, int):
            value = f"{value:02}"
        elif isinstance(value, str) and len(value) == 1 and value.isdigit():
            value = value.zfill(2)
        return value


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

    professional_service_fee_submitted: Annotated[str | None, StringConstraints(pattern=r"^\d+[A-IJ-R{}]$")] = Field(
        default=None, description="Professional service fee in Overpunch format"
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


# TODO: Double check which segments are mandatory and which are optional
class ClaimModel(BaseModel):
    header: NCPDPClaimHeader  # Transaction Header Segment
    insurance: InsuranceSegment
    patient: PatientSegment
    claim: ClaimSegment  # Claim Segment
    pricing: PricingSegment  # Pricing Segment
    prescriber: PrescriberSegment | None = None
    pharmacy_provider: PharmacyProviderSegment | None = None
    clinical: ClinicalSegment | None = None

    # If we were to add any addtional segments, this is where to start.
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
        claim_data = {
            "header": header,
            "insurance": None,
            "patient": None,
            "claim": None,
            "pricing": None,
            "prescriber": None,
            "pharmacy_provider": None,
            "clinical": None,
        }
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
        return cls(**{k: v for k, v in claim_data.items() if v is not None})

    def serialize(self) -> str:
        """Serializes the ClaimModel to a string."""
        segments = [self.header.serialize()]
        for segment in [
            self.insurance,
            # self.patient,
            self.claim,
            self.pricing,
            self.prescriber,
            self.pharmacy_provider,
            self.clinical,
        ]:
            if segment:
                segments.append(segment.serialize())
        segments.insert(
            2, self.patient.serialize() + GROUP_SEPARATOR
        )  # Use group separator between Patient and Claim segments
        return SEGMENT_SEPARATOR.join(segments)

    @classmethod
    def from_file(cls, file_path: str) -> ClaimModel:
        """
        Parse a claim from a file containing an NCPDP claim string.

        Args:
            file_path: Path to file containing NCPDP claim data

        Returns:
            ClaimModel: Parsed claim model
        """
        content = pathlib.Path(file_path).read_text(encoding="utf-8")

        header, *raw_segments = content.split(SEGMENT_SEPARATOR)
        claim_header = NCPDPClaimHeader.parse(header)

        segments: Sequence[SegmentBase] = [
            segment for segment in (parse_segment(segment.strip()) for segment in raw_segments) if segment is not None
        ]

        return ClaimModel.from_segments(claim_header, segments)

    @classmethod
    def reverse(cls) -> ClaimModel:
        """Reverse the claim by swapping the first and last name of the patient."""
        cls.header.transaction_code = TransactionCode.REVERSAL


class NCPDPClaimHeaderFactory(ModelFactory[NCPDPClaimHeader]):
    """Factory for generating test NCPDPHeader instances."""

    __model__ = NCPDPClaimHeader

    version = Version.MODERN  # Use modern version
    transaction_code = TransactionCode.BILLING  # Use submission transaction code
    service_date = datetime.now().strftime("%Y%m%d")


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

    prescription_service_reference_number = "123456789015"  # TODO: Solve without hardcoding

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
