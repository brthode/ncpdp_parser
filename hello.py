from __future__ import annotations

import pathlib
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

HEADER_LENGTH = 31
FIELD_SEPARATOR = chr(28)  # File Separator <FS> / <0x1c>
GROUP_SEPARATOR = chr(29)  # Group Separator <GS> / <0x1d>
SEGMENT_SEPARATOR = chr(30)  # Record Separator <RS> / <0x1e>

type DigitString = Annotated[str, StringConstraints(pattern="^\\d+$")]


def parse_claim(raw_claim: str):
    row: str = raw_claim.split(SEGMENT_SEPARATOR)[1]
    return [s for s in row.split(FIELD_SEPARATOR) if s]


def get_header(raw_claim: str):
    rows: list[str] = raw_claim.split(SEGMENT_SEPARATOR)
    clean_header = "".join(rows[0].split())
    return clean_header


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


# @dataclass
# class Format:
#     start: int
#     end: int | None


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


class NCPDP(BaseModel):
    header: EMIHeader


EMI_HEADER: dict[str, Format] = {
    "rxbin": Format(0, 6),
    "version": Format(6, 8),
    "transaction_code": Format(8, 10),
    "processor_control": Format(10, 20),
    "count": Format(21, 24),
    "date": Format(23, None),
}

NCPCP_HEADER: dict[str, str] = {
    "C4": "Patient Date of Birth",
    "CA": "Patient First Name",
    "CB": "Patient Last Name",
    "C5": "Patient Gender Code",
    "CM": "Patient Street Address",
    "CN": "Patient City Address",
    "CP": "Patient State Address",
    "CO": "Patient Zip Code",
}

# Create a dictonary of field mappings to their model.
# Split all fields into prefix and value.
# Construct an instance of each model via lookup.


def main():
    raw_data = pathlib.Path("RAW_Claim_Data.txt").read_text(encoding="utf-8")
    # claims = split_claims(raw_data)
    header = get_header(raw_data)
    parse_header_values(header)
    # fields = {name: header[fmt.start : fmt.end] for name, fmt in EMI_HEADER.items()}
    sadf = EMIHeader.from_emi_string(header)
    patient_info = parse_claim(raw_data)
    print(patient_info)


if __name__ == "__main__":
    main()
