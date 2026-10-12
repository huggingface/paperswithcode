"""Public framework catalogue endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.taxonomy import FrameworkCatalog
from backend.services.framework_service import FrameworkService

router = APIRouter(prefix="/frameworks", tags=["frameworks"])


@router.get("/", response_model=FrameworkCatalog)
def get_framework_catalog(
    db: Session = Depends(get_database_session),
) -> FrameworkCatalog:
    return FrameworkService(db).get_catalog()
