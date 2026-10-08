# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import re
import sys
from textwrap import dedent
from typing import Any

from pytest import mark, param

from hydra._internal.core_plugins.basic_sweeper import BasicSweeper
from hydra.core.override_parser.overrides_parser import OverridesParser
from hydra.test_utils.test_utils import assert_multiline_regex_search, run_process


@mark.parametrize(
    "args,max_batch_size,expected",
    [
        param(["x=10"], None, [[["x=10"]]], id="simple"),
        param(["x=10,20"], None, [[["x=10"], ["x=20"]]], id="split_1d"),
        param(["x=[10,20]"], None, [[["x=[10,20]"]]], id="not_split_yaml_list"),
        param(
            ["x=[a,b,c],[d,e,f]"],
            None,
            [[["x=[a,b,c]"], ["x=[d,e,f]"]]],
            id="list_of_lists",
        ),
        param(
            ["a=1,2", "b=10,11"],
            None,
            [[["a=1", "b=10"], ["a=1", "b=11"], ["a=2", "b=10"], ["a=2", "b=11"]]],
            id="no_batching",
        ),
        param(
            ["a=1,2", "b=10,11"],
            1,
            [
                [["a=1", "b=10"]],
                [["a=1", "b=11"]],
                [["a=2", "b=10"]],
                [["a=2", "b=11"]],
            ],
            id="batches_of_1",
        ),
        param(
            ["a=1,2", "b=10,11"],
            2,
            [[["a=1", "b=10"], ["a=1", "b=11"]], [["a=2", "b=10"], ["a=2", "b=11"]]],
            id="batches_of_2",
        ),
        param(["a=range(0,3)"], None, [[["a=0"], ["a=1"], ["a=2"]]], id="range"),
        param(["a=range(3)"], None, [[["a=0"], ["a=1"], ["a=2"]]], id="range_no_start"),
        param(
            ["a=int(range(0,5,1.5))"],
            None,
            [[["a=0"], ["a=1"], ["a=3"], ["a=4"]]],
            id="cast_range_values",
        ),
        param(
            ["a=int(range(0,1,0.25))"],
            2,
            [[["a=0"], ["a=0"]], [["a=0"], ["a=0"]]],
            id="cast_range_duplicates",
        ),
        param(
            ["a=float(sort(range(0,1,0.25),reverse=true))"],
            None,
            [[["a=0.75"], ["a=0.5"], ["a=0.25"], ["a=0.0"]]],
            id="cast_sorted_float_range",
        ),
    ],
)
def test_split(
    args: list[str], max_batch_size: int | None, expected: list[list[list[str]]]
) -> None:
    parser = OverridesParser.create()
    ret = BasicSweeper.split_arguments(
        parser.parse_overrides(args), max_batch_size=max_batch_size
    )
    lret = [list(x) for x in ret]
    assert lret == expected


def test_partial_failure(
    tmpdir: Any,
) -> None:
    cmd = [
        sys.executable,
        "-Werror",
        "tests/test_apps/app_can_fail/my_app.py",
        "--multirun",
        "+divisor=1,0",
        f'hydra.run.dir="{str(tmpdir)}"',
        f'hydra.sweep.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "hydra.hydra_logging.formatters.simple.format='[HYDRA] %(message)s'",
    ]
    out, err = run_process(cmd=cmd, print_error=False, raise_exception=False)

    expected_out_regex = re.escape(
        dedent("""
            [HYDRA] Launching 2 jobs locally
            [HYDRA] \t#0 : +divisor=1
            val=1.0
            [HYDRA] \t#1 : +divisor=0
            """).strip()
    )

    assert_multiline_regex_search(expected_out_regex, out)
    assert "Job failed" not in out

    expected_err_regex = dedent(r"""
        Error executing job with overrides: \['\+divisor=0'\](
        )?
        Traceback \(most recent call last\):
          File ".*my_app\.py", line 9, in my_app
            val = 1 / cfg\.divisor(
                  ~~\^~~~~~~~~~~~~)?
        ZeroDivisionError: division by zero
        """).strip()

    assert_multiline_regex_search(expected_err_regex, err)

    job_log = tmpdir / "1" / "my_app.log"
    log_content = job_log.read()
    assert "Job failed" in log_content
    assert "ZeroDivisionError: division by zero" in log_content


def test_multiple_failures_log_to_own_job_files(
    tmpdir: Any,
) -> None:
    cmd = [
        sys.executable,
        "tests/test_apps/app_can_fail/my_app.py",
        "--multirun",
        "+divisor=0,1,x",
        f'hydra.run.dir="{str(tmpdir)}"',
        f'hydra.sweep.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ]
    run_process(cmd=cmd, print_error=False, raise_exception=False)

    succeeded_log = (tmpdir / "1" / "my_app.log").read()
    assert "Job failed" not in succeeded_log

    zero_division_log = (tmpdir / "0" / "my_app.log").read()
    assert "Job failed" in zero_division_log
    assert "ZeroDivisionError: division by zero" in zero_division_log

    type_error_log = (tmpdir / "2" / "my_app.log").read()
    assert "Job failed" in type_error_log
    assert "TypeError" in type_error_log


def test_glob_uses_primary_config_searchpath(tmpdir: Any) -> None:
    cmd = [
        sys.executable,
        "tests/test_apps/glob_searchpath/my_app.py",
        "+group1@=glob(file*)",
        f"hydra.sweep.dir={tmpdir}",
        "hydra.job.chdir=False",
        "--multirun",
    ]
    out, err = run_process(cmd=cmd, print_error=False, raise_exception=False)

    assert err == ""
    assert "Launching 2 jobs locally" in out
    assert "foo=10" in out
    assert "foo=20" in out
