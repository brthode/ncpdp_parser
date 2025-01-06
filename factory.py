from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from polyfactory.factories import DataclassFactory
from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

type DigitString = Annotated[str, StringConstraints(pattern="^\\d+$")]


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

    @model_validator(mode="after")
    def validate_bounds(self) -> Format:
        if self.end is not None and self.start > self.end:
            raise ValueError("Start position cannot be greater than end position")
        return self


class EMIHeader(BaseModel):
    """
    Represents an EMI header with strict format requirements.

    Format:
    DDDDDD = RXBin (6 digits)
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
        if len(emi_string) == 31:
            raise ValueError("EMI Header string must be exactly 31 characters long")

        return cls(
            rxbin=emi_string[0:6].strip(),
            version=emi_string[6:8].strip(),
            transaction_code=emi_string[8:10].strip(),
            processor_control=emi_string[10:20].strip(),
            count=emi_string[20:23].strip(),
            date=emi_string[23:31].strip(),
        )


# Factory for generating test data
class EMIHeaderFactory(DataclassFactory[EMIHeader]):
    """Factory for generating test EMIHeader instances."""

    __model__ = EMIHeader

    @classmethod
    def rxbin(cls) -> str:
        """Generates a valid 6-digit RxBIN."""
        return "".join(str(cls.__random__.randint(0, 9)) for _ in range(6))

    @classmethod
    def processor_control(cls) -> str:
        """Generates a valid 10-digit processor control number."""
        return "".join(str(cls.__random__.randint(0, 9)) for _ in range(10))

    @classmethod
    def count(cls) -> str:
        """Generates a valid 3-digit count string."""
        return f"{cls.__random__.randint(1, 999):03d}"
