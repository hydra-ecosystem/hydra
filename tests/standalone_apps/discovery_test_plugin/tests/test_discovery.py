# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import os
from pathlib import Path

from hydra_plugins import discovery_test

from hydra.core.plugins import Plugins


def test_number_of_imports(tmpdir: Path) -> None:
    os.environ["TMP_FILE"] = str(tmpdir / "import.log")
    # Exercise namespace scanning independently of the fixture's entry points.
    plugins, _ = Plugins._scan_all_plugins([discovery_test])
    assert "DiscoveryTestPlugin" in [x.__name__ for x in plugins]

    f = Path(os.environ["TMP_FILE"])
    txt = str(f.read_text())
    assert txt.split("\n").count("imported") == 1


def test_skipped_imports(tmpdir: Path) -> None:
    # Tests that modules starting with an "_" (but not "__") are skipped

    plugins, _ = Plugins._scan_all_plugins([discovery_test])
    discovered_plugins = [x.__name__ for x in plugins]
    assert "HiddenTestPlugin" not in discovered_plugins

    assert "NotHiddenTestPlugin" in discovered_plugins
