# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import importlib
import io
import subprocess
import sys
import threading
import zipfile
from importlib.abc import Loader
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any

from pytest import fixture, mark, raises

from hydra import compose, initialize_config_module
from hydra._internal.core_plugins.importlib_resources_config_source import (
    ImportlibResourcesConfigSource,
)
from hydra.core.plugins import Plugins
from hydra.core.singleton import Singleton
from hydra.plugins.config_source import ConfigLoadError


@fixture(params=["source", "compiled", "zip", "namespace_parent"])
def config_package(request: Any, tmp_path: Path, monkeypatch: Any) -> Any:
    # Register built-in config classes before a test snapshots singleton state.
    Plugins.instance()
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
        Singleton.get_state()
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


def test_package_containment(config_package: str) -> None:
    source = ImportlibResourcesConfigSource("test", f"pkg://{config_package}")
    for operation in (source.load_config, source.is_config, source.is_group):
        with raises(ConfigLoadError, match="outside"):
            operation("../outside")
    with raises(ConfigLoadError, match="outside"):
        source.list("../outside", None)
    assert source.load_config("dataset/../config").config == {
        "defaults": [{"dataset": "sample"}, "_self_"],
        "value": 10,
    }


def test_package_root_is_cached(config_package: str, monkeypatch: Any) -> None:
    from hydra._internal.core_plugins import importlib_resources_config_source as pkg

    original = pkg.resources.files
    calls = []

    def files(package: Any) -> Any:
        calls.append(package)
        return original(package)

    monkeypatch.setattr(pkg.resources, "files", files)
    source = ImportlibResourcesConfigSource("test", f"pkg://{config_package}")
    assert source.available()
    assert source.is_config("config")
    assert source.load_config("dataset/sample").config == {"kind": "sample"}
    assert len(calls) == 1


def test_package_native_links(tmp_path: Path, monkeypatch: Any) -> None:
    name = "config_containment_links"
    package = tmp_path / name
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "config.yaml").write_text("value: 10\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "config.yaml").write_text("value: outside\n", encoding="utf-8")
    try:
        (package / "internal.yaml").symlink_to(package / "config.yaml")
        (package / "escape").symlink_to(outside, target_is_directory=True)
        (package / "escape.yaml").symlink_to(outside / "config.yaml")
    except OSError as error:
        from pytest import skip

        skip(f"Symlink creation is unavailable: {error}")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        source = ImportlibResourcesConfigSource("test", f"pkg://{name}")
        assert source.load_config("internal").config == {"value": 10}
        assert source.list("", None) == ["config", "internal"]
        with raises(ConfigLoadError, match="outside"):
            source.load_config("escape/config")
        if sys.platform == "win32":
            assert source.load_config("escape/../config").config == {"value": 10}
        else:
            with raises(ConfigLoadError, match="outside"):
                source.load_config("escape/../config")
        with raises(ConfigLoadError, match="outside"):
            source.list("escape", None)
    finally:
        sys.modules.pop(name, None)


@fixture
def virtual_package(monkeypatch: Any) -> Any:
    Plugins.instance()
    calls: list[str] = []

    class Resource:
        def __init__(self, name: str = "") -> None:
            self.name = name
            self.lock = threading.Lock()

        def joinpath(self, path: str) -> Any:
            return Resource(path)

        def is_file(self) -> bool:
            return self.name == "config.yaml"

        def is_dir(self) -> bool:
            return self.name == ""

        def iterdir(self) -> Any:
            return iter([Resource("config.yaml")])

        def open(self, **kwargs: Any) -> Any:
            calls.append(self.name)
            assert self.is_file()
            return io.StringIO("value: 10\n")

    class Reader:
        def open_resource(self, resource: str) -> Any:
            calls.append(resource)
            assert resource == "config.yaml"
            return io.BytesIO(b"value: 10\n")

        def resource_path(self, resource: str) -> str:
            raise FileNotFoundError(resource)

        def is_resource(self, resource: str) -> bool:
            return resource == "config.yaml"

        def contents(self) -> list[str]:
            return ["config.yaml"]

        def files(self) -> Resource:
            return Resource()

    class VirtualLoader(Loader):
        def get_resource_reader(self, fullname: str) -> Reader:
            return Reader()

    module = ModuleType("config_containment_virtual")
    module.__spec__ = ModuleSpec(module.__name__, VirtualLoader(), is_package=True)
    module.__spec__.origin = "trusted-virtual-package"
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return ImportlibResourcesConfigSource("test", f"pkg://{module.__name__}"), calls


def test_rooted_resource_reader_containment(
    virtual_package: Any, hydra_restore_singletons: Any
) -> None:
    source, calls = virtual_package
    assert source.available()
    assert source.list("", None) == ["config"]
    assert source.load_config("./config").config.value == 10
    for path in ("../config", "/config", "C:config", r"dir\config"):
        with raises(ConfigLoadError):
            source.load_config(path)
    assert calls == ["config.yaml"]
    with initialize_config_module(config_module=source.path):
        assert compose(config_name="config") == {"value": 10}


@mark.skipif(
    sys.version_info < (3, 11), reason="Legacy reader adapter requires Python 3.11"
)
def test_legacy_resource_reader_containment(
    virtual_package: Any, monkeypatch: Any
) -> None:
    source, calls = virtual_package
    module: Any = sys.modules[source.path]
    reader = module.__spec__.loader.get_resource_reader(source.path)
    monkeypatch.delattr(type(reader), "files")
    assert source.list("", None) == ["config"]
    assert source.load_config("config").config.value == 10
    with raises(ConfigLoadError):
        source.load_config("../config")
    assert calls == ["config.yaml"]


@mark.skipif(sys.version_info < (3, 12), reason="Default joinpath requires Python 3.12")
def test_missing_default_traversable(virtual_package: Any, monkeypatch: Any) -> None:
    from importlib.resources.abc import Traversable

    from hydra._internal.core_plugins import importlib_resources_config_source as pkg

    class EmptyRoot(Traversable):
        @property
        def name(self) -> str:
            return "empty"

        def iterdir(self) -> Any:
            return iter(())

        def is_file(self) -> bool:
            return False

        def is_dir(self) -> bool:
            return True

        def open(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("Missing resources must not be opened")

    # Runtime Traversable provides concrete defaults absent from older stubs.
    root_type: Any = EmptyRoot
    monkeypatch.setattr(pkg.resources, "files", lambda package: root_type())
    source, calls = virtual_package
    assert not source.is_config("missing")
    assert not source.is_group("missing")
    with raises(ConfigLoadError, match="Config not found : missing.yaml"):
        source.load_config("missing")
    assert calls == []


@mark.parametrize("kind", ["unsupported", "concrete_candidate", "invalid_child"])
def test_unestablished_package_root(
    kind: str, virtual_package: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    from hydra._internal.core_plugins import importlib_resources_config_source as pkg

    class Root:
        name = "root"

        def joinpath(self, path: str) -> Any:
            if kind == "concrete_candidate":
                return tmp_path / "outside.yaml"
            return self

        def open(self, **kwargs: Any) -> Any:
            raise AssertionError("Unestablished resource must not be opened")

        def is_file(self) -> bool:
            return True

        def is_dir(self) -> bool:
            return False

        def iterdir(self) -> Any:
            child = Root()
            child.name = "../outside.yaml"
            return iter([child])

    root = object() if kind == "unsupported" else Root()
    monkeypatch.setattr(pkg.resources, "files", lambda package: root)
    source, _ = virtual_package
    with raises(ConfigLoadError, match="containment|resource name"):
        if kind == "invalid_child":
            source.list("", None)
        else:
            source.load_config("config")
