"""Google Sheets integration endpoints."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis

from app.api.deps import CurrentOrganization, CurrentUser, DbSession
from app.config import settings
from app.schemas.google_sheets import (
    GoogleSheetsConnectionResponse,
    GoogleSheetsExportRequest,
    GoogleSheetsExportResponse,
    GoogleSheetsSyncCreate,
    GoogleSheetsSyncResponse,
    GoogleSheetsSyncRunResponse,
    GoogleSheetsSyncUpdate,
)
from app.services.google_sheets_service import (
    GoogleReauthRequired,
    GoogleSheetsError,
    GoogleSheetsService,
    enqueue_google_sheets_run_processing,
    google_sheets_connection_to_response,
    google_sheets_sync_run_to_response,
    google_sheets_sync_to_response,
)

router = APIRouter()


def _frontend_settings_url(status_value: str) -> str:
    return (
        f"{settings.APP_FRONTEND_URL.rstrip('/')}/settings"
        f"?tab=integrations&google={status_value}"
    )


async def _oauth_state_redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)


@router.get("/oauth/authorize")
async def get_google_sheets_authorize_url(
    current_user: CurrentUser,
    organization: CurrentOrganization,
):
    """Build a Google OAuth authorize URL."""
    service = GoogleSheetsService(None)  # type: ignore[arg-type]
    try:
        import secrets

        state = secrets.token_urlsafe(32)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate OAuth state") from exc
    redis = await _oauth_state_redis()
    try:
        await redis.setex(
            f"gsheets_oauth:{state}",
            600,
            json.dumps({"user_id": str(current_user.id), "organization_id": str(organization.id)}),
        )
    finally:
        await redis.aclose()

    try:
        auth_url = service.build_auth_url(state)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return {"auth_url": auth_url}


@router.get("/oauth/callback")
async def google_sheets_oauth_callback(
    db: DbSession,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    """Handle the Google OAuth callback and persist the connection."""
    if error:
        return RedirectResponse(url=_frontend_settings_url("error"), status_code=status.HTTP_302_FOUND)
    if not code or not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing OAuth code or state")

    redis = await _oauth_state_redis()
    try:
        raw_state = await redis.get(f"gsheets_oauth:{state}")
        await redis.delete(f"gsheets_oauth:{state}")
    finally:
        await redis.aclose()

    if not raw_state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state")

    try:
        state_payload = json.loads(raw_state)
        user_id = UUID(state_payload["user_id"])
        organization_id = UUID(state_payload["organization_id"])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state payload") from exc

    service = GoogleSheetsService(db)
    try:
        token_payload = await service.exchange_code_for_tokens(code)
        access_token = token_payload.get("access_token")
        if not access_token:
            raise GoogleSheetsError("Google did not return an access token")
        scopes = str(token_payload.get("scope") or "").split() or []
        google_email = await service.fetch_google_user_email(access_token)
        await service.upsert_connection(
            user_id=user_id,
            organization_id=organization_id,
            google_email=google_email,
            refresh_token=token_payload.get("refresh_token"),
            access_token=access_token,
            expires_in=int(token_payload.get("expires_in") or 3600),
            scopes=scopes,
        )
        await db.commit()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except GoogleSheetsError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return RedirectResponse(url=_frontend_settings_url("connected"), status_code=status.HTTP_302_FOUND)


@router.get("/connection", response_model=GoogleSheetsConnectionResponse)
async def get_google_sheets_connection(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get the active Google Sheets connection for the current user and organization."""
    service = GoogleSheetsService(db)
    connection = await service.get_connection(current_user.id, organization.id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google Sheets connection not found")
    return google_sheets_connection_to_response(connection)


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
async def delete_google_sheets_connection(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Disconnect the Google account and remove stored credentials."""
    service = GoogleSheetsService(db)
    connection = await service.get_connection(current_user.id, organization.id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google Sheets connection not found")
    await service.disconnect_connection(connection)
    await db.commit()


@router.post("/export", response_model=GoogleSheetsExportResponse)
async def export_to_google_sheets(
    payload: GoogleSheetsExportRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Export selected datasets directly to Google Sheets."""
    service = GoogleSheetsService(db)
    connection = await service.get_connection(current_user.id, organization.id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google Sheets connection not found")

    try:
        response, _ = await service.export_to_sheets(connection, organization.id, payload)
        await db.commit()
        return response
    except GoogleReauthRequired as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except GoogleSheetsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/syncs", response_model=list[GoogleSheetsSyncResponse])
async def list_google_sheets_syncs(
    _current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """List Google Sheets sync configurations for the organization."""
    service = GoogleSheetsService(db)
    syncs = await service.list_syncs(organization.id)
    return [google_sheets_sync_to_response(sync) for sync in syncs]


@router.post("/syncs", response_model=GoogleSheetsSyncResponse, status_code=status.HTTP_201_CREATED)
async def create_google_sheets_sync(
    payload: GoogleSheetsSyncCreate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Create a new scheduled Google Sheets sync."""
    service = GoogleSheetsService(db)
    connection = await service.get_connection(current_user.id, organization.id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google Sheets connection not found")

    try:
        sync = await service.create_sync(organization, connection, current_user.id, payload)
        await db.commit()
        await db.refresh(sync)
        return google_sheets_sync_to_response(sync)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.put("/syncs/{sync_id}", response_model=GoogleSheetsSyncResponse)
async def update_google_sheets_sync(
    sync_id: UUID,
    payload: GoogleSheetsSyncUpdate,
    _current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Update a Google Sheets sync configuration."""
    service = GoogleSheetsService(db)
    sync = await service.get_sync(sync_id, organization.id)
    if not sync:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google Sheets sync not found")

    try:
        updated = await service.update_sync(sync, organization, payload)
        await db.commit()
        await db.refresh(updated)
        return google_sheets_sync_to_response(updated)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/syncs/{sync_id}/toggle", response_model=GoogleSheetsSyncResponse)
async def toggle_google_sheets_sync(
    sync_id: UUID,
    _current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    enabled: bool = Query(...),
):
    """Enable or disable a Google Sheets sync."""
    service = GoogleSheetsService(db)
    sync = await service.get_sync(sync_id, organization.id)
    if not sync:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google Sheets sync not found")

    updated = await service.toggle_sync(sync, enabled)
    await db.commit()
    await db.refresh(updated)
    return google_sheets_sync_to_response(updated)


@router.delete("/syncs/{sync_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_google_sheets_sync(
    sync_id: UUID,
    _current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Delete a Google Sheets sync."""
    service = GoogleSheetsService(db)
    sync = await service.get_sync(sync_id, organization.id)
    if not sync:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google Sheets sync not found")
    await service.delete_sync(sync)
    await db.commit()


@router.post("/syncs/{sync_id}/run-now", response_model=GoogleSheetsSyncRunResponse)
async def run_google_sheets_sync_now(
    sync_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Queue an immediate Google Sheets sync run."""
    service = GoogleSheetsService(db)
    sync = await service.get_sync(sync_id, organization.id)
    if not sync:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google Sheets sync not found")

    run = await service.create_run(sync)
    await db.commit()
    enqueue_google_sheets_run_processing(str(run.id))
    await db.refresh(run)
    return google_sheets_sync_run_to_response(run)


@router.get("/syncs/{sync_id}/runs", response_model=list[GoogleSheetsSyncRunResponse])
async def list_google_sheets_sync_runs(
    sync_id: UUID,
    _current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
):
    """List run history for a Google Sheets sync."""
    service = GoogleSheetsService(db)
    sync = await service.get_sync(sync_id, organization.id)
    if not sync:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google Sheets sync not found")

    runs = await service.list_runs(sync_id, organization.id, limit=limit)
    return [google_sheets_sync_run_to_response(run) for run in runs]
