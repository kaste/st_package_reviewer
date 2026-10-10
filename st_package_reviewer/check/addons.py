import hashlib
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import sys

from . import find_all


def find_additional(path, base_class, exclude=()):
    """Load checkers from a trusted directory in an isolated package namespace."""
    path = Path(path).expanduser().resolve()
    if not path.is_dir():
        raise ValueError("Checker path is not a directory: {}".format(path))

    # Two addons may have the same folder name. Do not modify sys.path or shadow
    # packages already imported by the caller (including the reviewer itself).
    digest = hashlib.sha256(os.path.normcase(str(path)).encode()).hexdigest()
    package = "_st_package_reviewer_addon_" + digest
    try:
        if package not in sys.modules:
            _load_package(path, package)
        return find_all(path, package, base_class=base_class, exclude=tuple(exclude))
    except Exception as exc:
        # Allow a failed import to be fixed and retried in the same process.
        for name in tuple(sys.modules):
            if name == package or name.startswith(package + "."):
                del sys.modules[name]
        raise ImportError("Unable to load checkers from {}: {}".format(path, exc)) from exc


def _load_package(path, package):
    init = path / "__init__.py"
    if init.is_file():
        spec = importlib.util.spec_from_file_location(
            package, init, submodule_search_locations=[str(path)],
        )
    else:
        spec = importlib.machinery.ModuleSpec(package, loader=None, is_package=True)
        spec.submodule_search_locations = [str(path)]

    module = importlib.util.module_from_spec(spec)
    sys.modules[package] = module
    if init.is_file():
        spec.loader.exec_module(module)
