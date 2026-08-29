"""Keep one test module's import-time stubs out of the next module's imports.

Several test modules import a service in isolation by installing fake `app.*`
packages into ``sys.modules`` before importing it, and never take them back
out. Whether a later module then gets the real `app.api.deps` or somebody's
stub depends on alphabetical file order, which is why the suite collects fine
per file and reports a wall of ImportErrors in a single process.

The repair is narrow on purpose. After a test module has been imported we
compare `sys.modules` against the snapshot taken before it, and only:

* put back a real module that was replaced by a stub, and
* drop a stub that was newly installed.

Real modules imported along the way stay cached. Evicting those instead would
re-execute the SQLAlchemy model modules and blow up on re-registered mappers —
which is exactly what happens if you try to fix this with a blunt purge.
"""
import sys

import pytest

_TRACKED_PREFIXES = ("app.", "workers.")
_snapshots: dict[str, dict] = {}


def _is_stub(module) -> bool:
    """A module with no file behind it was built by a test, not imported."""
    return getattr(module, "__file__", None) is None


def _tracked(name: str) -> bool:
    return name in ("app", "workers") or name.startswith(_TRACKED_PREFIXES)


def _restore(before: dict) -> None:
    """Undo the tracked stubbing a test module or test did to sys.modules."""
    for name, module in list(sys.modules.items()):
        if not _tracked(name):
            continue
        previous = before.get(name)
        if previous is module:
            continue
        if previous is not None:
            sys.modules[name] = previous
        elif _is_stub(module):
            del sys.modules[name]

    # Put back real modules that were evicted. Leaving them out would let the
    # next importer re-execute them, and re-executing a model module
    # re-registers its table on the shared MetaData ("Table 'x' is already
    # defined"). The stubs used to shadow those imports by accident; now that
    # they are gone, this is what keeps the models loaded exactly once.
    for name, module in before.items():
        if _tracked(name) and name not in sys.modules and not _is_stub(module):
            sys.modules[name] = module


@pytest.fixture(autouse=True)
def _isolate_sys_modules():
    """Same repair around each test.

    Some modules stub `app.config` or the Celery decorators from inside a
    fixture rather than at import time, so collection-time cleanup alone does
    not catch them.
    """
    before = dict(sys.modules)
    yield
    _restore(before)


def pytest_collectstart(collector):
    if isinstance(collector, pytest.Module):
        _snapshots[collector.nodeid] = dict(sys.modules)


def pytest_collectreport(report):
    before = _snapshots.pop(report.nodeid, None)
    if before is not None:
        _restore(before)
