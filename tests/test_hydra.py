# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import os
import re
import subprocess
import sys
import warnings
from logging import getLogger
from pathlib import Path
from textwrap import dedent
from typing import Any, List, Optional, Set

from omegaconf import DictConfig, OmegaConf
from pytest import mark, param, raises, warns

from hydra import MissingConfigException, __version__, main, version
from hydra.core.hydra_config import HydraConfig
from hydra.errors import (
    ConfigCompositionException,
    Hydra14MigrationWarning,
    Hydra15MigrationWarning,
    HydraException,
)
from hydra.experimental.callback import Callback
from hydra.test_utils.test_utils import (
    TSweepRunner,
    TTaskRunner,
    assert_multiline_regex_search,
    assert_regex_match,
    assert_text_same,
    chdir_hydra_root,
    integration_test,
    normalize_newlines,
    run_python_script,
    run_with_error,
    verify_dir_outputs,
)
from hydra.utils import execution_whitelist
from tests.test_apps.app_instantiate_exception.my_app import InstantiationCase

chdir_hydra_root()

HIDDEN_HYDRA_FRAME = (
    f'File "{os.path.join(os.devnull, "Hydra frames hidden")}", line 1, in omitted'
)


def test_migration_warning_categories_are_release_specific() -> None:
    assert issubclass(Hydra14MigrationWarning, UserWarning)
    assert issubclass(Hydra15MigrationWarning, UserWarning)
    assert not issubclass(Hydra15MigrationWarning, Hydra14MigrationWarning)


@mark.parametrize("version_base", ["1.0", "1.1", "1.2"])
def test_hydra_main_old_version_base(
    hydra_restore_singletons: Any, version_base: str
) -> None:
    with raises(
        HydraException,
        match=(
            f"version_base={version_base!r} is not supported in Hydra 1.4; "
            "omit version_base to use the current behavior"
        ),
    ):
        main(version_base=version_base)


def test_hydra_main_omitted_version_base(hydra_restore_singletons: Any) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        main()
    assert version.getbase() == version._get_version(__version__)


@mark.parametrize("version_base", [None, "1.3", "1.4"])
def test_hydra_main_explicit_version_base_is_deprecated(
    hydra_restore_singletons: Any, version_base: Optional[str]
) -> None:
    with warns(
        Hydra15MigrationWarning,
        match="The version_base parameter is deprecated and will be removed in Hydra 1.5",
    ):
        main(version_base=version_base)
    expected = __version__ if version_base is None else version_base
    assert version.getbase() == version._get_version(expected)


@mark.parametrize("calling_file, calling_module", [(".", None), (None, ".")])
def test_missing_conf_dir(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    with raises(MissingConfigException):
        with hydra_task_runner(
            calling_file=calling_file,
            calling_module=calling_module,
            config_path="dir_not_found",
            config_name=None,
        ):
            pass


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/app_without_config/my_app.py", None),
        (None, "tests.test_apps.app_without_config.my_app"),
    ],
)
def test_missing_conf_file(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    with raises(MissingConfigException):
        with hydra_task_runner(
            calling_file=calling_file,
            calling_module=calling_module,
            config_path=None,
            config_name="not_found.yaml",
        ):
            pass


def test_run_dir() -> None:
    run_python_script(
        ["tests/test_apps/run_dir_test/my_app.py", "hydra.job.chdir=True"]
    )


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/app_without_config/my_app.py", None),
        (None, "tests.test_apps.app_without_config.my_app"),
    ],
)
def test_app_without_config___no_overrides(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    with hydra_task_runner(
        calling_file=calling_file,
        calling_module=calling_module,
        config_path=None,
        config_name=None,
    ) as task:
        assert task.job_ret is not None
        assert task.job_ret.cfg == {}


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/hydra_main_rerun/my_app.py", None),
        (None, "tests.test_apps.hydra_main_rerun.my_app"),
    ],
)
def test_hydra_main_rerun(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    with hydra_task_runner(
        calling_file=calling_file,
        calling_module=calling_module,
        config_path=None,
        config_name=None,
    ) as task:
        assert task.job_ret is not None
        assert task.job_ret.cfg == {}


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/app_without_config/my_app.py", None),
        (None, "tests.test_apps.app_without_config.my_app"),
    ],
)
def test_app_without_config__with_append(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    with hydra_task_runner(
        calling_file=calling_file,
        calling_module=calling_module,
        config_path="",
        config_name=None,
        overrides=["+abc=123", "+a.b=1", "+a.a=2"],
        configure_logging=True,
    ) as task:
        assert task.job_ret is not None and task.job_ret.cfg == dict(
            abc=123, a=dict(b=1, a=2)
        )
        verify_dir_outputs(task.job_ret, task.overrides)


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/app_with_cfg/my_app.py", None),
        (None, "tests.test_apps.app_with_cfg.my_app"),
    ],
)
def test_app_with_config_file__no_overrides(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    task = hydra_task_runner(
        calling_file=calling_file,
        calling_module=calling_module,
        config_path=".",
        config_name="config.yaml",
        configure_logging=True,
    )
    with task:
        assert task.job_ret is not None and task.job_ret.cfg == {
            "dataset": {"name": "imagenet", "path": "/datasets/imagenet"}
        }

        verify_dir_outputs(task.job_ret)


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/app_with_cfg_groups/my_app.py", None),
        (None, "tests.test_apps.app_with_cfg_groups.my_app"),
    ],
)
def test_app_with_config_path_backward_compatibility(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    msg = dedent("""\
    Using config_path to specify the config name is not supported, specify the config name via config_name.
    See https://hydra.cc/docs/1.2/upgrades/0.11_to_1.0/config_path_changes
    """)

    # This more is no longer supported in Hydra 1.1
    with raises(ValueError, match=re.escape(msg)):
        task = hydra_task_runner(
            calling_file=calling_file,
            calling_module=calling_module,
            config_path="conf/config.yaml",
            config_name=None,
            configure_logging=True,
        )
        with task:
            assert False  # will never get here.


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/app_with_cfg/my_app.py", None),
        (None, "tests.test_apps.app_with_cfg.my_app"),
    ],
)
def test_app_with_config_file__with_override(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    with hydra_task_runner(
        calling_file=calling_file,
        calling_module=calling_module,
        config_path=".",
        config_name="config.yaml",
        overrides=["dataset.path=/datasets/imagenet2"],
        configure_logging=True,
    ) as task:
        assert task.job_ret is not None and task.job_ret.cfg == dict(
            dataset=dict(name="imagenet", path="/datasets/imagenet2")
        )
        verify_dir_outputs(task.job_ret, task.overrides)


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/app_with_cfg_decorated/my_app.py", None),
        (None, "tests.test_apps.app_with_cfg_decorated.my_app"),
    ],
)
def test_app_with_config_file__with_decorators(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    with hydra_task_runner(
        calling_file=calling_file,
        calling_module=calling_module,
        config_path=".",
        config_name="config.yaml",
        configure_logging=True,
    ) as task:
        assert task.job_ret is not None and task.job_ret.cfg == dict(
            dataset=dict(name="imagenet", path="/datasets/imagenet")
        )
        verify_dir_outputs(task.job_ret)


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/app_with_split_cfg/my_app.py", None),
        (None, "tests.test_apps.app_with_split_cfg.my_app"),
    ],
)
def test_app_with_split_config(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    with hydra_task_runner(
        calling_file=calling_file,
        calling_module=calling_module,
        config_path=".",
        config_name="config.yaml",
        configure_logging=True,
    ) as task:
        assert task.job_ret is not None and task.job_ret.cfg == dict(
            dataset=dict(name="imagenet", path="/datasets/imagenet"),
            optimizer=dict(lr=0.001, type="nesterov"),
        )
        verify_dir_outputs(task.job_ret)


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/app_with_cfg_groups/my_app.py", None),
        (None, "tests.test_apps.app_with_cfg_groups.my_app"),
    ],
)
def test_app_with_config_groups__override_dataset__wrong(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    with raises(MissingConfigException) as ex:
        with hydra_task_runner(
            calling_file=calling_file,
            calling_module=calling_module,
            config_path="conf",
            config_name=None,
            overrides=["+optimizer=wrong_name"],
        ):
            pass
    assert sorted(ex.value.options) == sorted(["adam", "nesterov"])  # type: ignore


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/app_with_cfg_groups/my_app.py", None),
        (None, "tests.test_apps.app_with_cfg_groups.my_app"),
    ],
)
def test_app_with_config_groups__override_all_configs(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    with hydra_task_runner(
        calling_file=calling_file,
        calling_module=calling_module,
        config_path="conf",
        config_name=None,
        overrides=["+optimizer=adam", "optimizer.lr=10"],
        configure_logging=True,
    ) as task:
        assert task.job_ret is not None and task.job_ret.cfg == dict(
            optimizer=dict(type="adam", lr=10, beta=0.01)
        )
        verify_dir_outputs(task.job_ret, overrides=task.overrides)


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/app_with_custom_launcher/my_app.py", None),
        (None, "tests.test_apps.app_with_custom_launcher.my_app"),
    ],
)
def test_app_with_sweep_cfg__override_to_basic_launcher(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    with hydra_task_runner(
        calling_file=calling_file,
        calling_module=calling_module,
        config_path=".",
        config_name="config.yaml",
        overrides=["hydra/launcher=basic"],
    ) as task:
        assert task.job_ret is not None
        assert task.job_ret.hydra_cfg is not None
        hydra_cfg = task.job_ret.hydra_cfg
        assert (
            hydra_cfg.hydra.launcher._target_
            == "hydra._internal.core_plugins.basic_launcher.BasicLauncher"
        )
        assert len(task.job_ret.hydra_cfg.hydra.launcher) == 1


def test_short_module_name(tmpdir: Path) -> None:
    cmd = [
        "examples/tutorials/basic/your_first_hydra_app/2_config_file/my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ]
    out, _err = run_python_script(cmd)
    assert OmegaConf.create(out) == {
        "db": {"driver": "mysql", "password": "secret", "user": "omry"}
    }


def test_hydra_main_module_override_name(tmpdir: Path) -> None:
    cfg = OmegaConf.create()
    integration_test(
        tmpdir=tmpdir,
        task_config=cfg,
        overrides=[],
        prints="HydraConfig.get().job.name",
        expected_outputs="Foo",
        env_override={"HYDRA_MAIN_MODULE": "hydra.test_utils.configs.Foo"},
    )


@mark.parametrize(
    "env_name", ["HYDRA_MAIN_MODULE", "FB_PAR_MAIN_MODULE", "FB_XAR_MAIN_MODULE"]
)
def test_module_env_override(tmpdir: Path, env_name: str) -> None:
    """
    Tests that module name overrides are working.
    """
    cmd = [
        "examples/tutorials/basic/your_first_hydra_app/2_config_file/my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ]
    modified_env = os.environ.copy()
    modified_env[env_name] = "hydra.test_utils.configs.Foo"
    result, _err = run_python_script(cmd, env=modified_env)
    assert OmegaConf.create(result) == {"normal_yaml_config": True}


@mark.parametrize("resolve", [True, False])
@mark.parametrize(
    "flag,expected_keys",
    [("--cfg=all", ["db", "hydra"]), ("--cfg=hydra", ["hydra"]), ("--cfg=job", ["db"])],
)
def test_cfg(tmpdir: Path, flag: str, resolve: bool, expected_keys: List[str]) -> None:
    cmd = [
        "examples/tutorials/basic/your_first_hydra_app/5_defaults/my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        flag,
    ]
    if resolve:
        cmd.append("--resolve")
    result, _err = run_python_script(cmd)
    conf = OmegaConf.create(result)
    for key in expected_keys:
        assert key in conf


@mark.parametrize("resolve", [True, False])
@mark.parametrize(
    "flags,expected",
    [
        param(
            ["--cfg=job"],
            dedent("""\
                db:
                  driver: mysql
                  user: omry
                  pass: secret
                """),
            id="no-package",
        ),
        param(
            ["--cfg=job", "--package=_global_"],
            dedent("""\
                db:
                  driver: mysql
                  user: omry
                  pass: secret
                """),
            id="package=_global_",
        ),
        param(
            ["--cfg=job", "--package=db"],
            dedent("""\
                # @package db
                driver: mysql
                user: omry
                pass: secret
                """),
            id="package=db",
        ),
        param(["--cfg=job", "--package=db.driver"], "mysql\n", id="package=db.driver"),
    ],
)
def test_cfg_with_package(
    tmpdir: Path, flags: List[str], resolve: bool, expected: str
) -> None:
    cmd = [
        "examples/tutorials/basic/your_first_hydra_app/5_defaults/my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ] + flags
    if resolve:
        cmd.append("--resolve")

    result, _err = run_python_script(cmd)
    assert normalize_newlines(result) == expected.rstrip()


@mark.parametrize(
    "script,resolve,flags,expected",
    [
        param(
            "tests/test_apps/simple_interpolation/my_app.py",
            False,
            [],
            dedent("""\
                a: ${b}
                b: 10
                """),
            id="cfg",
        ),
        param(
            "tests/test_apps/simple_interpolation/my_app.py",
            True,
            [],
            dedent("""\
                a: 10
                b: 10
                """),
            id="resolve",
        ),
        param(
            "tests/test_apps/simple_app/my_app.py",
            True,
            [
                "--config-name=interp_to_hydra",
                "--config-dir=tests/test_apps/simple_app",
            ],
            dedent("""\
                a: my_app
                """),
            id="resolve_hydra_config",
        ),
    ],
)
def test_cfg_resolve_interpolation(
    tmpdir: Path, script: str, resolve: bool, flags: List[str], expected: str
) -> None:
    cmd = [
        script,
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "--cfg=job",
    ] + flags
    if resolve:
        cmd.append("--resolve")

    result, _err = run_python_script(cmd)
    assert_text_same(result, expected)


@mark.parametrize(
    "script,expected",
    [
        param(
            "tests/test_apps/passes_callable_class_to_hydra_main/my_app.py",
            dedent("""\
                123
                my_app
                """),
            id="passes_callable_class_to_hydra_main",
        ),
        param(
            "tests/test_apps/passes_callable_class_to_hydra_main/partial_app.py",
            "123\n",
            id="passes_partial_callable_to_hydra_main",
        ),
    ],
)
def test_pass_callable_class_to_hydra_main(
    tmpdir: Path, script: str, expected: str
) -> None:
    cmd = [
        script,
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ]

    result, _err = run_python_script(cmd)
    assert_text_same(result, expected)


@mark.parametrize("script", ["my_app.py", "partial_app.py"])
def test_callable_class_setup_error_precedes_application(
    tmp_path: Path, script: str
) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("")
    ret = run_with_error(
        [
            f"tests/test_apps/passes_callable_class_to_hydra_main/{script}",
            f'hydra.run.dir="{blocked / "child"}"',
        ]
    )

    assert "in _run_job" in ret
    assert "in mkdir" in ret
    assert "in __call__" not in ret
    assert "Hydra frames hidden" not in ret


@mark.parametrize(
    "other_flag",
    [None, "--run", "--multirun", "--info", "--shell-completion", "--hydra-help"],
)
def test_resolve_flag_errmsg(tmpdir: Path, other_flag: Optional[str]) -> None:
    cmd = [
        "examples/tutorials/basic/your_first_hydra_app/3_using_config/my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "--resolve",
    ]
    if other_flag is not None:
        cmd.append(other_flag)

    err = run_with_error(cmd)
    assert normalize_newlines(err).endswith(
        "ValueError: The --resolve flag can only be used in conjunction with --cfg or --help"
    )


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/app_with_config_with_free_group/my_app.py", None),
        (None, "tests.test_apps.app_with_config_with_free_group.my_app"),
    ],
)
@mark.parametrize("overrides", [["+free_group=opt1,opt2"]])
def test_multirun_with_free_override(
    hydra_restore_singletons: Any,
    hydra_sweep_runner: TSweepRunner,
    calling_file: str,
    calling_module: str,
    overrides: List[str],
) -> None:
    sweep = hydra_sweep_runner(
        calling_file=calling_file,
        calling_module=calling_module,
        config_path="conf/",
        config_name="config.yaml",
        task_function=None,
        overrides=overrides,
    )
    with sweep:
        assert sweep.returns is not None and len(sweep.returns[0]) == 2
        assert sweep.returns[0][0].overrides == ["+free_group=opt1"]
        assert sweep.returns[0][0].cfg == {"group_opt1": True, "free_group_opt1": True}
        assert sweep.returns[0][1].overrides == ["+free_group=opt2"]
        assert sweep.returns[0][1].cfg == {"group_opt1": True, "free_group_opt2": True}


@mark.parametrize(
    "calling_file, calling_module",
    [
        param("tests/test_apps/sweep_complex_defaults/my_app.py", None, id="file_path"),
        param(None, "tests.test_apps.sweep_complex_defaults.my_app", id="pkg_path"),
    ],
)
def test_sweep_complex_defaults(
    hydra_restore_singletons: Any,
    hydra_sweep_runner: TSweepRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    with hydra_sweep_runner(
        calling_file=calling_file,
        calling_module=calling_module,
        config_path="conf",
        config_name="config.yaml",
        task_function=None,
        overrides=["optimizer=adam,nesterov"],
    ) as sweep:
        assert sweep.returns is not None and len(sweep.returns[0]) == 2
        assert sweep.returns[0][0].overrides == ["optimizer=adam"]
        assert sweep.returns[0][1].overrides == ["optimizer=nesterov"]


@mark.parametrize(
    "controller,experiment",
    [
        param("hydra/launcher", "custom_launcher", id="launcher"),
        param("hydra/sweeper", "custom_sweeper", id="sweeper"),
    ],
)
def test_multirun_rejects_swept_config_hydra_controller_override(
    hydra_restore_singletons: Any,
    hydra_sweep_runner: TSweepRunner,
    tmpdir: Path,
    controller: str,
    experiment: str,
) -> None:
    with raises(
        ConfigCompositionException,
        match=rf"{re.escape(controller)}.*must be selected before the sweep starts",
    ):
        with hydra_sweep_runner(
            calling_file="tests/test_apps/sweep_hydra_launcher_override/my_app.py",
            calling_module=None,
            config_path="conf",
            config_name="config.yaml",
            task_function=None,
            overrides=[f"experiment=base,{experiment}"],
            temp_dir=tmpdir,
        ):
            pass


@mark.parametrize(
    "controller,experiment",
    [
        param("hydra.launcher", "launcher_config", id="launcher"),
        param("hydra.sweeper", "sweeper_params", id="sweeper"),
    ],
)
def test_multirun_rejects_swept_config_hydra_controller_config_override(
    hydra_restore_singletons: Any,
    hydra_sweep_runner: TSweepRunner,
    tmpdir: Path,
    controller: str,
    experiment: str,
) -> None:
    with raises(
        ConfigCompositionException,
        match=rf"{re.escape(controller)}.*must be configured before the sweep starts",
    ):
        with hydra_sweep_runner(
            calling_file="tests/test_apps/sweep_hydra_launcher_override/my_app.py",
            calling_module=None,
            config_path="conf",
            config_name="config.yaml",
            task_function=None,
            overrides=[f"experiment=base,{experiment}"],
            temp_dir=tmpdir,
        ):
            pass


@mark.parametrize(
    "script, flags, overrides,expected",
    [
        param(
            "examples/tutorials/basic/your_first_hydra_app/1_simple_cli/my_app.py",
            ["--help"],
            ["hydra.help.template=foo"],
            "foo\n",
            id="simple_cli_app",
        ),
        param(
            "examples/tutorials/basic/your_first_hydra_app/2_config_file/my_app.py",
            ["--help"],
            ["hydra.help.template=foo"],
            "foo\n",
            id="overriding_help_template",
        ),
        param(
            "examples/tutorials/basic/your_first_hydra_app/2_config_file/my_app.py",
            ["--help"],
            ["hydra.help.template=$CONFIG", "db.user=root"],
            dedent("""\
                db:
                  driver: mysql
                  user: root
                  password: secret
                """),
            id="overriding_help_template:$CONFIG",
        ),
        param(
            "examples/tutorials/basic/your_first_hydra_app/2_config_file/my_app.py",
            ["--help", "--resolve"],
            ["hydra.help.template=$CONFIG", "db.user=${db.driver}"],
            dedent("""\
                db:
                  driver: mysql
                  user: mysql
                  password: secret
                """),
            id="overriding_help_template:$CONFIG,interp,yes_resolve",
        ),
        param(
            "tests/test_apps/app_with_cfg/my_app.py",
            ["--help", "--resolve"],
            ["hydra.help.template=$CONFIG", "dataset.name=${hydra:job.name}"],
            dedent("""\
                dataset:
                  name: my_app
                  path: /datasets/imagenet
                """),
            id="overriding_help_template:$CONFIG,resolve_interp_to_hydra_config",
        ),
        param(
            "examples/tutorials/basic/your_first_hydra_app/2_config_file/my_app.py",
            ["--help"],
            ["hydra.help.template=$CONFIG", "db.user=${db.driver}"],
            dedent("""\
                db:
                  driver: mysql
                  user: ${{db.driver}}
                  password: secret
                """),
            id="overriding_help_template:$CONFIG,interp,no_resolve",
        ),
        param(
            "examples/tutorials/basic/your_first_hydra_app/2_config_file/my_app.py",
            ["--help"],
            ["hydra.help.template=$FLAGS_HELP"],
            dedent("""\
                --help,-h : Application's help
                --hydra-help : Hydra's help
                --version : Show Hydra's version and exit
                --cfg,-c : Show config instead of running [job|hydra|all]
                --resolve : Used in conjunction with --cfg, resolve config interpolations before printing.
                --package,-p : Config package to show
                --run,-r : Run a job
                --multirun,-m : Run multiple jobs with the configured launcher and sweeper
                --shell-completion,-sc : Install or Uninstall shell completion:
                    Bash - Install:
                    eval "$(python {script} -sc install=bash)"
                    Bash - Uninstall:
                    eval "$(python {script} -sc uninstall=bash)"

                    Fish - Install:
                    python {script} -sc install=fish | source
                    Fish - Uninstall:
                    python {script} -sc uninstall=fish | source

                    Zsh - Install:
                    Zsh is compatible with the Bash shell completion, see the [documentation]\
(https://hydra.cc/docs/1.2/tutorials/basic/running_your_app/tab_completion#zsh-instructions) \
for details.
                    eval "$(python {script} -sc install=bash)"
                    Zsh - Uninstall:
                    eval "$(python {script} -sc uninstall=bash)"

                --config-path,-cp : Overrides the config_path specified in hydra.main().
                                    The config_path is absolute or relative to the Python file declaring @hydra.main()
                --config-name,-cn : Overrides the config_name specified in hydra.main()
                --config-dir,-cd : Adds an additional config dir to the config search path
                --experimental-rerun : Rerun a job from a previous config pickle
                --info,-i : Print Hydra information [all|config|defaults|defaults-tree|plugins|searchpath]
                Overrides : Any key=value arguments to override config values (use dots for.nested=overrides)
                """),
            id="overriding_help_template:$FLAGS_HELP",
        ),
        param(
            "examples/tutorials/basic/your_first_hydra_app/4_config_groups/my_app.py",
            ["--help"],
            ["hydra.help.template=$APP_CONFIG_GROUPS"],
            "db: mysql, postgresql",
            id="overriding_help_template:$APP_CONFIG_GROUPS",
        ),
        param(
            "examples/tutorials/basic/your_first_hydra_app/2_config_file/my_app.py",
            ["--hydra-help"],
            ["hydra.hydra_help.template=foo"],
            "foo\n",
            id="overriding_hydra_help_template",
        ),
        param(
            "examples/tutorials/basic/your_first_hydra_app/2_config_file/my_app.py",
            ["--hydra-help"],
            ["hydra.hydra_help.template=$FLAGS_HELP"],
            dedent("""\
                --help,-h : Application's help
                --hydra-help : Hydra's help
                --version : Show Hydra's version and exit
                --cfg,-c : Show config instead of running [job|hydra|all]
                --resolve : Used in conjunction with --cfg, resolve config interpolations before printing.
                --package,-p : Config package to show
                --run,-r : Run a job
                --multirun,-m : Run multiple jobs with the configured launcher and sweeper
                --shell-completion,-sc : Install or Uninstall shell completion:
                    Bash - Install:
                    eval "$(python {script} -sc install=bash)"
                    Bash - Uninstall:
                    eval "$(python {script} -sc uninstall=bash)"

                    Fish - Install:
                    python {script} -sc install=fish | source
                    Fish - Uninstall:
                    python {script} -sc uninstall=fish | source

                    Zsh - Install:
                    Zsh is compatible with the Bash shell completion, see the [documentation]\
(https://hydra.cc/docs/1.2/tutorials/basic/running_your_app/tab_completion#zsh-instructions) \
for details.
                    eval "$(python {script} -sc install=bash)"
                    Zsh - Uninstall:
                    eval "$(python {script} -sc uninstall=bash)"

                --config-path,-cp : Overrides the config_path specified in hydra.main().
                                    The config_path is absolute or relative to the Python file declaring @hydra.main()
                --config-name,-cn : Overrides the config_name specified in hydra.main()
                --config-dir,-cd : Adds an additional config dir to the config search path
                --experimental-rerun : Rerun a job from a previous config pickle
                --info,-i : Print Hydra information [all|config|defaults|defaults-tree|plugins|searchpath]
                Overrides : Any key=value arguments to override config values (use dots for.nested=overrides)
                """),
            id="overriding_hydra_help_template:$FLAGS_HELP",
        ),
    ],
)
def test_help(
    tmpdir: Path, script: str, flags: List[str], overrides: List[str], expected: Any
) -> None:
    cmd = [script, f'hydra.run.dir="{str(tmpdir)}"', "hydra.job.chdir=True"]
    cmd.extend(overrides)
    cmd.extend(flags)
    result, _err = run_python_script(cmd)
    assert_text_same(result, expected.format(script=script))


def test_shell_completion_help(tmpdir: Path) -> None:
    """Test that --shell-completion --help works (regression test for Python 3.14+ argparse)."""
    # This test ensures that the LazyCompletionHelp workaround in utils.py works correctly
    # In Python 3.14+, argparse validates that help is a string, but we use a lazy callable
    # The workaround temporarily disables _check_help validation
    cmd = [
        "examples/tutorials/basic/your_first_hydra_app/1_simple_cli/my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        "--shell-completion",
        "--help",
    ]
    result, _err = run_python_script(cmd)
    # When both flags are present, --help takes precedence and shows help text
    assert "powered by hydra" in result.lower()
    assert not _err


@mark.parametrize(
    "overrides,expected",
    [
        param(
            ["--info", "searchpath", "hydra.searchpath=['pkg://additional_conf']"],
            r".*hydra.searchpath in command-line\s+|\s+pkg://additional_conf.*",
            id="searchpath config from command-line",
        ),
        param(
            ["--info", "searchpath"],
            r".*hydra.searchpath in main\s+|\s+pkg://additional_conf.*",
            id="print info with searchpath config",
        ),
        param(
            ["--info", "all", "dataset=imagenet"],
            r".*path:\s+/datasets/imagenet",
            id="searchpath config from config file",
        ),
    ],
)
def test_searchpath_config(tmpdir: Path, overrides: List[str], expected: str) -> None:
    cmd = ["examples/advanced/config_search_path/my_app.py"]
    cmd.extend(overrides)
    cmd.extend([f'hydra.run.dir="{str(tmpdir)}"', "hydra.job.chdir=True"])
    result, _err = run_python_script(cmd)
    assert re.match(expected, result, re.DOTALL)


@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/interpolating_dir_hydra_to_app/my_app.py", None),
        (None, "tests.test_apps.interpolating_dir_hydra_to_app.my_app"),
    ],
)
def test_interpolating_dir_hydra_to_app(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
) -> None:
    basedir = "foo"
    with hydra_task_runner(
        calling_file=calling_file,
        calling_module=calling_module,
        config_path=".",
        config_name="config.yaml",
        overrides=["experiment.base_dir=" + basedir],
    ) as task:
        assert task.temp_dir is not None
        path = Path(task.temp_dir) / basedir
        assert path.exists()


def test_sys_exit(tmpdir: Path) -> None:
    cmd = [
        sys.executable,
        "-Werror",
        "tests/test_apps/sys_exit/my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ]
    assert subprocess.run(cmd).returncode == 42


@mark.parametrize(
    "task_config, overrides, expected_dir",
    [
        ({"hydra": {"run": {"dir": "foo"}}}, ["hydra.job.chdir=True"], "foo"),
        ({}, ["hydra.run.dir=bar", "hydra.job.chdir=True"], "bar"),
        (
            {"hydra": {"run": {"dir": "foo"}}},
            ["hydra.run.dir=boom", "hydra.job.chdir=True"],
            "boom",
        ),
        (
            {
                "hydra": {"run": {"dir": "foo-${hydra_override_dirname:}"}},
                "app": {"a": 1, "b": 2},
            },
            ["app.a=20", "hydra.job.chdir=True"],
            "foo-app.a=20",
        ),
        (
            {
                "hydra": {"run": {"dir": "foo-${hydra_override_dirname:}"}},
                "app": {"a": 1, "b": 2},
            },
            ["app.b=10", "app.a=20", "hydra.job.chdir=True"],
            "foo-app.a=20,app.b=10",
        ),
    ],
)
def test_local_run_workdir(
    tmpdir: Path, task_config: DictConfig, overrides: List[str], expected_dir: str
) -> None:
    cfg = OmegaConf.create(task_config)
    assert isinstance(cfg, DictConfig)
    expected_dir1 = tmpdir / expected_dir
    integration_test(
        tmpdir=tmpdir,
        task_config=cfg,
        overrides=overrides,
        prints="os.getcwd()",
        expected_outputs=str(expected_dir1),
    )


def test_hydra_job_override_dirname_in_run_dir(tmpdir: Path) -> None:
    tmp_path = Path(str(tmpdir))
    cfg = OmegaConf.create(
        {
            "hydra": {
                "run": {
                    "dir": f"{tmp_path}/foo-${{hydra.job.override_dirname}}",
                }
            },
            "app": {"a": 1},
        }
    )
    OmegaConf.save(cfg, tmp_path / "config.yaml")
    task_file = tmp_path / "task.py"
    task_file.write_text(
        dedent("""
            import os

            import hydra


            @hydra.main(config_path=".", config_name="config")
            def experiment(_cfg):
                print(os.getcwd())


            if __name__ == "__main__":
                experiment()
            """),
        encoding="utf-8",
    )

    out, _err = run_python_script([str(task_file), "app.a=20", "hydra.job.chdir=True"])

    assert out == str(tmp_path / "foo-app.a=20")


@mark.parametrize(
    "task_config",
    [
        ({"hydra": {"run": {"dir": "${now:%Y%m%d_%H%M%S_%f}"}}}),
    ],
)
def test_run_dir_microseconds(tmpdir: Path, task_config: DictConfig) -> None:
    cfg = OmegaConf.create(task_config)
    assert isinstance(cfg, DictConfig)
    integration_test(
        tmpdir=tmpdir,
        task_config=cfg,
        overrides=[],
        prints="str('%f' not in os.getcwd())",
        expected_outputs="True",
    )


def test_hydra_env_set_with_config(tmpdir: Path) -> None:
    cfg = OmegaConf.create({"hydra": {"job": {"env_set": {"foo": "bar"}}}})
    integration_test(
        tmpdir=tmpdir,
        task_config=cfg,
        overrides=[],
        prints="os.environ['foo']",
        expected_outputs="bar",
    )


def test_hydra_env_set_with_config_interpolation(tmpdir: Path) -> None:
    cfg = OmegaConf.create(
        {"foo": "bar", "hydra": {"job": {"env_set": {"foo": "${foo}"}}}}
    )
    integration_test(
        tmpdir=tmpdir,
        task_config=cfg,
        overrides=[],
        prints="os.environ['foo']",
        expected_outputs="bar",
    )


def test_hydra_env_set_with_override(tmpdir: Path) -> None:
    integration_test(
        tmpdir=tmpdir,
        task_config={},
        overrides=["+hydra.job.env_set.foo=bar"],
        prints="os.environ['foo']",
        expected_outputs="bar",
    )


@mark.parametrize(
    "override",
    [
        param("xyz", id="db=xyz"),
        param("", id="db="),
    ],
)
@mark.parametrize(
    "calling_file, calling_module",
    [
        param("hydra/test_utils/example_app.py", None, id="file"),
        param(None, "hydra.test_utils.example_app", id="module"),
    ],
)
def test_override_with_invalid_group_choice(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: Optional[str],
    calling_module: Optional[str],
    override: str,
) -> None:
    msg = dedent(f"""\
    In 'db_conf': Could not find 'db/{override}'

    Available options in 'db':
    \tmysql
    \tpostgresql
    """)

    with raises(MissingConfigException) as e:
        with hydra_task_runner(
            calling_file=calling_file,
            calling_module=calling_module,
            config_path="configs",
            config_name="db_conf",
            overrides=[f"db={override}"],
        ):
            pass

    # assert_text_same(from_line=msg, to_line=str(e.value))
    assert re.search(msg, str(e.value)) is not None


@mark.parametrize(
    "config_path",
    [
        "dir1",
        "dir2",
        os.path.abspath("tests/test_apps/app_with_multiple_config_dirs/dir2"),
    ],
)
@mark.parametrize("config_name", ["cfg1", "cfg2"])
def test_config_name_and_path_overrides(
    tmpdir: Path, config_path: str, config_name: str
) -> None:
    cmd = [
        "tests/test_apps/app_with_multiple_config_dirs/my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
        f"--config-name={config_name}",
        f"--config-path={config_path}",
    ]
    result, _err = run_python_script(cmd)
    # normalize newlines on Windows to make testing easier
    result = result.replace("\r\n", "\n")
    assert result == f"{os.path.basename(config_path)}_{config_name}: true"


@mark.parametrize(
    "overrides, expected_files",
    [
        ([], {".hydra"}),
        (["hydra.output_subdir=foo"], {"foo"}),
        (["hydra.output_subdir=null"], set()),
    ],
)
@mark.parametrize(
    "calling_file, calling_module",
    [
        ("tests/test_apps/app_with_cfg/my_app.py", None),
        (None, "tests.test_apps.app_with_cfg.my_app"),
    ],
)
def test_hydra_output_dir(
    hydra_restore_singletons: Any,
    hydra_task_runner: TTaskRunner,
    calling_file: str,
    calling_module: str,
    overrides: List[str],
    expected_files: Set[str],
) -> None:
    with hydra_task_runner(
        calling_file=calling_file,
        calling_module=calling_module,
        config_path=None,
        config_name=None,
        overrides=overrides,
    ) as task:
        assert task.temp_dir is not None
        path = Path(task.temp_dir)
        files = {str(x)[len(task.temp_dir) + 1 :] for x in path.iterdir()}
        assert files == expected_files


@mark.parametrize(
    "directory,file,module, error",
    [
        (
            "tests/test_apps/run_as_module_1",
            "my_app.py",
            "my_app",
            "Primary config module is empty",
        ),
        ("tests/test_apps/run_as_module_2", "my_app.py", "my_app", None),
        ("tests/test_apps/run_as_module_3", "module/my_app.py", "module.my_app", None),
        ("tests/test_apps/run_as_module_4", "module/my_app.py", "module.my_app", None),
    ],
)
def test_module_run(
    tmpdir: Any, directory: str, file: str, module: str, error: Optional[str]
) -> None:
    cmd = [
        directory + "/" + file,
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ]
    modified_env = os.environ.copy()
    modified_env["PYTHONPATH"] = directory
    modified_env["HYDRA_MAIN_MODULE"] = module
    if error is not None:
        ret = run_with_error(cmd, modified_env)
        assert re.search(re.escape(error), ret) is not None
    else:
        result, _err = run_python_script(cmd, env=modified_env)
        assert OmegaConf.create(result) == {"x": 10}


@mark.parametrize(
    "overrides,error,expected",
    [
        param(["test.param=1"], False, "1", id="run:value"),
        param(
            ["test.param=1,2"],
            True,
            dedent(
                r"""
                Ambiguous value for argument 'test\.param=1,2'
                1\. To use it as a list, use key=\[value1,value2\]
                2\. To use it as string, quote the value: key=\\'value1,value2\\'
                3\. To sweep over it, add --multirun to your command line
                """
            ).strip(),
            id="run:choice_sweep",
        ),
        param(
            ["test.param=[1,2]"],
            True,
            dedent(
                r"""
                Error merging override test.param=\[1,2\]
                Value '\[1, 2\]'( of type 'list')? could not be converted to Integer
                    full_key: test\.param
                    object_type=TestConfig
                """
            ).strip(),
            id="run:list_value",
        ),
        param(["test.param=1", "-m"], False, "1", id="multirun:value"),
        param(["test.param=1,2", "-m"], False, "1\n2", id="multirun:choice_sweep"),
    ],
)
def test_multirun_structured_conflict(
    tmpdir: Any, overrides: List[str], error: bool, expected: Any
) -> None:
    cmd = [
        "tests/test_apps/multirun_structured_conflict/my_app.py",
        "hydra.sweep.dir=" + str(tmpdir),
        "hydra.job.chdir=True",
    ]
    cmd.extend(overrides)
    if error:
        expected = normalize_newlines(expected)
        ret = run_with_error(cmd)
        assert_multiline_regex_search(
            pattern=expected,
            string=ret,
            from_name="Expected output",
            to_name="Actual output",
        )
    else:
        ret, _err = run_python_script(cmd)
        assert ret == expected


@mark.parametrize(
    "cmd_base",
    [["tests/test_apps/simple_app/my_app.py", "hydra/hydra_logging=disabled"]],
)
class TestVariousRuns:
    @mark.parametrize(
        "sweep",
        [
            param(False, id="run"),
            param(True, id="sweep"),
        ],
    )
    def test_run_with_missing_default(
        self, cmd_base: List[str], tmpdir: Any, sweep: bool
    ) -> None:
        cmd = cmd_base + [
            "hydra.sweep.dir=" + str(tmpdir),
            "hydra.job.chdir=True",
            "--config-name=unspecified_mandatory_default",
            "--config-path=../../../hydra/test_utils/configs",
        ]
        if sweep:
            cmd.append("-m")
        expected = """You must specify 'group1', e.g, group1=<OPTION>
Available options:
\tabc.cde
\tfile1
\tfile2"""
        ret = run_with_error(cmd)
        assert re.search(re.escape(expected), ret) is not None

    def test_command_line_interpolations_evaluated_lazily(
        self, cmd_base: List[str], tmpdir: Any
    ) -> None:
        cmd = cmd_base + [
            "hydra.sweep.dir=" + str(tmpdir),
            "hydra.job.chdir=True",
            "+foo=10,20",
            "+bar=${foo}",
            "--multirun",
        ]
        expected = """foo: 10
bar: 10

foo: 20
bar: 20"""
        ret, _err = run_python_script(cmd)
        assert normalize_newlines(ret) == normalize_newlines(expected)

    def test_multirun_config_overrides_evaluated_lazily(
        self, cmd_base: List[str], tmpdir: Any
    ) -> None:
        cmd = cmd_base + [
            "hydra.sweep.dir=" + str(tmpdir),
            "hydra.job.chdir=True",
            "+foo=10,20",
            "+bar=${foo}",
            "--multirun",
        ]
        expected = """foo: 10
bar: 10

foo: 20
bar: 20"""
        ret, _err = run_python_script(cmd)
        assert normalize_newlines(ret) == normalize_newlines(expected)

    def test_multirun_defaults_override(self, cmd_base: List[str], tmpdir: Any) -> None:
        cmd = cmd_base + [
            "hydra.sweep.dir=" + str(tmpdir),
            "hydra.job.chdir=True",
            "group1=file1,file2",
            "--multirun",
            "--config-path=../../../hydra/test_utils/configs",
            "--config-name=compose",
        ]
        expected = """foo: 10
bar: 100

foo: 20
bar: 100"""
        ret, _err = run_python_script(cmd)
        assert normalize_newlines(ret) == normalize_newlines(expected)

    def test_run_pass_list(self, cmd_base: List[str], tmpdir: Any) -> None:
        cmd = cmd_base + [
            "hydra.sweep.dir=" + str(tmpdir),
            "hydra.job.chdir=True",
            "+foo=[1,2,3]",
        ]
        expected = {"foo": [1, 2, 3]}
        ret, _err = run_python_script(cmd)
        assert OmegaConf.create(ret) == OmegaConf.create(expected)


def test_app_with_error_exception_sanitized(tmpdir: Any, monkeypatch: Any) -> None:
    cmd = [
        "tests/test_apps/app_with_runtime_config_error/my_app.py",
        f"hydra.sweep.dir={tmpdir}",
        "hydra.job.chdir=True",
    ]

    # Python 3.12 introduced enhanced error messages that suggest similar attribute
    # names for AttributeError. Unfortunately, it suggests private attributes like
    # '_return_value'
    # Python 3.13+ fixes this by not suggesting private attributes.
    if sys.version_info[:2] == (3, 12):
        suggestion_suffix = r". Did you mean: '_return_value'\?"
    else:
        suggestion_suffix = r""

    traceback_line = r"foo\(cfg\)"

    if sys.version_info >= (3, 13):
        # Python 3.13 changed the traceback format for error indicators
        traceback_line += r"\n    ~~~\^\^+\^+"

    expected_regex = (
        dedent(r"""
        Error executing job with overrides: \[\]
        Traceback \(most recent call last\):
          File ".*my_app\.py", line 13, in my_app
            {traceback_line}
          File ".*my_app\.py", line 8, in foo
            cfg\.foo = "bar"  # does not exist in the config(\n    \^+)?
        """)
        .strip()
        .format(traceback_line=traceback_line)
    )

    ret = run_with_error(cmd)
    assert_multiline_regex_search(expected_regex, ret)
    assert "in __setattr__" in ret
    assert "omegaconf.errors.ConfigAttributeError: Key 'foo' is not in struct" in ret
    assert "full_key: foo" in ret
    assert re.search(r"object_type=dict" + suggestion_suffix, ret)


def test_hydra_to_job_config_interpolation(tmpdir: Any) -> Any:
    cmd = [
        "tests/test_apps/hydra_to_cfg_interpolation/my_app.py",
        "hydra.sweep.dir=" + str(tmpdir),
        "hydra.job.chdir=True",
        "b=${a}",
        "a=foo",
    ]
    expected = "override_a=foo,b=foo"
    result, _err = run_python_script(cmd)
    assert result == expected.strip()


@mark.parametrize(
    "overrides,expected",
    [
        param(
            ["dataset=imagenet"], {"dataset": {"name": "imagenet"}}, id="no_conf_dir"
        ),
        param(
            ["dataset=cifar10", "--config-dir=user-dir"],
            {"dataset": {"name": "cifar10"}},
            id="no_conf_dir",
        ),
    ],
)
def test_config_dir_argument(
    monkeypatch: Any, tmpdir: Path, overrides: List[str], expected: DictConfig
) -> None:
    monkeypatch.chdir("tests/test_apps/user-config-dir")
    cmd = [
        "my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ]
    cmd.extend(overrides)
    result, _err = run_python_script(cmd)
    assert OmegaConf.create(result) == expected


def test_schema_overrides_hydra(monkeypatch: Any, tmpdir: Path) -> None:
    monkeypatch.chdir("tests/test_apps/schema_overrides_hydra")
    cmd = [
        "my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ]
    result, _err = run_python_script(cmd)
    assert result == "job_name: test, name: James Bond, age: 7, group: a"


def test_defaults_pkg_with_dot(monkeypatch: Any, tmpdir: Path) -> None:
    monkeypatch.chdir("tests/test_apps/defaults_pkg_with_dot")
    cmd = [
        "my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ]
    result, _err = run_python_script(cmd)
    assert OmegaConf.create(result) == {
        "dataset": {"test": {"name": "imagenet", "path": "/datasets/imagenet"}}
    }


class TestTaskRunnerLogging:
    def test_1(
        self, hydra_restore_singletons: Any, hydra_task_runner: TTaskRunner
    ) -> None:
        with hydra_task_runner(
            calling_file=None,
            calling_module="tests.test_apps.app_without_config.my_app",
            config_path=None,
            config_name=None,
        ):
            logger = getLogger(__name__)
            logger.info("test_1")

    def test_2(self) -> None:
        logger = getLogger(__name__)
        logger.info("test_2")


@mark.parametrize(
    "expected_regex",
    [
        dedent(r"""
            Error executing job with overrides: \[\]
            Traceback \(most recent call last\):
              File ".*my_app\.py", line 9, in my_app
                1 / 0(
                ~~\^~~)?
            ZeroDivisionError: division by zero
            """).strip()
    ],
)
def test_job_exception(
    tmpdir: Any,
    expected_regex: str,
) -> None:
    ret = run_with_error(
        [
            "tests/test_apps/app_exception/my_app.py",
            f'hydra.run.dir="{tmpdir}"',
            "hydra.job.chdir=True",
        ]
    )
    assert_multiline_regex_search(expected_regex, ret)


def test_job_exception_full_error(tmpdir: Any) -> None:
    ret = run_with_error(
        [
            "tests/test_apps/app_exception/my_app.py",
            f'hydra.run.dir="{tmpdir}"',
            "hydra.job.chdir=True",
        ],
        env={**os.environ, "HYDRA_FULL_ERROR": "1"},
    )

    assert "ZeroDivisionError: division by zero" in ret


@mark.parametrize(
    "case",
    [
        InstantiationCase.TARGET,
        InstantiationCase.MISSING,
        InstantiationCase.INVALID,
        InstantiationCase.NESTED,
    ],
)
def test_instantiate_exception_traceback(tmpdir: Any, case: InstantiationCase) -> None:
    ret = run_with_error(
        [
            "tests/test_apps/app_instantiate_exception/my_app.py",
            f"case={case.name}",
            f'hydra.run.dir="{tmpdir}"',
        ]
    )

    assert "in my_app\n    return instantiate(" in ret
    assert "hydra/_internal/instantiate/" not in ret.replace("\\", "/")
    if case is InstantiationCase.TARGET:
        assert ret.count(HIDDEN_HYDRA_FRAME) == 1
        assert (
            ret.index("in my_app")
            < ret.index(HIDDEN_HYDRA_FRAME)
            < ret.index("in __init__")
            < ret.index("in _prepare")
            < ret.index("in _validate")
        )
        assert ret.count("ValueError: target failed") == 1
        assert "InstantiationException" not in ret
        assert "ValueError('target failed')" not in ret
    elif case is InstantiationCase.MISSING:
        assert "Error locating target '__main__.missing'" in ret
        assert "full_key: child" in ret
        assert ret.count("ImportError:") == 1
        assert ret.count("ModuleNotFoundError:") == 1
        assert "ModuleNotFoundError(" not in ret
    elif case is InstantiationCase.NESTED:
        assert "in fail_nested" in ret
        assert ret.count(HIDDEN_HYDRA_FRAME) == 2
        assert (
            ret.index("in my_app")
            < ret.index(HIDDEN_HYDRA_FRAME)
            < ret.index("in fail_nested")
            < ret.rindex(HIDDEN_HYDRA_FRAME)
            < ret.index("in __init__")
            < ret.index("in _prepare")
            < ret.index("in _validate")
        )
        assert ret.count("ValueError: target failed") == 1
        assert "InstantiationException" not in ret
        assert "ValueError('target failed')" not in ret
    else:
        assert ret.count(HIDDEN_HYDRA_FRAME) == 1
        assert "Expected a callable target, got '123' of type 'int'" in ret
        assert "direct cause" not in ret


def test_instantiate_exception_case_rejected_by_composition(tmpdir: Any) -> None:
    ret = run_with_error(
        [
            "tests/test_apps/app_instantiate_exception/my_app.py",
            "case=UNKNOWN",
            f'hydra.run.dir="{tmpdir}"',
        ]
    )

    assert "Error merging override case=UNKNOWN" in ret
    assert "expected one of [TARGET, HOOK, DIRECT" in ret
    assert "object_type=AppConfig" in ret


def test_instantiate_exception_full_error(tmpdir: Any) -> None:
    ret = run_with_error(
        [
            "tests/test_apps/app_instantiate_exception/my_app.py",
            f"case={InstantiationCase.TARGET.name}",
            f'hydra.run.dir="{tmpdir}"',
        ],
        env={**os.environ, "HYDRA_FULL_ERROR": "1"},
    )

    assert "in my_app" in ret
    assert "in __init__" in ret
    assert "in _prepare" in ret
    assert "in _validate" in ret
    assert "hydra/_internal/instantiate/_instantiate2.py" in ret.replace("\\", "/")
    assert "Hydra frames hidden" not in ret
    assert "ValueError: target failed" in ret
    assert "InstantiationException" not in ret


def test_direct_exception_traceback(tmpdir: Any) -> None:
    ret = run_with_error(
        [
            "tests/test_apps/app_instantiate_exception/my_app.py",
            f"case={InstantiationCase.DIRECT.name}",
            f'hydra.run.dir="{tmpdir}"',
        ]
    )

    assert "in my_app\n    return fail()" in ret
    assert 'in fail\n    raise ValueError("direct call failed")' in ret
    assert "Hydra frames hidden" not in ret
    assert ret.count("ValueError: direct call failed") == 1


@mark.parametrize(
    "case", [InstantiationCase.EMBEDDED, InstantiationCase.EMBEDDED_INSTANTIATION]
)
def test_instantiate_exception_preserves_user_message(
    tmpdir: Any, case: InstantiationCase
) -> None:
    ret = run_with_error(
        [
            "tests/test_apps/app_instantiate_exception/my_app.py",
            f"case={case.name}",
            f'hydra.run.dir="{tmpdir}"',
        ]
    )

    error_type = (
        "RuntimeError"
        if case is InstantiationCase.EMBEDDED
        else "InstantiationException"
    )
    assert f"{error_type}: request failed:\nValueError('root cause')" in ret
    assert "The above exception was the direct cause" in ret
    assert "ValueError: root cause" in ret
    assert "hydra/_internal/instantiate/" not in ret.replace("\\", "/")


def test_instantiate_exception_before_run_job(tmpdir: Any) -> None:
    ret = run_with_error(
        [
            "tests/test_apps/app_instantiate_exception/my_app.py",
            "+hydra.callbacks.fail._target_=hydra.experimental.callbacks.LogJobReturnCallback",
            "+hydra.callbacks.fail.unknown=1",
            f'hydra.run.dir="{tmpdir}"',
        ]
    )

    assert "TypeError: LogJobReturnCallback.__init__()" in ret
    assert "full_key: hydra.callbacks.fail" not in ret
    assert "Traceback (most recent call last):" in ret
    assert "in _call_target" in ret
    assert "Hydra frames hidden" not in ret


def test_instantiate_exception_custom_hook(tmpdir: Any) -> None:
    ret = run_with_error(
        [
            "tests/test_apps/app_instantiate_exception/my_app.py",
            f"case={InstantiationCase.HOOK.name}",
            f'hydra.run.dir="{tmpdir}"',
        ]
    )

    assert "hook: ValueError" in ret
    assert "frame: my_app" in ret
    assert "frame: omitted" in ret
    assert "frame: __init__" in ret
    assert "frame: _prepare" in ret
    assert "frame: _validate" in ret
    assert "frame: instantiate" not in ret
    assert "frame: _call_target" not in ret
    assert "cause:" not in ret


def test_structured_with_none_list(monkeypatch: Any, tmpdir: Path) -> None:
    monkeypatch.chdir("tests/test_apps/structured_with_none_list")
    cmd = [
        "my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ]
    result, _err = run_python_script(cmd)
    assert result == "{'list': None}"


def test_self_hydra_config_interpolation_integration(tmpdir: Path) -> None:
    cfg = OmegaConf.create()
    integration_test(
        tmpdir=tmpdir,
        task_config=cfg,
        overrides=[],
        prints="HydraConfig.get().job_logging.handlers.file.filename",
        expected_outputs=r".+task.log$",
    )


def test_job_id_and_num_in_sweep(tmpdir: Path) -> None:
    cfg = OmegaConf.create()
    integration_test(
        tmpdir=tmpdir,
        task_config=cfg,
        overrides=["-m"],
        prints=["HydraConfig.get().job.id", "str(HydraConfig.get().job.num)"],
        expected_outputs=["0", "0"],
    )


def test_hydra_main_without_config_path(tmpdir: Path) -> None:
    cmd = [
        "tests/test_apps/hydra_main_without_config_path/my_app.py",
        f'hydra.run.dir="{tmpdir}"',
        "hydra.job.chdir=True",
    ]
    _, err = run_python_script(cmd)
    assert err == ""


def test_app_with_unicode_config(tmpdir: Path) -> None:
    cmd = [
        "tests/test_apps/app_with_unicode_in_config/my_app.py",
        f'hydra.run.dir="{tmpdir}"',
        "hydra.job.chdir=True",
    ]
    out, _ = run_python_script(cmd)
    assert out == "config: 数据库"


@mark.parametrize(
    "overrides,expected",
    [
        (["--cfg", "job", "-p", "baud_rate"], "19200"),
        (["--cfg", "hydra", "-p", "hydra.job.name"], "frozen"),
        (["--cfg", "job", "--resolve", "-p", "baud_rate"], "19200"),
        (["--cfg", "hydra", "--resolve", "-p", "hydra.job.name"], "frozen"),
        (["--info", "config"], "baud_rate: 19200"),
        (["--hydra-help"], "== Flags =="),
        (["--help"], "frozen is powered by Hydra."),
    ],
)
def test_frozen_primary_config(
    tmpdir: Path, overrides: List[str], expected: str
) -> None:
    cmd = [
        "examples/patterns/write_protect_config_node/frozen.py",
        f'hydra.run.dir="{tmpdir}"',
        "hydra.job.chdir=True",
    ]
    cmd.extend(overrides)
    ret, _err = run_python_script(cmd)
    assert expected in ret


@mark.parametrize(
    "env_deprecation_err,expected",
    [
        param(
            False,
            r"^\S*[/\\]my_app\.py:10: UserWarning: Feature FooBar is deprecated$",
            id="deprecation_warning",
        ),
        param(
            True,
            dedent(r"""
                ^Error executing job with overrides: \[\]\n?
                Traceback \(most recent call last\):
                  File "\S*[/\\]my_app.py", line 10, in my_app
                    deprecation_warning\("Feature FooBar is deprecated"\)(\n    [~\^]+)?
                  File ".*Hydra frames hidden", line 1, in omitted
                hydra\.errors\.HydraDeprecationError: Feature FooBar is deprecated
                """).strip(),
            id="deprecation_error",
        ),
    ],
)
def test_hydra_deprecation_warning(
    env_deprecation_err: bool, expected: str, tmpdir: Path
) -> None:
    cmd = [
        "tests/test_apps/deprecation_warning/my_app.py",
        f'hydra.run.dir="{tmpdir}"',
        "hydra.job.chdir=True",
    ]
    env = os.environ.copy()
    if env_deprecation_err:
        env["HYDRA_DEPRECATION_WARNINGS_AS_ERRORS"] = "1"
    _, err = run_python_script(
        cmd, env=env, allow_warnings=True, print_error=False, raise_exception=False
    )
    assert_multiline_regex_search(expected, err)


@mark.parametrize(
    "multirun,expected",
    [
        (False, ["my_app.log", ".hydra/config.yaml"]),
        (True, ["0/my_app.log", "0/.hydra/config.yaml", "multirun.yaml"]),
    ],
)
def test_disable_chdir(tmpdir: Path, multirun: bool, expected: List[str]) -> None:
    cmd = [
        "examples/tutorials/basic/running_your_hydra_app/3_working_directory/my_app.py",
        f'hydra.run.dir="{tmpdir}"',
        f"hydra.sweep.dir={tmpdir}",
        "hydra.job.chdir=False",
    ]
    if multirun:
        cmd += ["-m"]
    result, _err = run_python_script(cmd)
    assert f"Working directory : {os.getcwd()}" in result
    for p in expected:
        path = os.path.join(str(tmpdir), p)
        assert Path(path).exists()


@mark.parametrize(
    "chdir",
    [True, False],
)
def test_disable_chdir_with_app_chdir(tmpdir: Path, chdir: bool) -> None:
    cmd = [
        "tests/test_apps/app_change_dir/my_app.py",
        f'hydra.run.dir="{tmpdir}"',
        f"hydra.job.chdir={chdir}",
    ]
    result, _err = run_python_script(cmd)
    _path = os.getcwd() if chdir else Path(tmpdir) / "subdir"
    assert f"current dir: {_path}" in result


@mark.parametrize(
    "multirun",
    [False, True],
)
def test_hydra_verbose_1897(tmpdir: Path, multirun: bool) -> None:
    cmd = [
        "tests/test_apps/hydra_verbose/my_app.py",
        f'hydra.run.dir="{tmpdir}"',
        "hydra.job.chdir=False",
    ]
    if multirun:
        cmd += ["+a=1,2", "-m"]
    run_python_script(cmd)


@mark.parametrize(
    "multirun",
    [False, True],
)
def test_hydra_resolver_in_output_dir(tmpdir: Path, multirun: bool) -> None:
    from hydra import __version__

    subdir = "dir" + "${hydra:runtime.version}"

    output_dir = str(Path(tmpdir) / subdir)

    cmd = [
        "tests/test_apps/hydra_resolver_in_output_dir/my_app.py",
        f"hydra.run.dir='{output_dir}'",
        f"hydra.sweep.subdir='{subdir}'",
        f"hydra.sweep.dir={str(Path(tmpdir))}",
        "hydra.job.chdir=False",
    ]

    if multirun:
        cmd += ["-m"]

    out, _ = run_python_script(cmd)

    expected_subdir = f"dir{__version__}"
    expected_output_dir = str(Path(tmpdir) / expected_subdir)
    expected_log_file = Path(expected_output_dir) / "my_app.log"
    assert expected_log_file.exists()
    assert expected_output_dir in out


@mark.parametrize(
    "overrides,expected_output,error,warning,warning_msg",
    [
        param(
            ["hydra.mode=RUN"],
            "RunMode.RUN",
            False,
            False,
            None,
            id="single_run_config",
        ),
        param(
            ["x=1", "hydra.mode=MULTIRUN"],
            dedent("""\
                [HYDRA] Launching 1 jobs locally
                [HYDRA] \t#0 : x=1
                RunMode.MULTIRUN"""),
            False,
            False,
            None,
            id="multi_run_config",
        ),
        param(
            ["--multirun", "x=1"],
            dedent("""\
                [HYDRA] Launching 1 jobs locally
                [HYDRA] \t#0 : x=1
                RunMode.MULTIRUN"""),
            False,
            False,
            None,
            id="multi_run_commandline",
        ),
        param(
            ["x=1", "--multirun", "hydra.mode=MULTIRUN"],
            dedent("""\
                [HYDRA] Launching 1 jobs locally
                [HYDRA] \t#0 : x=1
                RunMode.MULTIRUN"""),
            False,
            False,
            None,
            id="multi_run_commandline_between_overrides",
        ),
        param(
            [],
            dedent("""\
                RunMode.RUN"""),
            False,
            False,
            None,
            id="run_with_no_config",
        ),
        param(
            ["x=1,2", "hydra.mode=RUN"],
            dedent("""\
                Ambiguous value for argument 'x=1,2'
                1. To use it as a list, use key=[value1,value2]
                2. To use it as string, quote the value: key=\\'value1,value2\\'
                3. To sweep over it, add --multirun to your command line
                """),
            True,
            False,
            None,
            id="illegal_sweep_run",
        ),
        param(
            ["x=1,2", "hydra.mode=MULTIRUN"],
            dedent("""\
                [HYDRA] Launching 2 jobs locally
                [HYDRA] \t#0 : x=1
                RunMode.MULTIRUN
                [HYDRA] \t#1 : x=2
                RunMode.MULTIRUN"""),
            False,
            False,
            None,
            id="sweep_from_config",
        ),
        param(
            ["x=1,2", "hydra.mode=MULTIRUN", "hydra/sweeper=test"],
            dedent("""\
                [HYDRA] Launching 1 jobs locally
                [HYDRA] \t#0 : x=1
                RunMode.MULTIRUN
                [HYDRA] Launching 1 jobs locally
                [HYDRA] \t#1 : x=2
                RunMode.MULTIRUN
                """),
            False,
            False,
            None,
            id="sweep_from_config_with_custom_sweeper",
        ),
        param(
            ["--multirun", "x=1,2", "hydra.mode=RUN"],
            dedent("""
                [HYDRA] Launching 2 jobs locally
                [HYDRA] \t#0 : x=1
                RunMode.MULTIRUN
                [HYDRA] \t#1 : x=2
                RunMode.MULTIRUN"""),
            False,
            True,
            dedent("""
                .*: UserWarning:
                \tRunning Hydra app with --multirun, overriding with `hydra.mode=MULTIRUN`.
                .*
                """),
            id="multirun_commandline_with_run_config_with_warning",
        ),
    ],
)
def test_hydra_mode(
    tmpdir: Path,
    overrides: List[str],
    expected_output: str,
    error: bool,
    warning: bool,
    warning_msg: Optional[str],
) -> None:
    cmd = [
        "tests/test_apps/app_print_hydra_mode/my_app.py",
    ]
    cmd.extend(overrides)
    cmd.extend(
        [
            f"hydra.run.dir='{tmpdir}'",
            f"hydra.sweep.dir={tmpdir}",
            "hydra.job.chdir=False",
            "hydra.hydra_logging.formatters.simple.format='[HYDRA] %(message)s'",
            "hydra.job_logging.formatters.simple.format='[JOB] %(message)s'",
        ]
    )
    if error:
        expected = normalize_newlines(expected_output)
        ret = run_with_error(cmd)
        assert_regex_match(
            from_line=expected,
            to_line=ret,
            from_name="Expected output",
            to_name="Actual output",
        )
    elif warning:
        out, err = run_python_script(cmd, allow_warnings=True)
        assert_regex_match(
            from_line=expected_output,
            to_line=out,
            from_name="Expected output",
            to_name="Actual output",
        )
        assert warning_msg is not None
        assert_regex_match(
            from_line=warning_msg,
            to_line=err,
            from_name="Expected error",
            to_name="Actual error",
        )
    else:
        out, _ = run_python_script(cmd)
        assert_regex_match(
            from_line=expected_output,
            to_line=out,
            from_name="Expected output",
            to_name="Actual output",
        )


def test_hydra_runtime_choice_1882(tmpdir: Path) -> None:
    cmd = [
        "tests/test_apps/app_with_cfg_groups/my_app_with_runtime_choices_print.py",
        "--multirun",
        f"hydra.sweep.dir={tmpdir}",
        "hydra.hydra_logging.formatters.simple.format='[HYDRA] %(message)s'",
        "hydra.job_logging.formatters.simple.format='[JOB] %(message)s'",
        "hydra.job.chdir=False",
        "optimizer=adam,nesterov",
    ]
    expected_output = dedent("""
                [HYDRA] Launching 2 jobs locally
                [HYDRA] \t#0 : optimizer=adam
                adam
                [HYDRA] \t#1 : optimizer=nesterov
                nesterov""")

    out, _ = run_python_script(cmd)
    assert_regex_match(
        from_line=expected_output,
        to_line=out,
        from_name="Expected output",
        to_name="Actual output",
    )


RESOLVED: dict[str, Any] = {}


class ControllerProbe(Callback):
    def __init__(self, controller_cwd: str) -> None:
        RESOLVED["controller_cwd"] = controller_cwd


class RaisingCallback(Callback):
    def __init__(self) -> None:
        raise RuntimeError("boom")


def test_controller_resolution_and_restore(
    hydra_restore_singletons: Any,
    hydra_sweep_runner: TSweepRunner,
    tmpdir: Path,
) -> None:
    """Regression for #3427: controller ${hydra:...} resolves; HydraConfig restored."""
    RESOLVED.clear()
    assert not HydraConfig.initialized()
    seen: dict[str, Any] = {}

    def task(cfg: DictConfig) -> None:
        seen["job_id"] = HydraConfig.get().job.id

    with (
        execution_whitelist("tests.test_hydra.*"),
        hydra_sweep_runner(
            calling_file="tests/test_apps/simple_app/my_app.py",
            calling_module=None,
            config_path=None,
            config_name=None,
            task_function=task,
            overrides=[
                "+x=1",
                "+hydra.callbacks.probe._target_=tests.test_hydra.ControllerProbe",
                "+hydra.callbacks.probe.controller_cwd=${hydra:runtime.cwd}",
            ],
            temp_dir=tmpdir,
        ),
    ):
        pass

    assert "controller_cwd" in RESOLVED
    assert seen["job_id"] == "0"
    assert not HydraConfig.initialized()


def test_multirun_restores_hydra_config_when_sweep_raises(
    hydra_restore_singletons: Any,
    hydra_sweep_runner: TSweepRunner,
    tmpdir: Path,
) -> None:
    """HydraConfig must be restored even when the sweep raises."""
    assert not HydraConfig.initialized()

    with raises(RuntimeError, match="boom"):
        with (
            execution_whitelist("tests.test_hydra.*"),
            hydra_sweep_runner(
                calling_file="tests/test_apps/simple_app/my_app.py",
                calling_module=None,
                config_path=None,
                config_name=None,
                task_function=None,
                overrides=[
                    "+x=1",
                    "+hydra.callbacks.boom._target_=tests.test_hydra.RaisingCallback",
                ],
                temp_dir=tmpdir,
            ),
        ):
            pass

    assert not HydraConfig.initialized()
