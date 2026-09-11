from datetime import date
from typing import Annotated

from fastapi import HTTPException, Query

from backend.models.papers import PaperDateRange


def get_paper_date_range(
    start_date: Annotated[
        date | None,
        Query(description="Inclusive earliest publication date (YYYY-MM-DD)"),
    ] = None,
    end_date: Annotated[
        date | None,
        Query(description="Inclusive latest publication date (YYYY-MM-DD)"),
    ] = None,
) -> PaperDateRange:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date",
        )
    return PaperDateRange(start_date=start_date, end_date=end_date)
