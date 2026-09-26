# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import subprocess
import sys
from email.parser import Parser
from pathlib import Path

import pytest

PLUGINS = Path(__file__).resolve().parents[1] / "plugins"


@pytest.mark.parametrize("plugin", sorted(PLUGINS.glob("*/setup.py")))
def test_bundled_plugin_requires_matching_core_line(
    plugin: Path, tmp_path: Path
) -> None:
    subprocess.run(
        [sys.executable, "setup.py", "egg_info", "--egg-base", str(tmp_path)],
        cwd=plugin.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    (metadata_path,) = tmp_path.glob("*.egg-info/PKG-INFO")
    metadata = Parser().parsestr(metadata_path.read_text())
    major, minor = (int(part) for part in metadata["Version"].split(".")[:2])
    expected = f"hydra-core<{major}.{minor + 1}.0.dev0,>={major}.{minor}.0.dev1"
    requirements = [
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if requirement.lower().startswith("hydra-core")
    ]
    assert requirements == [expected]
