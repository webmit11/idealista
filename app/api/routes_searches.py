"""Search profile endpoints."""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db.database import get_session
from app.db.models import SearchProfile
from app.schemas import SearchProfileCreate

router = APIRouter(prefix="/search-profiles", tags=["search-profiles"])


@router.get("")
def list_profiles(session: Session = Depends(get_session)):
    return session.exec(select(SearchProfile)).all()


@router.post("")
def create_profile(payload: SearchProfileCreate, session: Session = Depends(get_session)):
    profile = SearchProfile(**payload.model_dump())
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile
