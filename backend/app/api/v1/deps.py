"""
Shared FastAPI dependencies: authentication and per-deal authorization.

require_deal_owner is the fix for the core IDOR issue — every deal-scoped
endpoint should depend on this instead of loading the deal itself, so
"does this deal exist" and "does it belong to the caller" are checked in
exactly one place rather than reimplemented per-endpoint.
"""

from fastapi import Depends, HTTPException, Request

from app.security.jwt_tokens import TokenError, decode_access_token
from app.storage import deal_store, user_store

SESSION_COOKIE_NAME = "tam_session"


def get_current_user(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        user_id = decode_access_token(token)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = user_store.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Session refers to a user that no longer exists")
    return user


def require_deal_owner(deal_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    """Load a deal and verify the authenticated caller owns it. Use this in
    place of a bare deal_store.get_deal() call on every deal-scoped route."""
    deal = deal_store.get_deal(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    if deal.get("owner_user_id") != current_user["id"]:
        # 404, not 403: don't confirm the deal_id even exists to a caller who
        # doesn't own it — avoids leaking valid-UUID information via status code.
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    return deal
