"""Services for Google Sheets exports and scheduled syncs."""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.security import decrypt_value, encrypt_value
from app.models.advertising import AdvertisingCampaign, AdvertisingMetrics
from app.models.amazon_account import AmazonAccount
from app.models.forecast import Forecast
from app.models.google_sheets import (
    GoogleSheetsConnection,
    GoogleSheetsSync,
    GoogleSheetsSyncRun,
)
from app.models.inventory import InventoryData
from app.models.product import Product
from app.models.sales_data import SalesData
from app.models.user import Organization
from app.schemas.google_sheets import (
    GoogleSheetsConnectionResponse,
    GoogleSheetsExportRequest,
    GoogleSheetsExportResponse,
    GoogleSheetsSyncCreate,
    GoogleSheetsSyncResponse,
    GoogleSheetsSyncRunResponse,
    GoogleSheetsSyncUpdate,
)
from app.services.analytics_service import AnalyticsService
from app.services.data_extraction import DAILY_TOTAL_ASIN
from app.services.scheduled_report_utils import get_timezone, local_to_utc, utcnow

logger = logging.getLogger(__name__)

GOOGLE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_SHEETS_BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"

LOW_STOCK_THRESHOLD = 10
AT_RISK_THRESHOLD = 25
SHEET_ROW_CHUNK_SIZE = 1000

SHEET_TITLES = {
    "sales": "Sales Data",
    "inventory": "Inventory",
    "advertising": "Advertising",
    "forecasts": "Forecasts",
    "analytics": "Analytics Summary",
}


class GoogleSheetsError(Exception):
    """Generic Google Sheets integration error."""


class GoogleReauthRequired(GoogleSheetsError):
    """Raised when the Google refresh token has been revoked."""


def _google_redirect_uri() -> str:
    if settings.GOOGLE_REDIRECT_URI:
        return settings.GOOGLE_REDIRECT_URI
    return f"{settings.APP_API_URL.rstrip('/')}/api/v1/google-sheets/oauth/callback"


def _require_google_oauth_config() -> None:
    if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
        return
    raise RuntimeError("Google OAuth is not configured")


