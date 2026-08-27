"""Reset/invite tokens must stop working once the password they were issued for changes."""
import pytest
from fastapi import HTTPException
from uuid import uuid4

from app.api.v1.auth import _reject_self, INVITE_LINK_EXPIRY_DAYS
from app.core.security import (
    create_password_reset_token, decode_token, get_password_hash, password_fingerprint,
)


def test_token_matches_the_password_it_was_issued_for():
    hashed = get_password_hash("original-password")
    payload = decode_token(create_password_reset_token(uuid4(), hashed))

    assert payload["type"] == "password_reset"
    assert payload["pwf"] == password_fingerprint(hashed)


def test_token_stops_matching_once_the_password_changes():
    hashed = get_password_hash("original-password")
    payload = decode_token(create_password_reset_token(uuid4(), hashed))

    # This is what /reset-password compares after the user picks a new password;
    # a mismatch is what makes a link single-use instead of valid for 7 days.
    assert payload["pwf"] != password_fingerprint(get_password_hash("new-password"))


def test_invite_links_outlive_an_emailed_reset_link():
    hashed = get_password_hash("x")
    short = decode_token(create_password_reset_token(uuid4(), hashed))
    long = decode_token(
        create_password_reset_token(uuid4(), hashed, expires_minutes=INVITE_LINK_EXPIRY_DAYS * 24 * 60)
    )
    assert long["exp"] - short["exp"] > 6 * 24 * 3600


def test_admin_cannot_modify_their_own_membership():
    user_id = uuid4()

    class _User:
        id = user_id

    with pytest.raises(HTTPException) as exc:
        _reject_self(_User(), user_id)
    assert exc.value.status_code == 400

    _reject_self(_User(), uuid4())
