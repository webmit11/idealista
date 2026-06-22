"""Import endpoints (mock / Apify)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db.database import get_session
from app.schemas import ImportApifyRequest, ImportMockRequest
from app.services.ingest import run_import
from app.services.providers.apify_idealista import ApifyIdealistaProvider
from app.services.providers.base import SearchInput
from app.services.providers.mock_provider import MockProvider

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/mock")
def import_mock(
    payload: Optional[ImportMockRequest] = None,
    session: Session = Depends(get_session),
):
    provider = MockProvider(path=payload.path if payload else None)
    return run_import(session, provider)


@router.post("/apify")
def import_apify(
    payload: Optional[ImportApifyRequest] = None,
    session: Session = Depends(get_session),
):
    provider = ApifyIdealistaProvider()
    search = SearchInput(
        urls=payload.urls if payload else [],
        max_items=payload.max_items if payload else None,
    )
    try:
        return run_import(
            session, provider, search,
            deactivate_missing=payload.deactivate_missing if payload else False,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
