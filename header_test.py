from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple, Self


class PaddingDirection(StrEnum):
    """Direction to apply padding for fixed width fields"""

    LEFT = "left"  # Pad with spaces on the left
    RIGHT = "right"  # Pad with spaces on the right


class NCPDPPosition(NamedTuple):
    """Position and length for NCPDP fixed width fields"""

    start: int
    length: int
    padding: PaddingDirection = PaddingDirection.LEFT  # Default to left padding

    @property
    def end(self) -> int:
        """Calculate end position based on start and length"""
        return self.start + self.length

    def slice(self, data: str) -> str:
        """Extract field from string using position"""
        return data[self.start : self.end].strip()

    def pad(self, value: str) -> str:
        """Pad value to required length with proper alignment"""
        if len(value) > self.length:
            raise ValueError(f"Value '{value}' exceeds maximum length of {self.length}")

        if self.padding == PaddingDirection.LEFT:
            return value.rjust(self.length)  # Right-justify with left padding
        return value.ljust(self.length)  # Left-justify with right padding


# Constants for NCPDP fixed width format
class NCPDPFormat:
    """NCPDP fixed width format field positions and lengths"""

    IIN = NCPDPPosition(0, 6, PaddingDirection.RIGHT)  # Issuer Identification Number - left justified
    VERSION = NCPDPPosition(6, 2)  # Version Number - right justified
    TRANSACTION_CODE = NCPDPPosition(8, 2)  # Transaction Code - right justified
    PCN = NCPDPPosition(10, 10, PaddingDirection.RIGHT)  # Processor Control Number - left justified
    TRANSACTION_COUNT = NCPDPPosition(20, 1)  # Transaction Count - right justified
    SERVICE_PROVIDER_ID_QUAL = NCPDPPosition(21, 2)  # Service Provider ID Qualifier - right justified
    SERVICE_PROVIDER_ID = NCPDPPosition(23, 15, PaddingDirection.RIGHT)  # Service Provider ID - left justified
    SERVICE_DATE = NCPDPPosition(38, 8)  # Service Date - right justified
    CERTIFICATION_ID = NCPDPPosition(46, 10, PaddingDirection.RIGHT)  # Certification ID - left justified

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


@dataclass
class NCPDPHeader:
    """NCPDP header fields with parsing and serialization"""

    iin: str  # Issuer Identification Number
    version: str  # Version Number
    transaction_code: str  # Transaction Code
    pcn: str | None  # Processor Control Number
    transaction_count: str  # Transaction Count
    service_provider_id_qual: str  # Service Provider ID Qualifier
    service_provider_id: str  # Service Provider ID
    service_date: str  # Service Date
    certification_id: str  # Certification ID

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
        # Build output string with proper padding for each field
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


# Example usage:
def test_parsing_and_serialization() -> None:
    """Example of parsing and serializing NCPDP header"""
    # Sample input string
    # sample_input = "123456D0B11790887081001ABCD1234567890120240108CERT123456"
    sample_input = "024368D0B1          1011790887081     20231110          "

    # Parse the input
    header = NCPDPHeader.parse(sample_input)

    # Serialize back to string
    output = header.serialize()

    # Verify round-trip
    print("Original:", sample_input)
    print("Serialized:", output)
    print("Lengths match:", len(sample_input) == len(output))
    print("Strings match:", sample_input == output)

    # Print individual fields for verification
    print("\nParsed fields:")
    print(f"IIN: '{header.iin}'")
    print(f"Version: '{header.version}'")
    print(f"Transaction Code: '{header.transaction_code}'")
    print(f"PCN: '{header.pcn}'")
    print(f"Transaction Count: '{header.transaction_count}'")
    print(f"Service Provider ID Qualifier: '{header.service_provider_id_qual}'")
    print(f"Service Provider ID: '{header.service_provider_id}'")
    print(f"Service Date: '{header.service_date}'")
    print(f"Certification ID: '{header.certification_id}'")


if __name__ == "__main__":
    test_parsing_and_serialization()
