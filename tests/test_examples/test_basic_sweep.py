# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from pathlib import Path
from textwrap import dedent

from pytest import mark

from hydra.test_utils.test_utils import (
    assert_text_same,
    chdir_hydra_root,
    run_python_script,
)

chdir_hydra_root()


@mark.parametrize(
    "args,expected",
    [
        (
            [],
            dedent("""\
                [HYDRA] Launching 4 jobs locally
                [HYDRA] \t#0 : db=mysql db.timeout=5
                driver=mysql, timeout=5
                [HYDRA] \t#1 : db=mysql db.timeout=10
                driver=mysql, timeout=10
                [HYDRA] \t#2 : db=postgresql db.timeout=5
                driver=postgresql, timeout=5
                [HYDRA] \t#3 : db=postgresql db.timeout=10
                driver=postgresql, timeout=10"""),
        ),
        (
            ["db=glob([m*],exclude=postgresql)"],
            dedent("""\
                [HYDRA] Launching 2 jobs locally
                [HYDRA] \t#0 : db=mysql db.timeout=5
                driver=mysql, timeout=5
                [HYDRA] \t#1 : db=mysql db.timeout=10
                driver=mysql, timeout=10"""),
        ),
        (
            ["db=mysql", "db.user=choice(one,two)"],
            dedent("""\
                [HYDRA] Launching 4 jobs locally
                [HYDRA] \t#0 : db=mysql db.timeout=5 db.user=one
                driver=mysql, timeout=5
                [HYDRA] \t#1 : db=mysql db.timeout=5 db.user=two
                driver=mysql, timeout=5
                [HYDRA] \t#2 : db=mysql db.timeout=10 db.user=one
                driver=mysql, timeout=10
                [HYDRA] \t#3 : db=mysql db.timeout=10 db.user=two
                driver=mysql, timeout=10"""),
        ),
    ],
)
def test_basic_sweep_example(
    tmpdir: Path,
    args: list[str],
    expected: str,
) -> None:
    app_path = "examples/tutorials/basic/running_your_hydra_app/5_basic_sweep/my_app.py"

    cmd = [
        app_path,
        "--multirun",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "hydra.hydra_logging.formatters.simple.format='[HYDRA] %(message)s'",
        "hydra.job_logging.formatters.simple.format='[JOB] %(message)s'",
    ]
    cmd.extend(args)
    result, _err = run_python_script(cmd)

    assert_text_same(
        from_line=expected,
        to_line=result,
        from_name="Expected output",
        to_name="Actual output",
    )
