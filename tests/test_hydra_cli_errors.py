# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from pathlib import Path
from typing import Any

from pytest import mark, param

from hydra.test_utils.test_utils import (
    chdir_hydra_root,
    normalize_newlines,
    run_with_error,
)

chdir_hydra_root()


@mark.parametrize(
    "override,expected_substrings",
    [
        param(
            "+key=int(",
            [
                "Error when parsing index: 1, string: +key=int( out of [",
                "no viable alternative at input 'int('",
            ],
            id="parse_error_in_function",
        ),
        param(
            "+key=sort()",
            [
                """Error when parsing index: 1, string: +key=sort() out of [""",
                """Error parsing override '+key=sort()'
ValueError while evaluating 'sort()': empty sort input""",
            ],
            id="empty_sort",
        ),
        param(
            "key=sort(interval(1,10))",
            [
                """Error when parsing index: 1, string: key=sort(interval(1,10)) out of [""",
                """Error parsing override 'key=sort(interval(1,10))'
TypeError while evaluating 'sort(interval(1,10))': mismatch type argument args[0]""",
            ],
            id="sort_interval",
        ),
        param(
            "+key=choice()",
            [
                """Error when parsing index: 1, string: +key=choice() out of [""",
                """Error parsing override '+key=choice()'
ValueError while evaluating 'choice()': empty choice is not legal""",
            ],
            id="empty choice",
        ),
        param(
            "+key=extend_list(1, 2, 3)",
            [
                """Error when parsing index: 1, string: +key=extend_list(1, 2, 3) out of [""",
                """Error parsing override '+key=extend_list(1, 2, 3)'
Trying to use override symbols when extending a list""",
            ],
            id="plus key extend_list",
        ),
        param(
            "key={inner_key=extend_list(1, 2, 3)}",
            [
                """Error when parsing index: 1, string: key={inner_key=extend_list(1, 2, 3)} out of [""",
                "no viable alternative at input '{inner_key='",
            ],
            id="embedded extend_list",
        ),
        param(
            ["+key=choice(choice(a,b))", "-m"],
            [
                """Error when parsing index: 1, string: +key=choice(choice(a,b)) out of [""",
                """Error parsing override '+key=choice(choice(a,b))'
ValueError while evaluating 'choice(choice(a,b))': nesting choices is not supported
See https://hydra.cc/docs/1.2/advanced/override_grammar/basic for details
""",
            ],
            id="empty choice",
        ),
        param(
            "--config-dir=/dir/not/found",
            [
                f"""Additional config directory '{Path("/dir/not/found").absolute()}' not found
"""
            ],
            id="config_dir_not_found",
        ),
    ],
)
def test_cli_error(
    tmpdir: Any,
    monkeypatch: Any,
    override: Any,
    expected_substrings: list[str],
) -> None:
    monkeypatch.chdir("tests/test_apps/app_without_config/")
    if isinstance(override, str):
        override = [override]
    cmd = ["my_app.py", "hydra.sweep.dir=" + str(tmpdir)] + override
    ret = normalize_newlines(run_with_error(cmd))
    missing_substrings = [s for s in expected_substrings if s.strip() not in ret]
    assert not missing_substrings, (
        f"Result:"
        f"\n---"
        f"\n{ret}"
        f"\n---"
        f"\nDoes not contain the following expected substrings:"
        + "\n---\n".join(f"{s}" for s in missing_substrings)
        + "\n---"
    )
