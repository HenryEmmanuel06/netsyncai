"""Device pairing endpoints.

Flow: signed-in owner POSTs /pairing → gets a short-lived code → the
desktop app (opened via a netsync://pair link, or the user types the code)
GETs /pairing/preview to show "Connect this PC to <email>?" → on the
user's local confirmation it POSTs /pairing/redeem → device_id + scoped
credential. Redeem and preview are intentionally not JWT-authed: the code
IS the authorization. Codes are 8 chars (~40 bits), single-use, 10-min TTL.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import current_auth, get_device_store
from app.errors import http_401
from app.schemas.pairing import (
    PairingCreateRequest,
    PairingCreateResponse,
    PairingPreviewResponse,
    PairingRedeemRequest,
    PairingRedeemResponse,
)
from app.security.jwt import AuthContext
from app.services.activity import log_activity
from app.services.device_registry import DeviceStore, PairingError

router = APIRouter(prefix="/pairing", tags=["pairing"])

PAIRING_TTL_SECONDS = 600  # 10 minutes


@router.post("", response_model=PairingCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_pairing(
    req: PairingCreateRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
) -> PairingCreateResponse:
    code, expires = await store.create_pairing(
        auth.user_id, req.device_name, PAIRING_TTL_SECONDS, owner_email=auth.email
    )
    return PairingCreateResponse(
        code=code, expires_at=expires, expires_in_seconds=PAIRING_TTL_SECONDS
    )


@router.get("/preview", response_model=PairingPreviewResponse)
async def preview_pairing(
    code: str,
    store: DeviceStore = Depends(get_device_store),
) -> PairingPreviewResponse:
    try:
        return PairingPreviewResponse(**await store.preview_pairing(code))
    except PairingError as exc:
        raise http_401(str(exc)) from exc


@router.post("/redeem", response_model=PairingRedeemResponse)
async def redeem_pairing(
    req: PairingRedeemRequest,
    store: DeviceStore = Depends(get_device_store),
) -> PairingRedeemResponse:
    try:
        device, credential, owner_email = await store.redeem_pairing(
            req.code, req.agent_version, machine_id=req.machine_id
        )
    except PairingError as exc:
        raise http_401(str(exc)) from exc
    await log_activity(store, device.owner_id, "device.paired",
                       device_id=device.id, target=device.name)
    return PairingRedeemResponse(
        device_id=device.id,
        device_name=device.name,
        device_credential=credential,
        owner_email=owner_email,
    )
