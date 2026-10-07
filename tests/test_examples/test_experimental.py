# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

from pathlib import Path

from hydra.test_utils.test_utils import run_python_script


def test_rerun(tmpdir: Path) -> None:
    cmd = [
        "examples/experimental/rerun/my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "hydra.hydra_logging.formatters.simple.format='[HYDRA] %(message)s'",
        "hydra.job_logging.formatters.simple.format='[JOB] %(message)s'",
    ]

    result, _err = run_python_script(cmd)
    assert "[JOB] cfg.foo=bar" in result
    result, _err = run_python_script(
        [cmd[0], "--experimental-rerun", str(tmpdir), "foo=baz"]
    )
    assert "[JOB] cfg.foo=baz" in result
