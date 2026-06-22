"""CSV / XLSX export endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, Response
from sqlmodel import Session

from app.db.database import get_session
from app.services.export import to_csv, to_xlsx
from app.services.query import query_properties

router = APIRouter(prefix="/exports", tags=["exports"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/properties.csv")
def export_csv(
    session: Session = Depends(get_session),
    min_score: Optional[float] = Query(None),
    typology: Optional[str] = Query(None),
    municipality: Optional[str] = Query(None),
    sort: str = Query("score_desc"),
    limit: int = Query(1000, ge=1, le=5000),
):
    results = query_properties(
        session, min_score=min_score, typology=typology,
        municipality=municipality, sort=sort, limit=limit,
    )
    return PlainTextResponse(
        to_csv(results),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=properties.csv"},
    )


@router.get("/properties.xlsx")
def export_xlsx(
    session: Session = Depends(get_session),
    min_score: Optional[float] = Query(None),
    typology: Optional[str] = Query(None),
    municipality: Optional[str] = Query(None),
    sort: str = Query("score_desc"),
    limit: int = Query(1000, ge=1, le=5000),
):
    results = query_properties(
        session, min_score=min_score, typology=typology,
        municipality=municipality, sort=sort, limit=limit,
    )
    return Response(
        to_xlsx(results),
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": "attachment; filename=properties.xlsx"},
    )


@router.get("/sold.csv")
def export_sold_csv(
    session: Session = Depends(get_session),
    limit: int = Query(2000, ge=1, le=5000),
):
    results = query_properties(
        session, only_delisted=True, active_only=False, sort="delisted_desc", limit=limit
    )
    return PlainTextResponse(
        to_csv(results),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sold.csv"},
    )
