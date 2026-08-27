"""Generate the technical pages of /docs from the code itself.

Run from backend/:  venv/bin/python scripts/gen_tech_docs.py

Everything here is read out of the source, so re-running after a change keeps
the pages honest. Prose that explains *why* lives in tech-architecture.md and is
hand-written — no generator can recover a decision that was never in the code.
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = ROOT.parent
OUT = [REPO / "frontend/src/content/docs/it", REPO / "frontend/src/content/docs/en"]

sys.path.insert(0, str(ROOT))


def scheduler_jobs() -> list[tuple[str, str, str]]:
    """(job id, entrypoint, trigger) for every scheduler.add_job in main.py."""
    src = (ROOT / "app/main.py").read_text()
    tree = ast.parse(src)
    jobs = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "add_job":
            continue
        entry = ast.unparse(node.args[0]) if node.args else "?"
        trigger = ast.unparse(node.args[1]) if len(node.args) > 1 else "?"
        job_id = next(
            (ast.literal_eval(k.value) for k in node.keywords
             if k.arg == "id" and isinstance(k.value, ast.Constant)),
            "?",
        )
        jobs.append((job_id, entry, " ".join(trigger.split())))
    return jobs


def api_routes() -> dict[str, list[tuple[str, str]]]:
    """{module: [(method, path)]} parsed from the @router decorators."""
    routes: dict[str, list[tuple[str, str]]] = {}
    for path in sorted((ROOT / "app/api/v1").glob("*.py")):
        if path.name in ("__init__.py", "router.py"):
            continue
        found = []
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            for dec in node.decorator_list:
                call = dec if isinstance(dec, ast.Call) else None
                func = call.func if call else dec
                if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
                    continue
                if func.value.id != "router" or func.attr not in {
                    "get", "post", "put", "patch", "delete"
                }:
                    continue
                route = ""
                if call and call.args and isinstance(call.args[0], ast.Constant):
                    route = call.args[0].value
                found.append((func.attr.upper(), route or "/"))
        if found:
            routes[path.stem] = found
    return routes


def prefixes() -> dict[str, str]:
    """{module: url prefix} from the include_router calls."""
    src = (ROOT / "app/api/v1/router.py").read_text()
    out = {}
    for mod, prefix in re.findall(r"(\w+)\.router,\s*prefix=\"([^\"]+)\"", src):
        out[mod] = prefix
    return out


def tables() -> list[tuple[str, int, list[str]]]:
    """(table, column count, foreign keys) straight from the SQLAlchemy metadata."""
    import app.models  # noqa: F401  — registers every mapper
    from app.db.base import Base

    rows = []
    for name, table in sorted(Base.metadata.tables.items()):
        fks = sorted({fk.column.table.name for fk in table.foreign_keys})
        rows.append((name, len(table.columns), fks))
    return rows


def settings_fields() -> list[tuple[str, str, str]]:
    """(name, type, default) for every field on the Settings class."""
    tree = ast.parse((ROOT / "app/config.py").read_text())
    cls = next(
        n for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "Settings"
    )
    out = []
    for node in cls.body:
        if not (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)):
            continue
        default = ast.unparse(node.value) if node.value else "required"
        if any(s in node.target.id for s in ("SECRET", "KEY", "PASSWORD", "TOKEN")):
            default = "—"
        out.append((node.target.id, ast.unparse(node.annotation), default))
    return out


def migrations() -> list[str]:
    d = ROOT / "app/db/migrations/versions"
    return sorted(p.stem for p in d.glob("*.py")) if d.exists() else []


def build() -> dict[str, str]:
    jobs = scheduler_jobs()
    routes = api_routes()
    pref = prefixes()
    tbls = tables()
    cfg = settings_fields()
    migs = migrations()

    stamp = ("> Generated from the source by `backend/scripts/gen_tech_docs.py`. "
             "Re-run it after changing the code; do not edit this page by hand.\n")

    scheduler = [f"# Scheduled jobs\n", stamp,
                 f"\nThe API process runs its own scheduler, so there is no Celery worker "
                 f"in production. {len(jobs)} jobs are registered in `app/main.py`.\n",
                 "\n## Job table\n\n",
                 "| Job id | Entrypoint | Trigger |\n| --- | --- | --- |\n"]
    for job_id, entry, trigger in jobs:
        scheduler.append(f"| `{job_id}` | `{entry}` | `{trigger}` |\n")

    api = [f"# API surface\n", stamp,
           f"\n{sum(len(v) for v in routes.values())} endpoints across "
           f"{len(routes)} routers, all under `/api/v1`.\n"]
    for mod in sorted(routes):
        api.append(f"\n## {mod}\n\n")
        api.append(f"Prefix `{pref.get(mod, '')}`.\n\n")
        api.append("| Method | Path |\n| --- | --- |\n")
        for method, route in routes[mod]:
            api.append(f"| {method} | `{pref.get(mod, '')}{route.rstrip('/') or ''}` |\n")

    data = [f"# Data model\n", stamp,
            f"\n{len(tbls)} tables, read from the SQLAlchemy metadata.\n",
            "\n## Tables\n\n",
            "| Table | Columns | References |\n| --- | --- | --- |\n"]
    for name, cols, fks in tbls:
        data.append(f"| `{name}` | {cols} | {', '.join(f'`{f}`' for f in fks) or '—'} |\n")
    data.append(f"\n## Migrations\n\n{len(migs)} revisions, applied on deploy by "
                "`alembic upgrade head` in the start command.\n\n")
    for m in migs:
        data.append(f"- `{m}`\n")

    conf = [f"# Configuration\n", stamp,
            "\nEvery setting on `Settings` in `app/config.py`. Secrets show `—` instead "
            "of a default. `required` means there is no default and the environment must "
            "provide it.\n",
            "\n## Settings\n\n",
            "| Setting | Type | Default |\n| --- | --- | --- |\n"]
    for name, typ, default in cfg:
        conf.append(f"| `{name}` | `{typ}` | `{default}` |\n")

    return {
        "tech-scheduler.md": "".join(scheduler),
        "tech-api.md": "".join(api),
        "tech-data-model.md": "".join(data),
        "tech-config.md": "".join(conf),
    }


if __name__ == "__main__":
    pages = build()
    for directory in OUT:
        directory.mkdir(parents=True, exist_ok=True)
        for name, body in pages.items():
            (directory / name).write_text(body)
    counts = {n: b.count("\n") for n, b in pages.items()}
    print("written to", ", ".join(str(d) for d in OUT))
    for name, lines in counts.items():
        print(f"  {name}: {lines} lines")
