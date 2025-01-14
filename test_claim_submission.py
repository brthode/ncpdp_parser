import os

import requests

from claim_response import ClaimResponse
from claim_submission import create_claim_payload
from ncpdp_parser import ClaimModel


def submit_claim(claim_model: ClaimModel, api_url: str) -> tuple[dict, ClaimResponse]:
    """
    Submits a claim to the API endpoint.

    Args:
        claim_model: The ClaimModel instance to submit
        api_url: The API endpoint URL

    Returns:
        tuple: A tuple containing the API response as a dictionary and the ClaimResponse instance
    """

    headers = {
        "Content-Type": "application/json",
    }

    payload = create_claim_payload(claim_model)

    response = requests.post(api_url, json=payload, headers=headers, timeout=10)
    # TODO: Return response to verify the status code and handle errors

    return response.json(), ClaimResponse.model_validate(response.json())


if __name__ == "__main__":
    # existing_claim = ClaimModel.from_file("RAW_Claim_Data.txt")
    existing_claim = ClaimModel.from_file("dev_claim_data.txt")

    url = os.getenv("API_URL")

    try:
        zebra_response, claim_response = submit_claim(existing_claim, url)
        if len(claim_response.transaction_context.rejects) == 0:
            print(f"Claim submitted successfully: {zebra_response}")
        else:
            print(f"Claim submission failed with rejects: {claim_response.transaction_context.rejects}")
    except Exception as e:
        print(f"Error submitting claim: {str(e)}")
