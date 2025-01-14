import base64
import uuid

from ncpdp_parser import ClaimModel


def create_claim_payload(
    claim_model: ClaimModel,
    is_debug: bool = True,
    ignore_sas: bool = True,
    web_pricing: bool = True,
    rules_range_start: int = 0,
    rules_range_stop: int = 29,
) -> dict:
    """
    Creates a JSON payload from a ClaimModel object matching the required format.

    Args:
        claim_model: The ClaimModel instance to serialize
        is_debug: Boolean flag for debug mode
        ignore_sas: Flag to ignore SAS
        web_pricing: Flag for web pricing
        rules_range_start: Starting point for rules execution range
        rules_range_stop: Stopping point for rules execution range

    Returns:
        dict: Formatted JSON payload ready for API submission
    """
    serialized_claim = claim_model.serialize()
    encoded_claim = base64.b64encode(serialized_claim.encode()).decode()

    payload = {
        "message_id": str(uuid.uuid4()),
        "transaction": encoded_claim,
        "is_debug": is_debug,
        "ignore_sas": ignore_sas,
        "web_pricing": web_pricing,
        "rules_execution_range": {"start": rules_range_start, "stop": rules_range_stop},
    }

    return payload
