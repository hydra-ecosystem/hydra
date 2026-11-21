# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT

"""Disposable design evidence; this does not implement authorization checks."""

import importlib
import importlib.metadata
import importlib.resources
import json
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from hydra.core.config_store import ConfigStore
from hydra.utils import instantiate

results = {"python": sys.version.split()[0]}
with tempfile.TemporaryDirectory() as scratch:
    root = Path(scratch)
    package = root / "probe_authorization_resources"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "config.yaml").write_text("value: 1\n")
    sys.path.insert(0, str(root))
    try:
        module = importlib.import_module(package.name)
        resources = importlib.resources.files(module)
        results["directory"] = {
            "is_path": isinstance(resources, Path),
            "value": resources.joinpath("config.yaml").read_text().strip(),
        }
    finally:
        sys.path.pop(0)
        sys.modules.pop(package.name, None)
    archive = root / "configs.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("probe_archive_resources/__init__.py", "")
        output.writestr("probe_archive_resources/config.yaml", "value: 2\n")
        output.writestr("sibling/config.yaml", "outside: true\n")
    sys.path.insert(0, str(archive))
    importlib.invalidate_caches()
    try:
        module = importlib.import_module("probe_archive_resources")
        resources = importlib.resources.files(module)
        results["archive"] = {
            "is_zip_path": isinstance(resources, zipfile.Path),
            "root_at": resources.at,
            "value": resources.joinpath("config.yaml").read_text().strip(),
        }
    finally:
        sys.path.pop(0)
        sys.modules.pop(module.__name__, None)
        importlib.invalidate_caches()
entry = importlib.metadata.EntryPoint(
    name="selected",
    value="not_imported_plugin.module:Plugin.Inner",
    group="hydra.plugins",
)
results["metadata_without_import"] = {
    "module": entry.module,
    "attribute": entry.attr,
    "module_imported": entry.module in sys.modules,
}

factory_calls = []


def record_factory():
    factory_calls.append("factory")
    return 1


@dataclass
class ConfigData:
    value: int = field(default_factory=record_factory)


ConfigStore.instance().store(name="__authorization_guard_probe__", node=ConfigData)
store_calls = len(factory_calls)
factory_calls.clear()
converted = instantiate(ConfigData, _execution_whitelist_=[])
results["structured_conversion"] = {
    "config_store_factory_calls": store_calls,
    "instantiate_factory_calls": len(factory_calls),
    "converted_value": converted.value,
}
print(json.dumps(results, sort_keys=True, indent=2))
