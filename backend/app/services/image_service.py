"""Catalog image management: S3 storage + SP-API image patch.

Uploads product images to S3 under a tenant-scoped prefix and then patches
the Amazon listing's main and alternate image slots through the Listings
Items API.
"""
from __future__ import annotations

import logging
import mimetypes
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AmazonAPIError
from app.models.amazon_account import AmazonAccount, AccountType
from app.models.product import Product
from app.services.catalog_service import CatalogOperationError

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB per Amazon's spec
MAX_ALTERNATE_IMAGES = 8


@dataclass
class ImageUpload:
    """An image payload ready to be pushed to S3."""
    filename: str
    content_type: str
    data: bytes
    is_main: bool = False


def _ext_for(content_type: str, filename: Optional[str] = None) -> str:
    if filename:
        guessed = mimetypes.guess_extension(content_type or "") or ""
        base = filename.rsplit(".", 1)
        if len(base) == 2 and base[1].lower() in {"jpg", "jpeg", "png", "webp"}:
            return f".{base[1].lower()}"
        if guessed:
            return guessed
    mapping = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    return mapping.get(content_type, ".jpg")


class ImageService:
    """Service for uploading catalog images and syncing them to SP-API."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._s3 = boto3.client(
            "s3",
            region_name=settings.AWS_S3_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    # ------------------------------------------------------------------
    # S3 helpers
    # ------------------------------------------------------------------

    def _prefix(self, organization_id: UUID, account_id: UUID, asin: str) -> str:
        return f"catalog/{organization_id}/{account_id}/{asin}"

    def _public_url(self, key: str) -> str:
        return f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_S3_REGION}.amazonaws.com/{key}"

    def _upload_to_s3(
        self,
        organization_id: UUID,
        account_id: UUID,
        asin: str,
        upload: ImageUpload,
    ) -> str:
        ext = _ext_for(upload.content_type, upload.filename)
        key = f"{self._prefix(organization_id, account_id, asin)}/{uuid.uuid4().hex}{ext}"
        try:
            self._s3.put_object(
                Bucket=settings.AWS_S3_BUCKET,
                Key=key,
                Body=upload.data,
                ContentType=upload.content_type,
                ACL="public-read",
                CacheControl="public, max-age=31536000, immutable",
            )
        except (BotoCoreError, ClientError) as exc:
            logger.exception("Failed to upload image to S3: %s", key)
            raise CatalogOperationError(f"S3 upload failed: {exc}") from exc
        return key

    def _list_keys(self, organization_id: UUID, account_id: UUID, asin: str) -> List[str]:
        prefix = self._prefix(organization_id, account_id, asin) + "/"
        try:
            response = self._s3.list_objects_v2(Bucket=settings.AWS_S3_BUCKET, Prefix=prefix)
        except (BotoCoreError, ClientError) as exc:
            logger.exception("Failed to list S3 objects for %s", prefix)
            raise CatalogOperationError(f"S3 list failed: {exc}") from exc
        return [obj["Key"] for obj in response.get("Contents", [])]

    def _delete_key(self, key: str) -> None:
        try:
            self._s3.delete_object(Bucket=settings.AWS_S3_BUCKET, Key=key)
        except (BotoCoreError, ClientError) as exc:
            logger.exception("Failed to delete S3 object: %s", key)
            raise CatalogOperationError(f"S3 delete failed: {exc}") from exc

    # ------------------------------------------------------------------
    # DB helpers (mirrors CatalogService patterns)
    # ------------------------------------------------------------------

    async def _require_seller_account(self, account_id: UUID) -> AmazonAccount:
        result = await self.db.execute(
            select(AmazonAccount).where(AmazonAccount.id == account_id)
        )
        account = result.scalar_one_or_none()
        if not account:
            raise CatalogOperationError(f"Account {account_id} not found")
        if account.account_type != AccountType.SELLER:
            raise CatalogOperationError(
                "Image updates are only available for Seller Central accounts"
            )
        if not account.seller_id:
            raise CatalogOperationError(
                f"Account {account.account_name} is missing a Seller ID"
            )
        return account

    async def _load_organization(self, account: AmazonAccount):
        from app.models.user import Organization
        result = await self.db.execute(
            select(Organization).where(Organization.id == account.organization_id)
        )
        return result.scalar_one_or_none()

    async def _load_product(self, account_id: UUID, asin: str) -> Optional[Product]:
        result = await self.db.execute(
            select(Product).where(
                Product.account_id == account_id,
                Product.asin == asin,
            )
        )
        return result.scalar_one_or_none()

    def _create_sp_api_client(self, account: AmazonAccount, organization=None):
        from app.core.amazon.credentials import resolve_credentials
        from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace

        credentials = resolve_credentials(account, organization)
        marketplace = resolve_marketplace(account.marketplace_country)
        return SPAPIClient(credentials, marketplace, account_type=account.account_type.value)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_upload(self, upload: ImageUpload) -> None:
        if upload.content_type not in ALLOWED_CONTENT_TYPES:
            raise CatalogOperationError(
                f"Unsupported image type {upload.content_type!r}; allowed: {sorted(ALLOWED_CONTENT_TYPES)}"
            )
        size = len(upload.data)
        if size == 0:
            raise CatalogOperationError("Empty file payload")
        if size > MAX_IMAGE_BYTES:
            raise CatalogOperationError(
                f"Image exceeds {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit (got {size} bytes)"
            )

    async def list_images(self, account_id: UUID, asin: str) -> List[Dict[str, str]]:
        account = await self._require_seller_account(account_id)
        keys = self._list_keys(account.organization_id, account_id, asin)
        return [
            {"key": k, "url": self._public_url(k), "filename": k.rsplit("/", 1)[-1]}
            for k in keys
        ]

    async def upload_images(
        self,
        account_id: UUID,
        asin: str,
        uploads: List[ImageUpload],
        push_to_amazon: bool = True,
        product_type: str = "PRODUCT",
    ) -> Dict[str, Any]:
        """Upload images to S3 and optionally patch them into the Amazon listing."""
        if not uploads:
            raise CatalogOperationError("No files provided")

        for up in uploads:
            self.validate_upload(up)

        account = await self._require_seller_account(account_id)
        product = await self._load_product(account_id, asin)
        if not product:
            raise CatalogOperationError(f"Product {asin} not found for this account")

        uploaded: List[Dict[str, str]] = []
        main_url: Optional[str] = None
        other_urls: List[str] = []

        for up in uploads:
            key = self._upload_to_s3(account.organization_id, account_id, asin, up)
            url = self._public_url(key)
            entry = {"key": key, "url": url, "filename": up.filename, "is_main": up.is_main}
            uploaded.append(entry)
            if up.is_main and main_url is None:
                main_url = url
            else:
                other_urls.append(url)

        # If none explicitly marked main, promote the first upload.
        if main_url is None and other_urls:
            main_url = other_urls.pop(0)
            for entry in uploaded:
                if entry["url"] == main_url:
                    entry["is_main"] = True
                    break

        sp_api_result: Optional[Dict[str, Any]] = None
        sp_api_error: Optional[str] = None

        if push_to_amazon:
            if not product.sku:
                sp_api_error = f"Product {asin} has no SKU; skipped SP-API image patch"
                logger.warning(sp_api_error)
            else:
                organization = await self._load_organization(account)
                client = self._create_sp_api_client(account, organization)
                try:
                    sp_api_result = client.update_listing_images(
                        seller_id=account.seller_id,
                        sku=product.sku,
                        product_type=product_type,
                        main_image_url=main_url,
                        other_image_urls=other_urls[:MAX_ALTERNATE_IMAGES],
                    )
                except AmazonAPIError as exc:
                    logger.warning("SP-API image patch failed for %s: %s", product.sku, exc)
                    sp_api_error = str(exc)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Unexpected failure patching images for %s", product.sku)
                    sp_api_error = str(exc)

        return {
            "account_id": str(account_id),
            "asin": asin,
            "uploaded": uploaded,
            "main_image_url": main_url,
            "other_image_urls": other_urls[:MAX_ALTERNATE_IMAGES],
            "sp_api_result": sp_api_result,
            "sp_api_error": sp_api_error,
        }

    async def delete_image(self, account_id: UUID, asin: str, key: str) -> Dict[str, Any]:
        account = await self._require_seller_account(account_id)
        expected_prefix = self._prefix(account.organization_id, account_id, asin) + "/"
        if not key.startswith(expected_prefix):
            raise CatalogOperationError("Image key does not belong to this product")
        self._delete_key(key)
        return {"deleted": key}
