from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "export_service.py"
services_pkg = types.ModuleType("app.services")
services_pkg.__path__ = [str(MODULE_PATH.parent)]
sys.modules.setdefault("app.services", services_pkg)

data_extraction_stub = types.ModuleType("app.services.data_extraction")
data_extraction_stub.DAILY_TOTAL_ASIN = "__DAILY_TOTAL__"
sys.modules["app.services.data_extraction"] = data_extraction_stub

SPEC = spec_from_file_location("export_service_under_test", MODULE_PATH)
MODULE = module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

ExportService = MODULE.ExportService
_previous_period = MODULE._previous_period


def test_previous_period_uses_same_inclusive_length():
    prev_start, prev_end = _previous_period(date(2026, 3, 1), date(2026, 3, 31))

    assert prev_start == date(2026, 1, 29)
    assert prev_end == date(2026, 2, 28)


def test_csv_bytes_uses_bom_and_localized_headers():
    service = ExportService(None)  # type: ignore[arg-type]
    rows = [
        {
            "section": "Metadata",
            "metric": "Report Type",
            "current_value": "Sales Report",
            "previous_value": "",
            "change_percent": "",
            "unit": "",
            "notes": "",
        }
    ]

    payload = service._csv_bytes(
        rows,
        ["section", "metric", "current_value", "previous_value", "change_percent", "unit", "notes"],
        "it",
    )

    text = payload.decode("utf-8-sig")
    assert text.startswith("Sezione,Metrica,Valore Attuale")
    assert "Sales Report" in text


def test_inventory_metrics_respects_low_stock_filter():
    service = ExportService(None)  # type: ignore[arg-type]
    rows = [
        {"total_available": 0, "inbound_total": 5, "reserved_quantity": 1},
        {"total_available": 8, "inbound_total": 3, "reserved_quantity": 0},
        {"total_available": 40, "inbound_total": 2, "reserved_quantity": 4},
    ]

    metrics = service._inventory_metrics(rows, True)

    assert metrics["total_skus"] == 3
    assert metrics["exported_rows"] == 2
    assert metrics["low_stock_skus"] == 2
    assert metrics["total_available"] == 48