def _spreadsheet_url(spreadsheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return ""
    return value


def _column_letter(index: int) -> str:
    value = index + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _quote_sheet_title(sheet_title: str) -> str:
    return "'" + sheet_title.replace("'", "''") + "'"


def _status_from_total(total_quantity: int) -> str:
    if total_quantity <= 0:
        return "Out of Stock"
    if total_quantity < LOW_STOCK_THRESHOLD:
        return "Low Stock"
    if total_quantity < AT_RISK_THRESHOLD:
        return "At Risk"
    return "Healthy"


def _require_int(config: dict[str, Any], key: str, *, min_value: int, max_value: int) -> int:
    value = config.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Invalid schedule config: {key}")
    if value < min_value or value > max_value:
        raise ValueError(f"Invalid schedule config: {key}")
    return value


def compute_google_sync_next_run_at(
    frequency: str,
    schedule_config: dict[str, Any],
    tz_name: str,
    now: Optional[datetime] = None,
) -> datetime:
    """Compute the next UTC execution timestamp for a Google Sheets sync."""
    now_utc = now or utcnow()
    tz = get_timezone(tz_name)
    local_now = now_utc.astimezone(tz)

    hour = _require_int(schedule_config, "hour", min_value=0, max_value=23)
    minute = _require_int(schedule_config, "minute", min_value=0, max_value=59)

    if frequency == "daily":
        candidate = datetime.combine(local_now.date(), time(hour, minute))
        if candidate <= local_now.replace(tzinfo=None):
            candidate += timedelta(days=1)
        return local_to_utc(candidate, tz_name)

    weekday = _require_int(schedule_config, "weekday", min_value=0, max_value=6)
    target_date = local_now.date() + timedelta((weekday - local_now.weekday()) % 7)
    candidate = datetime.combine(target_date, time(hour, minute))
    if candidate <= local_now.replace(tzinfo=None):
        candidate += timedelta(days=7)
    return local_to_utc(candidate, tz_name)


def resolve_google_sync_period(
    frequency: str,
    tz_name: str,
    reference: Optional[datetime] = None,
    date_range_days: Optional[int] = None,
) -> tuple[date, date]:
    """Resolve the export window for a scheduled sync."""
    now_utc = reference or utcnow()
    local_today = now_utc.astimezone(get_timezone(tz_name)).date()
    end_date = local_today - timedelta(days=1)

    if date_range_days and date_range_days > 0:
        return end_date - timedelta(days=date_range_days - 1), end_date

    if frequency == "daily":
        return end_date, end_date

    return end_date - timedelta(days=6), end_date


def google_sheets_connection_to_response(
    connection: GoogleSheetsConnection,
) -> GoogleSheetsConnectionResponse:
    return GoogleSheetsConnectionResponse.model_validate(connection)


def google_sheets_sync_to_response(sync: GoogleSheetsSync) -> GoogleSheetsSyncResponse:
    return GoogleSheetsSyncResponse.model_validate(sync)


def google_sheets_sync_run_to_response(run: GoogleSheetsSyncRun) -> GoogleSheetsSyncRunResponse:
    return GoogleSheetsSyncRunResponse.model_validate(run)


class GoogleSheetsService:
    """CRUD and export orchestration for Google Sheets."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.analytics_service = AnalyticsService(db)

    async def _validate_accounts(self, organization_id: UUID, account_ids: list[UUID]) -> list[str]:
        if not account_ids:
            return []
        result = await self.db.execute(
            select(AmazonAccount.id).where(
                AmazonAccount.organization_id == organization_id,
                AmazonAccount.id.in_(account_ids),
            )
        )
        found = {row[0] for row in result.all()}
        missing = [account_id for account_id in account_ids if account_id not in found]
        if missing:
            raise ValueError("One or more account IDs are invalid")
        return [str(account_id) for account_id in account_ids]

    async def get_connection(
        self,
        user_id: UUID,
        organization_id: UUID,
    ) -> Optional[GoogleSheetsConnection]:
        result = await self.db.execute(
            select(GoogleSheetsConnection).where(
                GoogleSheetsConnection.user_id == user_id,
                GoogleSheetsConnection.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_connection(
        self,
        user_id: UUID,
        organization_id: UUID,
        google_email: str,
        refresh_token: Optional[str],
        access_token: str,
        expires_in: int,
        scopes: list[str],
    ) -> GoogleSheetsConnection:
        connection = await self.get_connection(user_id, organization_id)
        expires_at = utcnow() + timedelta(seconds=max(expires_in - 60, 60))
        refresh_token_encrypted: Optional[str] = encrypt_value(refresh_token) if refresh_token else None

        if connection is None:
            if not refresh_token_encrypted:
                raise GoogleSheetsError("Google did not return a refresh token")
            connection = GoogleSheetsConnection(
                user_id=user_id,
                organization_id=organization_id,
                google_email=google_email,
                refresh_token_encrypted=refresh_token_encrypted,
                access_token_encrypted=encrypt_value(access_token),
                token_expires_at=expires_at,
                scopes=scopes,
                is_active=True,
                connected_at=utcnow(),
                last_used_at=utcnow(),
            )
            self.db.add(connection)
        else:
            connection.google_email = google_email
            if refresh_token_encrypted:
                connection.refresh_token_encrypted = refresh_token_encrypted
            connection.access_token_encrypted = encrypt_value(access_token)
            connection.token_expires_at = expires_at
            connection.scopes = scopes
            connection.is_active = True
            connection.connected_at = utcnow()
            connection.last_used_at = utcnow()

        await self.db.flush()
        await self.db.refresh(connection)
        return connection

    async def disconnect_connection(self, connection: GoogleSheetsConnection) -> None:
        try:
            refresh_token = decrypt_value(connection.refresh_token_encrypted)
        except Exception:
            refresh_token = None

        if refresh_token:
            async with httpx.AsyncClient(timeout=20.0) as client:
                try:
                    await client.post(
                        GOOGLE_REVOKE_URL,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        data={"token": refresh_token},
                    )
                except Exception:
                    logger.warning("Google token revocation failed for connection %s", connection.id, exc_info=True)

        await self.db.delete(connection)
        await self.db.flush()

    def build_auth_url(self, state: str) -> str:
        _require_google_oauth_config()
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": _google_redirect_uri(),
            "response_type": "code",
            "scope": " ".join(GOOGLE_SHEETS_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        _require_google_oauth_config()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": _google_redirect_uri(),
                    "grant_type": "authorization_code",
                },
            )
        if response.status_code >= 400:
            detail = self._extract_google_error(response)
            raise GoogleSheetsError(detail)
        return response.json()

    async def fetch_google_user_email(self, access_token: str) -> str:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code >= 400:
            detail = self._extract_google_error(response)
            raise GoogleSheetsError(detail)
        payload = response.json()
        email = payload.get("email")
        if not email:
            raise GoogleSheetsError("Google user email not available")
        return str(email)

    async def _get_valid_access_token(self, connection: GoogleSheetsConnection) -> str:
        if (
            connection.access_token_encrypted
            and connection.token_expires_at
            and connection.token_expires_at > utcnow() + timedelta(minutes=1)
        ):
            connection.last_used_at = utcnow()
            await self.db.flush()
            return decrypt_value(connection.access_token_encrypted)

        _require_google_oauth_config()
        refresh_token = decrypt_value(connection.refresh_token_encrypted)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )

        if response.status_code >= 400:
            detail = self._extract_google_error(response)
            if "invalid_grant" in detail:
                connection.is_active = False
                connection.access_token_encrypted = None
                connection.token_expires_at = None
                await self.db.commit()
                raise GoogleReauthRequired("google_reauth_required")
            raise GoogleSheetsError(detail)

        payload = response.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise GoogleSheetsError("Google did not return an access token")

        expires_in = int(payload.get("expires_in") or 3600)
        connection.access_token_encrypted = encrypt_value(access_token)
        connection.token_expires_at = utcnow() + timedelta(seconds=max(expires_in - 60, 60))
        connection.last_used_at = utcnow()
        connection.is_active = True
        await self.db.flush()
        return access_token

    async def _google_request(
        self,
        connection: GoogleSheetsConnection,
        method: str,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
        retry_on_auth: bool = True,
    ) -> dict[str, Any]:
        access_token = await self._get_valid_access_token(connection)

        async with httpx.AsyncClient(timeout=45.0) as client:
            for attempt in range(4):
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_data,
                    headers={"Authorization": f"Bearer {access_token}"},
                )

                if response.status_code == 401 and retry_on_auth:
                    connection.access_token_encrypted = None
                    connection.token_expires_at = None
                    await self.db.flush()
                    access_token = await self._get_valid_access_token(connection)
                    retry_on_auth = False
                    continue

                if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                    await asyncio.sleep(2 ** (attempt + 1))
                    continue

                if response.status_code >= 400:
                    detail = self._extract_google_error(response)
                    raise GoogleSheetsError(detail)

                if not response.content:
                    return {}
                return response.json()

        raise GoogleSheetsError("Google API request failed")

    def _extract_google_error(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            return response.text or f"Google API error ({response.status_code})"

        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("status")
            if message:
                return str(message)
        if isinstance(error, str):
            description = payload.get("error_description")
            if description:
                return f"{error}: {description}"
            return error
        return response.text or f"Google API error ({response.status_code})"

    async def create_spreadsheet(
        self,
        connection: GoogleSheetsConnection,
        title: str,
        initial_sheet_title: str,
    ) -> tuple[str, str]:
        payload = {
            "properties": {
                "title": title,
            },
            "sheets": [
                {
                    "properties": {
                        "title": initial_sheet_title,
                    }
                }
            ],
        }
        data = await self._google_request(
            connection,
            "POST",
            GOOGLE_SHEETS_BASE_URL,
            json_data=payload,
        )
        spreadsheet_id = data.get("spreadsheetId")
        spreadsheet_url = data.get("spreadsheetUrl") or _spreadsheet_url(spreadsheet_id)
        if not spreadsheet_id:
            raise GoogleSheetsError("Google did not return a spreadsheet id")
        return str(spreadsheet_id), str(spreadsheet_url)

    async def _get_spreadsheet_metadata(
        self,
        connection: GoogleSheetsConnection,
        spreadsheet_id: str,
    ) -> dict[str, Any]:
        return await self._google_request(
            connection,
            "GET",
            f"{GOOGLE_SHEETS_BASE_URL}/{spreadsheet_id}",
        )

    async def _ensure_sheet(
        self,
        connection: GoogleSheetsConnection,
        spreadsheet_id: str,
        sheet_title: str,
    ) -> int:
        metadata = await self._get_spreadsheet_metadata(connection, spreadsheet_id)
        for sheet in metadata.get("sheets", []):
            properties = sheet.get("properties") or {}
            if properties.get("title") == sheet_title:
                return int(properties.get("sheetId"))

        result = await self._google_request(
            connection,
            "POST",
            f"{GOOGLE_SHEETS_BASE_URL}/{spreadsheet_id}:batchUpdate",
            json_data={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": sheet_title,
                            }
                        }
                    }
                ]
            },
        )
        replies = result.get("replies") or []
        added = replies[0].get("addSheet", {}).get("properties", {}) if replies else {}
        return int(added.get("sheetId"))

    async def _clear_sheet(
        self,
        connection: GoogleSheetsConnection,
        spreadsheet_id: str,
        sheet_title: str,
    ) -> None:
        await self._google_request(
            connection,
            "POST",
            f"{GOOGLE_SHEETS_BASE_URL}/{spreadsheet_id}/values/{_quote_sheet_title(sheet_title)}:clear",
            json_data={},
        )

    async def _get_sheet_row_count(
        self,
        connection: GoogleSheetsConnection,
        spreadsheet_id: str,
        sheet_title: str,
    ) -> int:
        data = await self._google_request(
            connection,
            "GET",
            f"{GOOGLE_SHEETS_BASE_URL}/{spreadsheet_id}/values/{_quote_sheet_title(sheet_title)}!A:A",
            params={"majorDimension": "COLUMNS"},
        )
        values = data.get("values") or []
        if not values:
            return 0
        return len(values[0])

    async def _write_values(
        self,
        connection: GoogleSheetsConnection,
        spreadsheet_id: str,
        sheet_title: str,
        start_row: int,
        values: list[list[Any]],
    ) -> None:
        for offset in range(0, len(values), SHEET_ROW_CHUNK_SIZE):
            chunk = values[offset : offset + SHEET_ROW_CHUNK_SIZE]
            range_name = f"{_quote_sheet_title(sheet_title)}!A{start_row + offset}"
            await self._google_request(
                connection,
                "PUT",
                f"{GOOGLE_SHEETS_BASE_URL}/{spreadsheet_id}/values/{range_name}",
                params={"valueInputOption": "RAW"},
                json_data={
                    "range": range_name,
                    "majorDimension": "ROWS",
                    "values": chunk,
                },
            )
            if offset + SHEET_ROW_CHUNK_SIZE < len(values):
                await asyncio.sleep(0.1)

    async def _auto_resize_sheet(
        self,
        connection: GoogleSheetsConnection,
        spreadsheet_id: str,
        sheet_id: int,
        num_cols: int,
    ) -> None:
        await self._google_request(
            connection,
            "POST",
            f"{GOOGLE_SHEETS_BASE_URL}/{spreadsheet_id}:batchUpdate",
            json_data={
                "requests": [
                    {
                        "autoResizeDimensions": {
                            "dimensions": {
                                "sheetId": sheet_id,
                                "dimension": "COLUMNS",
                                "startIndex": 0,
                                "endIndex": num_cols,
                            }
                        }
                    }
                ]
            },
        )

    async def format_sheet(
        self,
        connection: GoogleSheetsConnection,
        spreadsheet_id: str,
        sheet_id: int,
        headers: list[str],
        num_rows: int,
        metadata_label: str,
        sheet_kind: str,
    ) -> None:
        num_cols = max(len(headers), 1)
        requests: list[dict[str, Any]] = [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {
                            "frozenRowCount": min(3, num_rows),
                        },
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            {
                "mergeCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": num_cols,
                    },
                    "mergeType": "MERGE_ALL",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": num_cols,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.95, "green": 0.97, "blue": 1.0},
                            "textFormat": {"bold": True, "fontSize": 11},
                            "horizontalAlignment": "LEFT",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
                }
            },
            {
                "addBanding": {
                    "bandedRange": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 2,
                            "endRowIndex": max(num_rows, 3),
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols,
                        },
                        "rowProperties": {
                            "headerColor": {"red": 0.121, "green": 0.306, "blue": 0.475},
                            "firstBandColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                            "secondBandColor": {"red": 0.839, "green": 0.894, "blue": 0.941},
                        },
                    }
                }
            },
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": num_cols,
                    }
                }
            },
        ]

        for column_index, format_type in self._sheet_number_formats(sheet_kind, headers).items():
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 3,
                            "endRowIndex": max(num_rows, 4),
                            "startColumnIndex": column_index,
                            "endColumnIndex": column_index + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": format_type,
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                }
            )

        try:
            await self._google_request(
                connection,
                "POST",
                f"{GOOGLE_SHEETS_BASE_URL}/{spreadsheet_id}:batchUpdate",
                json_data={"requests": requests},
            )
        except GoogleSheetsError:
            logger.warning(
                "Google Sheets formatting failed for sheet %s (%s)",
                metadata_label,
                sheet_kind,
                exc_info=True,
            )

    def _sheet_number_formats(self, sheet_kind: str, headers: list[str]) -> dict[int, dict[str, str]]:
        formats: dict[str, dict[str, str]] = {
            "currency": {"type": "CURRENCY", "pattern": '"€"#,##0.00'},
            "percent": {"type": "PERCENT", "pattern": "0.00%"},
            "integer": {"type": "NUMBER", "pattern": "0"},
            "decimal": {"type": "NUMBER", "pattern": "0.00"},
        }

        by_sheet: dict[str, dict[str, str]] = {
            "sales": {
                "Units": "integer",
                "Revenue": "currency",
                "Orders": "integer",
                "AOV": "currency",
            },
            "inventory": {
                "FBA Qty": "integer",
                "Inbound": "integer",
                "Reserved": "integer",
                "Total": "integer",
                "MFN Qty": "integer",
            },
            "advertising": {
                "Impressions": "integer",
                "Clicks": "integer",
                "Spend": "currency",
                "Sales 7d": "currency",
                "CTR": "percent",
                "CPC": "currency",
                "ACoS": "percent",
                "ROAS": "decimal",
            },
            "forecasts": {
                "Predicted": "decimal",
                "Lower Bound": "decimal",
                "Upper Bound": "decimal",
            },
            "analytics": {
                "Change %": "percent",
            },
        }

        result: dict[int, dict[str, str]] = {}
        for index, header in enumerate(headers):
            format_name = by_sheet.get(sheet_kind, {}).get(header)
            if format_name:
                result[index] = formats[format_name]
        return result

    async def write_sheet_data(
        self,
        connection: GoogleSheetsConnection,
        spreadsheet_id: str,
        sheet_title: str,
        headers: list[str],
        rows: list[dict[str, Any]],
        mode: str,
        *,
        metadata_label: str,
        sheet_kind: str,
    ) -> int:
        sheet_id = await self._ensure_sheet(connection, spreadsheet_id, sheet_title)
        row_values = [[_serialize_value(row.get(header)) for header in headers] for row in rows]
        full_values = [[metadata_label], [], headers, *row_values]
        existing_row_count = await self._get_sheet_row_count(connection, spreadsheet_id, sheet_title)

        if mode == "overwrite":
            await self._clear_sheet(connection, spreadsheet_id, sheet_title)
            await self._write_values(connection, spreadsheet_id, sheet_title, 1, full_values)
            await self.format_sheet(
                connection,
                spreadsheet_id,
                sheet_id,
                headers,
                len(full_values),
                metadata_label,
                sheet_kind,
            )
            return len(rows)

        if existing_row_count == 0:
            await self._write_values(connection, spreadsheet_id, sheet_title, 1, full_values)
            await self.format_sheet(
                connection,
                spreadsheet_id,
                sheet_id,
                headers,
                len(full_values),
                metadata_label,
                sheet_kind,
            )
            return len(rows)

        if row_values:
            await self._write_values(connection, spreadsheet_id, sheet_title, existing_row_count + 1, row_values)
            await self._auto_resize_sheet(connection, spreadsheet_id, sheet_id, len(headers))
        return len(rows)

    async def export_to_sheets(
        self,
        connection: GoogleSheetsConnection,
        organization_id: UUID,
        request: GoogleSheetsExportRequest,
        *,
        sync_mode: str = "overwrite",
    ) -> tuple[GoogleSheetsExportResponse, int]:
        data_types = list(dict.fromkeys(request.data_types))
        if not data_types:
            raise ValueError("At least one data type is required")

        collected = await self._collect_all_data(
            organization_id=organization_id,
            data_types=data_types,
            start_date=request.start_date,
            end_date=request.end_date,
            account_ids=request.account_ids or [],
            parameters=request.parameters,
        )

        first_sheet_title = collected[data_types[0]]["sheet_title"]
        if request.spreadsheet_id:
            spreadsheet_id = request.spreadsheet_id
            spreadsheet_url = _spreadsheet_url(spreadsheet_id)
        else:
            title = request.name or f"Inthezon Export {request.start_date.isoformat()} to {request.end_date.isoformat()}"
            spreadsheet_id, spreadsheet_url = await self.create_spreadsheet(connection, title, first_sheet_title)

        metadata_label = (
            f"Inthezon Report - {request.start_date.isoformat()} to {request.end_date.isoformat()} - "
            f"Generated {utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )

        total_rows = 0
        sheet_titles: list[str] = []
        for data_type in data_types:
            payload = collected[data_type]
            total_rows += await self.write_sheet_data(
                connection=connection,
                spreadsheet_id=spreadsheet_id,
                sheet_title=payload["sheet_title"],
                headers=payload["headers"],
                rows=payload["rows"],
                mode=sync_mode,
                metadata_label=metadata_label,
                sheet_kind=data_type,
            )
            sheet_titles.append(payload["sheet_title"])

        response = GoogleSheetsExportResponse(
            spreadsheet_id=spreadsheet_id,
            spreadsheet_url=spreadsheet_url,
            sheets_created=sheet_titles,
        )
        return response, total_rows

    async def list_syncs(self, organization_id: UUID) -> list[GoogleSheetsSync]:
        result = await self.db.execute(
            select(GoogleSheetsSync)
            .where(GoogleSheetsSync.organization_id == organization_id)
            .order_by(GoogleSheetsSync.created_at.desc())
        )
        return result.scalars().all()

    async def get_sync(self, sync_id: UUID, organization_id: UUID) -> Optional[GoogleSheetsSync]:
        result = await self.db.execute(
            select(GoogleSheetsSync).where(
                GoogleSheetsSync.id == sync_id,
                GoogleSheetsSync.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_sync(
        self,
        organization: Organization,
        connection: GoogleSheetsConnection,
        user_id: UUID,
        payload: GoogleSheetsSyncCreate,
    ) -> GoogleSheetsSync:
        account_ids = await self._validate_accounts(organization.id, payload.account_ids)
        sync = GoogleSheetsSync(
            organization_id=organization.id,
            connection_id=connection.id,
            created_by_id=user_id,
            name=payload.name.strip(),
            frequency=payload.frequency,
            sync_mode=payload.sync_mode,
            data_types=list(payload.data_types),
            account_ids=account_ids,
            parameters=payload.parameters,
            schedule_config=payload.schedule_config,
            timezone=payload.timezone,
            is_enabled=True,
            next_run_at=compute_google_sync_next_run_at(
                payload.frequency,
                payload.schedule_config,
                payload.timezone,
            ),
        )
        self.db.add(sync)
        await self.db.flush()
        await self.db.refresh(sync)
        return sync

    async def update_sync(
        self,
        sync: GoogleSheetsSync,
        organization: Organization,
        payload: GoogleSheetsSyncUpdate,
    ) -> GoogleSheetsSync:
        next_frequency = payload.frequency or sync.frequency
        next_schedule_config = (
            payload.schedule_config
            if payload.schedule_config is not None
            else dict(sync.schedule_config or {})
        )
        next_timezone = payload.timezone or sync.timezone

        sync.name = payload.name.strip() if payload.name is not None else sync.name
        sync.frequency = next_frequency
        sync.sync_mode = payload.sync_mode or sync.sync_mode
        sync.data_types = list(payload.data_types if payload.data_types is not None else (sync.data_types or []))
        next_account_ids = (
            payload.account_ids
            if payload.account_ids is not None
            else [UUID(account_id) for account_id in (sync.account_ids or [])]
        )
        sync.account_ids = await self._validate_accounts(organization.id, next_account_ids)
        sync.parameters = (
            payload.parameters
            if payload.parameters is not None
            else dict(sync.parameters or {})
        )
        sync.schedule_config = next_schedule_config
        sync.timezone = next_timezone
        if payload.is_enabled is not None:
            sync.is_enabled = payload.is_enabled
        sync.next_run_at = (
            compute_google_sync_next_run_at(sync.frequency, sync.schedule_config, sync.timezone)
            if sync.is_enabled
            else None
        )
        await self.db.flush()
        await self.db.refresh(sync)
        return sync

    async def toggle_sync(self, sync: GoogleSheetsSync, enabled: bool) -> GoogleSheetsSync:
        sync.is_enabled = enabled
        sync.next_run_at = (
            compute_google_sync_next_run_at(sync.frequency, sync.schedule_config, sync.timezone)
            if enabled
            else None
        )
        await self.db.flush()
        await self.db.refresh(sync)
        return sync

    async def delete_sync(self, sync: GoogleSheetsSync) -> None:
        await self.db.delete(sync)
        await self.db.flush()

    async def list_runs(
        self,
        sync_id: UUID,
        organization_id: UUID,
        limit: int = 20,
    ) -> list[GoogleSheetsSyncRun]:
        result = await self.db.execute(
            select(GoogleSheetsSyncRun)
            .where(
                GoogleSheetsSyncRun.sync_id == sync_id,
                GoogleSheetsSyncRun.organization_id == organization_id,
            )
            .order_by(GoogleSheetsSyncRun.triggered_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def create_run(
        self,
        sync: GoogleSheetsSync,
        *,
        reference_time: Optional[datetime] = None,
    ) -> GoogleSheetsSyncRun:
        run = GoogleSheetsSyncRun(
            sync_id=sync.id,
            organization_id=sync.organization_id,
            status="pending",
            progress_step="Queued",
            data_types_snapshot=list(sync.data_types or []),
        )
        self.db.add(run)
        sync.last_run_at = reference_time or utcnow()
        sync.last_run_status = "pending"
        sync.next_run_at = (
            compute_google_sync_next_run_at(sync.frequency, sync.schedule_config, sync.timezone, reference_time)
            if sync.is_enabled
            else None
        )
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def _collect_all_data(
        self,
        *,
        organization_id: UUID,
        data_types: list[str],
        start_date: date,
        end_date: date,
        account_ids: list[UUID],
        parameters: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        rows_by_type: dict[str, dict[str, Any]] = {}
        selected_account_ids = account_ids or []
        account_id_query = select(AmazonAccount.id).where(AmazonAccount.organization_id == organization_id)
        if selected_account_ids:
            account_id_query = account_id_query.where(AmazonAccount.id.in_(selected_account_ids))

        if "sales" in data_types:
            rows_by_type["sales"] = await self._collect_sales_sheet(account_id_query, start_date, end_date)
        if "inventory" in data_types:
            rows_by_type["inventory"] = await self._collect_inventory_sheet(account_id_query, end_date)
        if "advertising" in data_types:
            rows_by_type["advertising"] = await self._collect_advertising_sheet(account_id_query, start_date, end_date)
        if "forecasts" in data_types:
            rows_by_type["forecasts"] = await self._collect_forecasts_sheet(account_id_query, start_date, end_date)
        if "analytics" in data_types:
            rows_by_type["analytics"] = await self._collect_analytics_sheet(
                account_id_query,
                start_date,
                end_date,
            )

        return rows_by_type

    async def _collect_sales_sheet(
        self,
        account_id_query,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(
                SalesData.date,
                SalesData.asin,
                SalesData.sku,
                func.max(Product.title).label("title"),
                func.sum(SalesData.units_ordered).label("units"),
                func.sum(SalesData.ordered_product_sales).label("revenue"),
                func.sum(SalesData.total_order_items).label("orders"),
                func.max(SalesData.currency).label("currency"),
            )
            .select_from(SalesData)
            .outerjoin(
                Product,
                and_(
                    Product.account_id == SalesData.account_id,
                    Product.asin == SalesData.asin,
                ),
            )
            .where(
                SalesData.account_id.in_(account_id_query),
                SalesData.asin != DAILY_TOTAL_ASIN,
                SalesData.date >= start_date,
                SalesData.date <= end_date,
            )
            .group_by(SalesData.date, SalesData.asin, SalesData.sku)
            .order_by(SalesData.date.desc(), SalesData.asin)
        )
        rows = []
        for row in result.all():
            revenue = float(row.revenue or 0)
            orders = int(row.orders or 0)
            rows.append(
                {
                    "Date": row.date,
                    "ASIN": row.asin,
                    "SKU": row.sku or "",
                    "Title": row.title or "",
                    "Units": int(row.units or 0),
                    "Revenue": revenue,
                    "Orders": orders,
                    "AOV": revenue / orders if orders else 0,
                    "Currency": row.currency or "EUR",
                }
            )
        headers = ["Date", "ASIN", "SKU", "Title", "Units", "Revenue", "Orders", "AOV", "Currency"]
        return {"sheet_title": SHEET_TITLES["sales"], "headers": headers, "rows": rows}

    async def _collect_inventory_sheet(
        self,
        account_id_query,
        end_date: date,
    ) -> dict[str, Any]:
        snapshot_result = await self.db.execute(
            select(func.max(InventoryData.snapshot_date)).where(
                InventoryData.account_id.in_(account_id_query),
                InventoryData.snapshot_date <= end_date,
            )
        )
        snapshot_date = snapshot_result.scalar_one_or_none()
        rows: list[dict[str, Any]] = []
        if snapshot_date:
            result = await self.db.execute(
                select(
                    InventoryData.snapshot_date,
                    InventoryData.asin,
                    InventoryData.sku,
                    func.max(Product.title).label("title"),
                    InventoryData.afn_fulfillable_quantity,
                    InventoryData.afn_inbound_working_quantity,
                    InventoryData.afn_inbound_shipped_quantity,
                    InventoryData.afn_reserved_quantity,
                    InventoryData.afn_total_quantity,
                    InventoryData.mfn_fulfillable_quantity,
                )
                .select_from(InventoryData)
                .outerjoin(
                    Product,
                    and_(
                        Product.account_id == InventoryData.account_id,
                        Product.asin == InventoryData.asin,
                    ),
                )
                .where(
                    InventoryData.account_id.in_(account_id_query),
                    InventoryData.snapshot_date == snapshot_date,
                )
                .order_by(InventoryData.asin)
            )
            for row in result.all():
                inbound = int(row.afn_inbound_working_quantity or 0) + int(row.afn_inbound_shipped_quantity or 0)
                total = int(row.afn_total_quantity or 0) + int(row.mfn_fulfillable_quantity or 0)
                rows.append(
                    {
                        "Snapshot Date": row.snapshot_date,
                        "ASIN": row.asin,
                        "SKU": row.sku or "",
                        "Title": row.title or "",
                        "FBA Qty": int(row.afn_fulfillable_quantity or 0),
                        "Inbound": inbound,
                        "Reserved": int(row.afn_reserved_quantity or 0),
                        "Total": total,
                        "MFN Qty": int(row.mfn_fulfillable_quantity or 0),
                        "Status": _status_from_total(total),
                    }
                )
        headers = [
            "Snapshot Date",
            "ASIN",
            "SKU",
            "Title",
            "FBA Qty",
            "Inbound",
            "Reserved",
            "Total",
            "MFN Qty",
            "Status",
        ]
        return {"sheet_title": SHEET_TITLES["inventory"], "headers": headers, "rows": rows}

    async def _collect_advertising_sheet(
        self,
        account_id_query,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(
                AdvertisingMetrics.date,
                AdvertisingCampaign.campaign_name,
                AdvertisingCampaign.campaign_type,
                func.sum(AdvertisingMetrics.impressions).label("impressions"),
                func.sum(AdvertisingMetrics.clicks).label("clicks"),
                func.sum(AdvertisingMetrics.cost).label("spend"),
                func.sum(AdvertisingMetrics.attributed_sales_7d).label("sales_7d"),
                func.avg(AdvertisingMetrics.ctr).label("ctr"),
                func.avg(AdvertisingMetrics.cpc).label("cpc"),
                func.avg(AdvertisingMetrics.acos).label("acos"),
                func.avg(AdvertisingMetrics.roas).label("roas"),
            )
            .select_from(AdvertisingMetrics)
            .join(AdvertisingCampaign, AdvertisingCampaign.id == AdvertisingMetrics.campaign_id)
            .where(
                AdvertisingCampaign.account_id.in_(account_id_query),
                AdvertisingMetrics.date >= start_date,
                AdvertisingMetrics.date <= end_date,
            )
            .group_by(
                AdvertisingMetrics.date,
                AdvertisingCampaign.campaign_name,
                AdvertisingCampaign.campaign_type,
            )
            .order_by(AdvertisingMetrics.date.desc(), AdvertisingCampaign.campaign_name)
        )
        rows = [
            {
                "Date": row.date,
                "Campaign": row.campaign_name or "",
                "Type": row.campaign_type or "",
                "Impressions": int(row.impressions or 0),
                "Clicks": int(row.clicks or 0),
                "Spend": float(row.spend or 0),
                "Sales 7d": float(row.sales_7d or 0),
                "CTR": float(row.ctr or 0) / 100 if float(row.ctr or 0) > 1 else float(row.ctr or 0),
                "CPC": float(row.cpc or 0),
                "ACoS": float(row.acos or 0) / 100 if float(row.acos or 0) > 1 else float(row.acos or 0),
                "ROAS": float(row.roas or 0),
            }
            for row in result.all()
        ]
        headers = ["Date", "Campaign", "Type", "Impressions", "Clicks", "Spend", "Sales 7d", "CTR", "CPC", "ACoS", "ROAS"]
        return {"sheet_title": SHEET_TITLES["advertising"], "headers": headers, "rows": rows}

    async def _collect_forecasts_sheet(
        self,
        account_id_query,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(Forecast, AmazonAccount.account_name)
            .join(AmazonAccount, AmazonAccount.id == Forecast.account_id)
            .where(Forecast.account_id.in_(account_id_query))
            .order_by(Forecast.generated_at.desc())
        )
        rows: list[dict[str, Any]] = []
        for forecast, account_name in result.all():
            predictions = forecast.predictions or []
            filtered_predictions = []
            for item in predictions:
                try:
                    prediction_date = (
                        date.fromisoformat(item["date"])
                        if isinstance(item.get("date"), str)
                        else item.get("date")
                    )
                except Exception:
                    prediction_date = None

                if prediction_date and start_date <= prediction_date <= end_date:
                    filtered_predictions.append((prediction_date, item))

            if not filtered_predictions:
                filtered_predictions = []
                for item in predictions:
                    try:
                        prediction_date = (
                            date.fromisoformat(item["date"])
                            if isinstance(item.get("date"), str)
                            else item.get("date")
                        )
                    except Exception:
                        prediction_date = None
                    filtered_predictions.append((prediction_date, item))

            for prediction_date, item in filtered_predictions:
                predicted = float(item.get("value") or 0)
                rows.append(
                    {
                        "ASIN": forecast.asin or "ALL",
                        "Account": account_name or "",
                        "Metric": forecast.forecast_type or "sales",
                        "Period": prediction_date.isoformat() if prediction_date else "",
                        "Predicted": predicted,
                        "Lower Bound": float(item.get("lower") or predicted),
                        "Upper Bound": float(item.get("upper") or predicted),
                        "Model": forecast.model_used or "prophet",
                    }
                )
        headers = ["ASIN", "Account", "Metric", "Period", "Predicted", "Lower Bound", "Upper Bound", "Model"]
        return {"sheet_title": SHEET_TITLES["forecasts"], "headers": headers, "rows": rows}

    async def _collect_analytics_sheet(
        self,
        account_id_query,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        account_result = await self.db.execute(account_id_query)
        account_ids = [row[0] for row in account_result.all()]
        if not account_ids:
            headers = ["Metric", "Current Value", "Previous Value", "Change %", "Trend"]
            return {"sheet_title": SHEET_TITLES["analytics"], "headers": headers, "rows": []}

        period_days = (end_date - start_date).days + 1
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=period_days - 1)

        sales_metrics = await self.analytics_service.compute_dashboard_kpis(account_ids, start_date, end_date)
        ads_current = await self.analytics_service.compute_advertising_metrics(account_ids, start_date, end_date)
        ads_previous = await self.analytics_service.compute_advertising_metrics(account_ids, prev_start, prev_end)

        def metric_row(label: str, current: Any, previous: Any, change: Optional[float], trend: str) -> dict[str, Any]:
            return {
                "Metric": label,
                "Current Value": _serialize_value(current),
                "Previous Value": _serialize_value(previous),
                "Change %": (change or 0) / 100,
                "Trend": trend,
            }

        rows = [
            metric_row(
                "Revenue",
                sales_metrics["current"]["revenue"],
                sales_metrics["previous"]["revenue"],
                sales_metrics["changes"]["revenue"]["percent"],
                sales_metrics["changes"]["revenue"]["trend"],
            ),
            metric_row(
                "Units",
                sales_metrics["current"]["units"],
                sales_metrics["previous"]["units"],
                sales_metrics["changes"]["units"]["percent"],
                sales_metrics["changes"]["units"]["trend"],
            ),
            metric_row(
                "Orders",
                sales_metrics["current"]["orders"],
                sales_metrics["previous"]["orders"],
                sales_metrics["changes"]["orders"]["percent"],
                sales_metrics["changes"]["orders"]["trend"],
            ),
            metric_row(
                "Average Order Value",
                sales_metrics["current"]["average_order_value"],
                sales_metrics["previous"]["average_order_value"],
                sales_metrics["changes"]["average_order_value"]["percent"],
                sales_metrics["changes"]["average_order_value"]["trend"],
            ),
            metric_row(
                "Active ASINs",
                sales_metrics["current"]["active_asins"],
                sales_metrics["previous"]["active_asins"],
                None,
                "stable",
            ),
            metric_row(
                "Ad Spend",
                ads_current["cost"],
                ads_previous["cost"],
                _percent_change(ads_current["cost"], ads_previous["cost"]),
                _trend_from_change(_percent_change(ads_current["cost"], ads_previous["cost"])),
            ),
            metric_row(
                "Ad Sales",
                ads_current["sales"],
                ads_previous["sales"],
                _percent_change(ads_current["sales"], ads_previous["sales"]),
                _trend_from_change(_percent_change(ads_current["sales"], ads_previous["sales"])),
            ),
            metric_row(
                "CTR",
                ads_current["ctr"] / 100 if ads_current["ctr"] > 1 else ads_current["ctr"],
                ads_previous["ctr"] / 100 if ads_previous["ctr"] > 1 else ads_previous["ctr"],
                _percent_change(ads_current["ctr"], ads_previous["ctr"]),
                _trend_from_change(_percent_change(ads_current["ctr"], ads_previous["ctr"])),
            ),
            metric_row(
                "ACoS",
                ads_current["acos"] / 100 if ads_current["acos"] > 1 else ads_current["acos"],
                ads_previous["acos"] / 100 if ads_previous["acos"] > 1 else ads_previous["acos"],
                _percent_change(ads_current["acos"], ads_previous["acos"]),
                _trend_from_change(_percent_change(ads_current["acos"], ads_previous["acos"])),
            ),
        ]
        headers = ["Metric", "Current Value", "Previous Value", "Change %", "Trend"]
        return {"sheet_title": SHEET_TITLES["analytics"], "headers": headers, "rows": rows}


def _percent_change(current: Any, previous: Any) -> Optional[float]:
    current_value = float(current or 0)
    previous_value = float(previous or 0)
    if previous is None:
        return None
    if previous_value == 0:
        return 100.0 if current_value > 0 else 0.0
    return ((current_value - previous_value) / previous_value) * 100


def _trend_from_change(change: Optional[float]) -> str:
    if change is None:
        return "stable"
    if change > 5:
        return "up"
    if change < -5:
        return "down"
    return "stable"


def enqueue_google_sheets_run_processing(run_id: str) -> None:
    """Queue background execution for a Google Sheets sync run."""
    from workers.tasks.google_sheets import process_google_sheets_sync_task

    try:
        process_google_sheets_sync_task.delay(run_id)
    except Exception:
        logger.exception("Failed to enqueue Google Sheets run %s; using in-process thread fallback", run_id)
        thread = threading.Thread(target=process_google_sheets_sync_job, args=(run_id,), daemon=True)
        thread.start()


def process_google_sheets_sync_job(run_id: str) -> None:
    """Process a Google Sheets sync run in a dedicated async session."""
    from app.db.session import db_url as _db_url

    engine = create_async_engine(
        _db_url,
        echo=settings.APP_DEBUG,
        pool_size=2,
        max_overflow=1,
    )
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    async def _process() -> None:
        async with SessionLocal() as db:
            run_result = await db.execute(select(GoogleSheetsSyncRun).where(GoogleSheetsSyncRun.id == UUID(run_id)))
            run = run_result.scalar_one_or_none()
            if not run:
                return

            sync_result = await db.execute(select(GoogleSheetsSync).where(GoogleSheetsSync.id == run.sync_id))
            sync = sync_result.scalar_one_or_none()
            if not sync:
                run.status = "failed"
                run.error_message = "Google Sheets sync not found"
                run.completed_at = utcnow()
                await db.commit()
                return

            connection_result = await db.execute(
                select(GoogleSheetsConnection).where(GoogleSheetsConnection.id == sync.connection_id)
            )
            connection = connection_result.scalar_one_or_none()
            if not connection:
                run.status = "failed"
                run.error_message = "Google Sheets connection not found"
                run.completed_at = utcnow()
                sync.last_run_status = "failed"
                await db.commit()
                return

            service = GoogleSheetsService(db)
            try:
                run.status = "running"
                run.progress_step = "Exporting data"
                sync.last_run_status = "running"
                await db.commit()

                date_range_days = (sync.parameters or {}).get("date_range_days")
                start_date, end_date = resolve_google_sync_period(
                    sync.frequency,
                    sync.timezone,
                    reference=run.triggered_at,
                    date_range_days=int(date_range_days) if isinstance(date_range_days, int) else None,
                )

                export_request = GoogleSheetsExportRequest(
                    data_types=list(sync.data_types or []),
                    start_date=start_date,
                    end_date=end_date,
                    account_ids=[UUID(account_id) for account_id in (sync.account_ids or [])],
                    spreadsheet_id=sync.spreadsheet_id,
                    name=sync.name,
                    parameters=dict(sync.parameters or {}),
                )
                export_response, rows_written = await service.export_to_sheets(
                    connection,
                    sync.organization_id,
                    export_request,
                    sync_mode=sync.sync_mode,
                )

                sync.spreadsheet_id = export_response.spreadsheet_id
                sync.spreadsheet_url = export_response.spreadsheet_url
                sync.last_run_at = utcnow()
                sync.last_run_status = "completed"
                run.status = "completed"
                run.progress_step = "Sync completed"
                run.completed_at = utcnow()
                run.error_message = None
                run.rows_written = rows_written
                run.spreadsheet_url = export_response.spreadsheet_url
                await db.commit()
            except GoogleReauthRequired as exc:
                logger.warning("Google reauth required for sync run %s", run_id)
                run.status = "failed"
                run.progress_step = "Reconnect Google account"
                run.error_message = str(exc)
                run.completed_at = utcnow()
                sync.last_run_status = "failed"
                sync.last_run_at = run.completed_at
                await db.commit()
            except Exception as exc:
                logger.exception("Google Sheets sync processing failed for %s", run_id)
                run.status = "failed"
                run.progress_step = "Sync failed"
                run.error_message = str(exc)[:500]
                run.completed_at = utcnow()
                sync.last_run_status = "failed"
                sync.last_run_at = run.completed_at
                await db.commit()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_process())
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()
