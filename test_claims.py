from __future__ import annotations

import pathlib
from collections.abc import Sequence

from ncpdp_parser import (
    SEGMENT_SEPARATOR,
    ClaimModel,
    ClaimModelFactory,
    NCPDPClaimHeader,
    NCPDPClaimHeaderFactory,
    SegmentBase,
    parse_segment,
)


def test_parsed_claim_matches_serialized():
    """Test that a parsed claim can be serialized back to its original form."""
    raw_claim_data = pathlib.Path("RAW_Claim_Data.txt").read_text(encoding="utf-8")

    header, *raw_segments = raw_claim_data.split(SEGMENT_SEPARATOR)
    claim_header = NCPDPClaimHeader.parse(header)

    segments: Sequence[SegmentBase] = [
        segment for segment in (parse_segment(segment.strip()) for segment in raw_segments) if segment is not None
    ]
    claim = ClaimModel.from_segments(claim_header, segments)

    assert claim.serialize() == raw_claim_data


def test_factory_claim_parsing():
    """Test that a factory-generated claim can be parsed and reconstructed correctly."""
    # Create test claim using factory
    original_claim = ClaimModelFactory.build()
    original_serialized = original_claim.serialize()

    # Parse claim back into model
    header, *raw_segments = original_serialized.split(SEGMENT_SEPARATOR)
    claim_header = NCPDPClaimHeader.parse(header)

    segments: Sequence[SegmentBase] = [
        segment for segment in (parse_segment(segment.strip()) for segment in raw_segments) if segment is not None
    ]
    parsed_claim = ClaimModel.from_segments(claim_header, segments)

    # Test individual segments match
    assert original_claim.insurance == parsed_claim.insurance
    assert original_claim.patient == parsed_claim.patient
    assert original_claim.claim == parsed_claim.claim
    assert original_claim.pricing == parsed_claim.pricing
    assert original_claim.prescriber == parsed_claim.prescriber
    assert original_claim.pharmacy_provider == parsed_claim.pharmacy_provider
    assert original_claim.clinical == parsed_claim.clinical
    assert original_claim.header == parsed_claim.header

    # Test entire claim matches
    assert original_claim == parsed_claim, "Parsed claim does not match original"


def test_header_factory():
    """Test that the header factory generates valid headers."""
    claim = NCPDPClaimHeaderFactory.build()
    assert claim.version.value in ["D0", "51"]
    assert claim.transaction_code.value in ["B1", "B2"]
    assert len(claim.rxbin) == 6
    assert claim.rxbin.isdigit()
