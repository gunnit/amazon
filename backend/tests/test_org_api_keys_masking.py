"""Unit tests for IAM role ARN masking in the organization API-keys response."""
from app.api.v1.auth import _build_api_keys_response, _mask_arn, _mask_value
from app.core.security import encrypt_value

REAL_ARN = "arn:aws:iam::905355900769:role/sp-api"
ACCOUNT_ID = "905355900769"


def _sp_api_settings():
    return {
        "client_id_enc": encrypt_value("amzn1.application-oa2-client.abcdef123456"),
        "aws_access_key_enc": encrypt_value("AKIAIOSFODNN7EXAMPLE"),
        "role_arn_enc": encrypt_value(REAL_ARN),
    }


def test_role_arn_is_masked_in_response():
    resp = _build_api_keys_response(_sp_api_settings())
    arn = resp.sp_api_role_arn

    assert arn is not None
    assert ACCOUNT_ID not in arn
    assert "•" in arn
    assert arn.startswith("arn:aws:iam::")
    assert arn.endswith(":role/sp-api")
    # Last 3 digits of the account id stay visible.
    assert arn == "arn:aws:iam::•••••••••769:role/sp-api"


def test_other_credentials_stay_masked():
    resp = _build_api_keys_response(_sp_api_settings())

    assert resp.sp_api_client_id is not None
    assert "***" in resp.sp_api_client_id
    assert resp.sp_api_client_id != "amzn1.application-oa2-client.abcdef123456"

    assert resp.sp_api_aws_access_key is not None
    assert "***" in resp.sp_api_aws_access_key
    assert resp.sp_api_aws_access_key != "AKIAIOSFODNN7EXAMPLE"


def test_malformed_arn_falls_back_to_mask_value():
    malformed = "not-a-valid-arn-but-still-secret"
    assert _mask_arn(malformed) == _mask_value(malformed)
    assert malformed not in _mask_arn(malformed)


def test_mask_arn_handles_none():
    assert _mask_arn(None) is None
