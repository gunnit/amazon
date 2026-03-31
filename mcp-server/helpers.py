import json
import uuid
from datetime import date, datetime
from decimal import Decimal


class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for database types."""

    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def to_json(data) -> str:
    return json.dumps(data, cls=JSONEncoder, ensure_ascii=False)


def row_to_dict(row) -> dict:
    return dict(row._mapping)


def rows_to_list(rows) -> list[dict]:
    return [dict(r._mapping) for r in rows]
