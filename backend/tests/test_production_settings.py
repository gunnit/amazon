import pytest

from app.config import Settings, validate_production_settings


def _prod_settings(**overrides) -> Settings:
    base = dict(
        APP_ENV="production",
        APP_DEBUG=False,
        JWT_SECRET_KEY="x" * 40,
        APP_SECRET_KEY="y" * 40,
        ENCRYPTION_KEY="z" * 44,
        CORS_ORIGINS=["https://app.example.com"],
        APP_FRONTEND_URL="https://app.example.com",
    )
    base.update(overrides)
    return Settings(**base)


def test_valid_production_config_boots():
    validate_production_settings(_prod_settings())


def test_development_config_is_never_validated():
    validate_production_settings(_prod_settings(APP_ENV="development", APP_DEBUG=True))


def test_placeholder_jwt_secret_is_rejected():
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        validate_production_settings(
            _prod_settings(JWT_SECRET_KEY="your-jwt-secret-change-in-production")
        )


def test_short_jwt_secret_is_rejected():
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        validate_production_settings(_prod_settings(JWT_SECRET_KEY="short"))


def test_wildcard_cors_origin_is_rejected():
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        validate_production_settings(_prod_settings(CORS_ORIGINS=["*"]))


def test_debug_mode_is_rejected():
    with pytest.raises(RuntimeError, match="APP_DEBUG"):
        validate_production_settings(_prod_settings(APP_DEBUG=True))


def test_missing_encryption_key_is_rejected():
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        validate_production_settings(_prod_settings(ENCRYPTION_KEY=None))


def test_placeholder_app_secret_only_warns(caplog):
    validate_production_settings(
        _prod_settings(APP_SECRET_KEY="your-secret-key-change-in-production-min-32-chars")
    )

    assert "APP_SECRET_KEY" in caplog.text
