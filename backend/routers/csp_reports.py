"""Endpoint browsers post Content-Security-Policy violation reports to."""

import json

from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from backend.config import get_settings
from backend.services.csp_report_service import (
    MAX_BODY_BYTES,
    append_csp_reports,
    csp_report_log_path,
    parse_csp_reports,
)

router = APIRouter()


@router.post("/csp-reports", status_code=204, include_in_schema=False)
async def receive_csp_reports(request: Request) -> Response:
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return Response(status_code=413)
    try:
        payload = json.loads(body)
    except ValueError:
        return Response(status_code=400)
    path = csp_report_log_path(get_settings())
    if path is not None:
        await run_in_threadpool(append_csp_reports, parse_csp_reports(payload), path)
    return Response(status_code=204)
