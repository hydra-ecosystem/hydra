# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import importlib
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

from pytest import fixture, mark, raises

from hydra import compose, initialize_config_module
from hydra._internal.core_plugins.importlib_resources_config_source import (
    ImportlibResourcesConfigSource,
)


@fixture(params=["source", "compiled", "zip", "namespace_parent"])
def config_package(request: Any, tmp_path: Path, monkeypatch: Any) -> Any:
    name = f"config_fixture_2412_{request.param}"
    package = tmp_path / name
    package.mkdir()
    module_name = name
    if request.param == "namespace_parent":
        package = package / "conf"
        package.mkdir()
        module_name += ".conf"

    if request.param == "compiled":
        (tmp_path / "initializer.c").write_text(
            "#include <Python.h>\n"
            f'static struct PyModuleDef module = {{PyModuleDef_HEAD_INIT, "{name}", NULL, -1, NULL}};\n'
            f"PyMODINIT_FUNC PyInit_{name}(void) {{ return PyModule_Create(&module); }}\n",
            encoding="utf-8",
        )
        (tmp_path / "setup.py").write_text(
            "from setuptools import Extension, setup\n"
            f"setup(name={name!r}, ext_modules=[Extension({name!r}, ['initializer.c'])])\n",
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, "setup.py", "build_ext", "--build-lib", str(tmp_path)],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        binary = next(path for path in tmp_path.glob(f"{name}.*") if path.is_file())
        binary.rename(package / ("__init__" + binary.name[len(name) :]))
    else:
        (package / "__init__.py").write_text("", encoding="utf-8")

    (package / "dataset").mkdir()
    (package / "config.yaml").write_text(
        "defaults:\n  - dataset: sample\n  - _self_\nvalue: 10\n", encoding="utf-8"
    )
    (package / "dataset" / "sample.yaml").write_text("kind: sample\n", encoding="utf-8")
    search_path = tmp_path
    if request.param == "zip":
        search_path = tmp_path / "configs.zip"
        with zipfile.ZipFile(search_path, "w") as archive:
            for path in package.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(tmp_path))
    monkeypatch.syspath_prepend(str(search_path))
    yield module_name
    sys.modules.pop(module_name, None)
    sys.modules.pop(name, None)
    importlib.invalidate_caches()


def test_package_resources_compose(
    config_package: str, hydra_restore_singletons: Any
) -> None:
    source = ImportlibResourcesConfigSource("test", f"pkg://{config_package}")
    assert source.available()
    assert source.is_group("dataset")
    assert source.is_config("dataset/sample")
    assert source.list("", None) == ["config", "dataset"]
    assert source.load_config("dataset/sample").config == {"kind": "sample"}
    with initialize_config_module(config_module=config_package):
        cfg = compose(config_name="config")
    assert cfg == {"dataset": {"kind": "sample"}, "value": 10}


@mark.parametrize("kind", ["module", "namespace"])
def test_non_package_sources_are_unavailable(
    kind: str, tmp_path: Path, monkeypatch: Any
) -> None:
    name = f"non_package_2412_{kind}"
    if kind == "module":
        (tmp_path / f"{name}.py").write_text("", encoding="utf-8")
        resources = tmp_path
    else:
        resources = tmp_path / name
        resources.mkdir()
    (resources / "config.yaml").write_text("value: 10\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    source = ImportlibResourcesConfigSource("test", f"pkg://{name}")
    try:
        assert not source.available()
        assert not source.is_group("")
        assert not source.is_config("config")
        with raises((TypeError, ValueError)):
            source.load_config("config")
        with raises((TypeError, ValueError)):
            source.list("", None)
    finally:
        sys.modules.pop(name, None)
