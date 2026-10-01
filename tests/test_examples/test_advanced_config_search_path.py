# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import re
from pathlib import Path

from omegaconf import OmegaConf
from pytest import mark

from hydra.test_utils.test_utils import (
    chdir_hydra_root,
    run_python_script,
    run_with_error,
)

chdir_hydra_root()


@mark.parametrize(
    "args,expected, error",
    [
        ([], {"dataset": {"name": "cifar10", "path": "/datasets/cifar10"}}, None),
        (
            ["dataset=imagenet"],
            {"dataset": {"name": "imagenet", "path": "/datasets/imagenet"}},
            None,
        ),
        (
            ["hydra.searchpath=[]", "dataset=imagenet"],
            {"dataset": {"name": "imagenet", "path": "/datasets/imagenet"}},
            "Could not find 'dataset/imagenet'",
        ),
    ],
)
def test_config_search_path(
    args: list[str], expected: str, tmpdir: Path, error: str | None
) -> None:
    cmd = [
        "examples/advanced/config_search_path/my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ]
    cmd.extend(args)
    if error is not None:
        ret = run_with_error(cmd)
        assert re.search(re.escape(error), ret) is not None
    else:
        result, _err = run_python_script(cmd)
        assert OmegaConf.create(result) == expected
