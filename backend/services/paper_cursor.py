"""Opaque keyset cursors for walking the whole paper catalog in a stable order."""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Query

from backend.models.database import Paper as DBPaper

CURSOR_ORDER_FIELDS = {
    "date_published": DBPaper.date_published,
    "citation_count": DBPaper.citation_count,
}


class InvalidPaperCursorError(ValueError):
    pass


def _is_bigint(value: object) -> bool:
    return type(value) is int and -(2**63) <= value < 2**63


def _valid_value(order_by: str, value: object) -> bool:
    if value is None:
        return True
    if order_by == "citation_count":
        return _is_bigint(value)
    if type(value) is not str:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class PaperCursor:
    order_by: str
    order_dir: str
    value: Optional[str | int]
    paper_id: int

    def encode(self) -> str:
        payload = json.dumps(
            [self.order_by, self.order_dir, self.value, self.paper_id],
            separators=(",", ":"),
        )
        return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")

    @classmethod
    def decode(cls, token: str, order_by: str, order_dir: str) -> "PaperCursor":
        try:
            padded = token + "=" * (-len(token) % 4)
            fields = json.loads(base64.urlsafe_b64decode(padded.encode()))
            cursor_order, cursor_dir, value, paper_id = fields
        except (binascii.Error, UnicodeDecodeError, ValueError, TypeError) as error:
            raise InvalidPaperCursorError("cursor is malformed") from error
        if (cursor_order, cursor_dir) != (order_by, order_dir):
            raise InvalidPaperCursorError(
                "cursor was issued for a different order_by or order_dir"
            )
        if not _is_bigint(paper_id) or not _valid_value(order_by, value):
            raise InvalidPaperCursorError("cursor is malformed")
        return cls(order_by, order_dir, value, paper_id)

    @classmethod
    def after(cls, paper: DBPaper, order_by: str, order_dir: str) -> "PaperCursor":
        value = getattr(paper, order_by)
        if isinstance(value, date):
            value = value.isoformat()
        return cls(order_by, order_dir, value, int(paper.id))

    def sort_value(self):
        if self.order_by == "date_published" and self.value is not None:
            return date.fromisoformat(self.value)
        return self.value

    def apply(self, query: Query) -> Query:
        field = CURSOR_ORDER_FIELDS[self.order_by]
        descending = self.order_dir == "desc"
        id_after = (
            DBPaper.id < self.paper_id if descending else DBPaper.id > self.paper_id
        )
        if self.value is None:
            return query.filter(field.is_(None), id_after)
        value = self.sort_value()
        value_after = field < value if descending else field > value
        return query.filter(
            or_(value_after, and_(field == value, id_after), field.is_(None))
        )
