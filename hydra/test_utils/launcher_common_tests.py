# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
"""
Common test functions testing launchers
"""

import copy
import os
import re
import traceback
from pathlib import Path
from typing import Any, Callable

from omegaconf import DictConfig, OmegaConf
from pytest import mark, param, raises

from hydra import TaskFunction
from hydra.errors import HydraException
from hydra.test_utils.test_utils import (
    TSweepRunner,
    integration_test,
    verify_dir_outputs,
)


@mark.usefixtures("hydra_restore_singletons")
class LauncherTestSuite:
    def get_task_function(self) -> Callable[[Any], Any] | None:
        def task_func(_: DictConfig) -> Any:
            return 100

        return task_func

    def test_sweep_1_job(
        self,
        hydra_sweep_runner: TSweepRunner,
        launcher_name: str,
        overrides: list[str],
        tmpdir: Path,
    ) -> None:
        sweep_1_job(
            hydra_sweep_runner,
            overrides=["hydra/launcher=" + launcher_name] + overrides,
            task_function=self.get_task_function(),
            temp_dir=tmpdir,
        )

    def test_sweep_2_jobs(
        self,
        hydra_sweep_runner: TSweepRunner,
        launcher_name: str,
        overrides: list[str],
        tmpdir: Path,
    ) -> None:
        sweep_2_jobs(
            hydra_sweep_runner,
            overrides=["hydra/launcher=" + launcher_name] + overrides,
            task_function=self.get_task_function(),
            temp_dir=tmpdir,
        )

    def test_failure_preserves_task_traceback(
        self,
        hydra_sweep_runner: TSweepRunner,
        launcher_name: str,
        overrides: list[str],
        tmpdir: Path,
    ) -> None:
        def task_func(_: DictConfig) -> None:
            try:
                raise ValueError("launcher cause")
            except ValueError as cause:
                raise RuntimeError("launcher failure") from cause

        sweep = hydra_sweep_runner(
            calling_file=None,
            calling_module="hydra.test_utils.a_module",
            task_function=task_func,
            config_path="configs",
            config_name="compose.yaml",
            overrides=["hydra/launcher=" + launcher_name] + overrides,
            temp_dir=tmpdir,
        )
        try:
            with sweep:
                pass
        except RuntimeError as error:
            failure = error
        else:
            assert sweep.returns is not None
            with raises(RuntimeError, match="launcher failure") as exc_info:
                sweep.returns[0][0].return_value
            failure = exc_info.value

        assert str(failure) == "launcher failure"
        frames = traceback.extract_tb(failure.__traceback__)
        assert any(
            frame.name == "task_func"
            and Path(frame.filename).name == Path(__file__).name
            for frame in frames
        )
        formatted = "".join(
            traceback.TracebackException.from_exception(failure).format()
        )
        assert "ValueError: launcher cause" in formatted
        assert "The above exception was the direct cause" in formatted
        assert "in task_func" in formatted
        assert "RuntimeError: launcher failure" in formatted

    def test_not_sweeping_hydra_overrides(
        self,
        hydra_sweep_runner: TSweepRunner,
        launcher_name: str,
        overrides: list[str],
        tmpdir: Path,
    ) -> None:
        with raises(
            HydraException,
            match=re.escape(
                "Sweeping over Hydra's configuration is not supported : 'hydra.verbose=true,false'"
            ),
        ):
            with hydra_sweep_runner(
                calling_file=None,
                calling_module="hydra.test_utils.a_module",
                task_function=None,
                config_path="configs",
                config_name="compose.yaml",
                overrides=overrides
                + [
                    "hydra/launcher=" + launcher_name,
                    "+a=0,1",
                    "hydra.verbose=true,false",
                ],
                temp_dir=tmpdir,
            ):
                pass

    def test_sweep_1_job_strict(
        self,
        hydra_sweep_runner: TSweepRunner,
        launcher_name: str,
        overrides: list[str],
        tmpdir: Path,
    ) -> None:
        sweep_1_job(
            hydra_sweep_runner,
            overrides=["hydra/launcher=" + launcher_name] + overrides,
            task_function=self.get_task_function(),
            temp_dir=tmpdir,
        )

    def test_sweep_1_job_strict_and_bad_key(
        self,
        hydra_sweep_runner: TSweepRunner,
        launcher_name: str,
        overrides: list[str],
        tmpdir: Path,
    ) -> None:
        # Ideally this would be KeyError, This can't be more specific because some launcher plugins
        # like submitit raises a different exception on job failure and not the underlying exception.
        with raises(Exception):
            sweep_1_job(
                hydra_sweep_runner,
                overrides=["hydra/launcher=" + launcher_name, "boo=bar"] + overrides,
                task_function=self.get_task_function(),
                temp_dir=tmpdir,
            )

    def test_sweep_2_optimizers(
        self,
        hydra_sweep_runner: TSweepRunner,
        launcher_name: str,
        overrides: list[str],
        tmpdir: Path,
    ) -> None:
        sweep_two_config_groups(
            hydra_sweep_runner,
            overrides=["hydra/launcher=" + launcher_name] + overrides,
            task_function=self.get_task_function(),
            temp_dir=tmpdir,
        )

    def test_sweep_over_unspecified_mandatory_default(
        self,
        hydra_sweep_runner: TSweepRunner,
        launcher_name: str,
        overrides: list[str],
        tmpdir: Path,
    ) -> None:
        base_overrides = ["hydra/launcher=" + launcher_name, "group1=file1,file2"]
        sweep = hydra_sweep_runner(
            calling_file=None,
            calling_module="hydra.test_utils.a_module",
            task_function=self.get_task_function(),
            config_path="configs",
            config_name="unspecified_mandatory_default",
            overrides=base_overrides + overrides,
            temp_dir=tmpdir,
        )
        expected_overrides = [["group1=file1"], ["group1=file2"]]
        expected_conf = [OmegaConf.create({"foo": 10}), OmegaConf.create({"foo": 20})]
        with sweep:
            assert sweep.returns is not None
            assert len(sweep.returns[0]) == 2
            for i in range(2):
                job_ret = sweep.returns[0][i]
                assert job_ret.overrides == expected_overrides[i]
                assert job_ret.cfg == expected_conf[i]
                verify_dir_outputs(job_ret, job_ret.overrides)

    def test_sweep_and_override(
        self,
        hydra_sweep_runner: TSweepRunner,
        launcher_name: str,
        overrides: list[str],
        tmpdir: Path,
    ) -> None:
        """
        Tests that we can override things in the configs merged in only during the sweep config construction
        db.user=someone does not exist db_conf.yaml, and is only appear when we merge in db=mysql or db=postgresql.
        This presents a tricky situation when operating in strict mode, this tests verifies it's handled correctly.
        """
        base_overrides = [
            "hydra/launcher=" + launcher_name,
            "db=mysql,postgresql",
            "db.user=someone",
        ]
        sweep = hydra_sweep_runner(
            calling_file=None,
            calling_module="hydra.test_utils.a_module",
            task_function=None,
            config_path="configs",
            config_name="db_conf.yaml",
            overrides=base_overrides + overrides,
            temp_dir=tmpdir,
        )
        expected_overrides = [
            ["db=mysql", "db.user=someone"],
            ["db=postgresql", "db.user=someone"],
        ]
        expected_conf = [
            {"db": {"driver": "mysql", "password": "secret", "user": "someone"}},
            {
                "db": {
                    "user": "someone",
                    "driver": "postgresql",
                    "password": "drowssap",
                    "timeout": 10,
                }
            },
        ]
        with sweep:
            assert sweep.returns is not None
            assert len(sweep.returns[0]) == 2
            for i in range(2):
                job_ret = sweep.returns[0][i]
                assert job_ret.overrides == expected_overrides[i]
                assert job_ret.cfg == expected_conf[i]
                verify_dir_outputs(job_ret, job_ret.overrides)

    def test_sweep_with_custom_resolver(
        self,
        hydra_sweep_runner: TSweepRunner,
        launcher_name: str,
        overrides: list[str],
        tmpdir: Path,
    ) -> None:
        overrides1 = ["hydra/launcher=" + launcher_name] + overrides

        def task_func(c: DictConfig) -> Any:
            return c.x

        sweep = hydra_sweep_runner(
            calling_file=None,
            calling_module="hydra.test_utils.a_module",
            task_function=task_func,
            config_path="configs",
            config_name="custom_resolver",
            overrides=overrides1,
            temp_dir=tmpdir,
        )

        def my_custom_resolver() -> Any:
            return "foo"

        OmegaConf.register_resolver("my_custom_resolver", my_custom_resolver)
        with sweep:
            assert sweep.returns is not None
            job_ret = sweep.returns[0]
            assert len(job_ret) == 1
            assert job_ret[0].return_value == "foo"


@mark.usefixtures("hydra_restore_singletons")
class BatchedSweeperTestSuite:
    def test_sweep_2_jobs_2_batches(
        self,
        hydra_sweep_runner: TSweepRunner,
        launcher_name: str,
        overrides: list[str],
        tmpdir: Path,
    ) -> None:
        job_overrides = ["group1=file1,file2", "bar=100,200,300"]
        hydra_overrides = ["hydra/launcher=" + launcher_name]
        overrides.extend(job_overrides)
        overrides.extend(hydra_overrides)
        sweep = hydra_sweep_runner(
            calling_file=None,
            calling_module="hydra.test_utils.a_module",
            task_function=None,
            config_path="configs",
            config_name="compose.yaml",
            overrides=overrides,
            temp_dir=tmpdir,
        )
        expected_overrides = [
            ["group1=file1", "bar=100"],
            ["group1=file1", "bar=200"],
            ["group1=file1", "bar=300"],
            ["group1=file2", "bar=100"],
            ["group1=file2", "bar=200"],
            ["group1=file2", "bar=300"],
        ]

        expected_conf = [
            {"foo": 10, "bar": 100},
            {"foo": 10, "bar": 200},
            {"foo": 10, "bar": 300},
            {"foo": 20, "bar": 100},
            {"foo": 20, "bar": 200},
            {"foo": 20, "bar": 300},
        ]

        dirs: set[str] = set()
        with sweep:
            temp_dir = sweep.temp_dir
            assert temp_dir is not None
            multirun_cfg_path = Path(temp_dir) / "multirun.yaml"
            assert multirun_cfg_path.exists()
            multirun_cfg = OmegaConf.load(multirun_cfg_path)
            assert multirun_cfg.hydra.overrides.task == job_overrides

            assert sweep.returns is not None
            # expecting 3 batches of 2
            assert len(sweep.returns) == 3
            for batch in sweep.returns:
                assert len(batch) == 2

            flat = [rt for batch in sweep.returns for rt in batch]
            assert len(flat) == 6  # with a total of 6 jobs
            for idx, job_ret in enumerate(flat):
                assert job_ret.overrides == expected_overrides[idx]
                assert job_ret.cfg == expected_conf[idx]
                assert job_ret.hydra_cfg is not None
                dirs.add(job_ret.hydra_cfg.hydra.runtime.output_dir)
                verify_dir_outputs(job_ret, job_ret.overrides)
        assert len(dirs) == 6  # and a total of 6 unique output directories


def sweep_1_job(
    hydra_sweep_runner: TSweepRunner,
    overrides: list[str],
    task_function: TaskFunction | None,
    temp_dir: Path,
) -> None:
    """
    Runs a sweep with one job
    """
    sweep = hydra_sweep_runner(
        calling_file=None,
        calling_module="hydra.test_utils.a_module",
        task_function=task_function,
        config_path="configs",
        config_name="compose.yaml",
        overrides=overrides,
        temp_dir=temp_dir,
    )

    with sweep:
        assert sweep.returns is not None
        job_ret = sweep.returns[0]
        assert len(job_ret) == 1
        assert job_ret[0].overrides == []
        assert job_ret[0].cfg == {"foo": 10, "bar": 100}
        assert job_ret[0].hydra_cfg.hydra.job.name == "a_module", (
            "Unexpected job name: " + job_ret[0].hydra_cfg.hydra.job.name
        )
        assert job_ret[0].hydra_cfg.hydra.job.id is not None
        assert job_ret[0].hydra_cfg.hydra.job.num is not None
        verify_dir_outputs(sweep.returns[0][0])


def sweep_2_jobs(
    hydra_sweep_runner: TSweepRunner,
    overrides: list[str],
    task_function: TaskFunction | None,
    temp_dir: Path,
) -> None:
    """
    Runs a sweep with two jobs
    """
    job_overrides = ["+a=0,1"]
    overrides.extend(job_overrides)
    sweep = hydra_sweep_runner(
        calling_file=None,
        calling_module="hydra.test_utils.a_module",
        task_function=task_function,
        config_path="configs",
        config_name="compose",
        overrides=overrides,
        temp_dir=temp_dir,
    )
    base_cfg = {"foo": 10, "bar": 100, "a": 0}

    with sweep:
        assert sweep.temp_dir is not None
        assert sweep.returns is not None

        temp_dir = Path(sweep.temp_dir)

        multirun_cfg_path = temp_dir / "multirun.yaml"
        assert multirun_cfg_path.exists()
        multirun_cfg = OmegaConf.load(multirun_cfg_path)
        assert multirun_cfg.hydra.overrides.task == job_overrides

        assert len(sweep.returns[0]) == 2
        for i in range(2):
            job_ret = sweep.returns[0][i]
            expected_conf = OmegaConf.create(base_cfg)
            expected_conf.a = i
            assert job_ret.overrides == [f"+a={i}"]
            assert job_ret.cfg == expected_conf
            assert job_ret.hydra_cfg.hydra.job.name == "a_module", (
                "Unexpected job name: " + job_ret.hydra_cfg.hydra.job.name
            )
            assert job_ret.hydra_cfg.hydra.job.id is not None
            assert job_ret.hydra_cfg.hydra.job.num is not None

            verify_dir_outputs(job_ret, job_ret.overrides)
            path = temp_dir / str(i)
            lst = [x for x in temp_dir.iterdir() if x.is_dir()]
            assert path.exists(), f"'{path}' does not exist, dirs: {lst}"


def sweep_two_config_groups(
    hydra_sweep_runner: TSweepRunner,
    overrides: list[str],
    task_function: TaskFunction | None,
    temp_dir: Path,
) -> None:
    """
    Make sure that optimizers=adam,nesterov is interpreted correctly
    """
    overrides = copy.deepcopy(overrides)
    overrides.extend(["group1=file1,file2"])
    sweep = hydra_sweep_runner(
        calling_file=None,
        calling_module="hydra.test_utils.a_module",
        task_function=task_function,
        config_path="configs",
        config_name="compose",
        overrides=overrides,
        temp_dir=temp_dir,
    )
    expected_overrides = [["group1=file1"], ["group1=file2"]]
    expected_conf = [
        OmegaConf.create({"foo": 10, "bar": 100}),
        OmegaConf.create({"foo": 20, "bar": 100}),
    ]
    with sweep:
        assert sweep.returns is not None
        assert len(sweep.returns[0]) == 2
        for i in range(2):
            job_ret = sweep.returns[0][i]
            assert job_ret.overrides == expected_overrides[i]
            assert job_ret.cfg == expected_conf[i]
            verify_dir_outputs(job_ret, job_ret.overrides)


@mark.usefixtures("hydra_restore_singletons")
class IntegrationTestSuite:
    def get_test_app_working_dir(self) -> Path | None:
        """
        By default test applications working dir is tmpdir, override this method if that's not the case.
        This could be helpful when the tests kick off applications on remote machines.
        """
        return None

    def get_test_scratch_dir(self, tmpdir: Path) -> Path:
        """
        By default test applications will use tmpdir provided by the
        This can be customized by applications.
        """
        return tmpdir

    def generate_custom_cmd(self) -> Callable[..., list[str]]:
        """
        By default this does nothing, but it allows custom execution commands.
        Useful if the tests are not kicked off by python
        """

        def fun(cmd: list[str], filename: str) -> list[str]:
            """
            param cmd: old python commands in list of strings
            param filename: file name to be executed as main hydra module
            return: new commands to be executed in list of strings
            """
            return cmd

        return fun

    @mark.parametrize(
        "task_config, overrides, filename, expected_name",
        [
            param(None, [], "no_config.py", "no_config", id="no_config"),
            param(
                None,
                ["hydra.job.name=overridden_name"],
                "no_config.py",
                "overridden_name",
                id="different_filename",
            ),
            param(
                {"hydra": {"job": {"name": "name_from_config_file"}}},
                [],
                "with_config.py",
                "name_from_config_file",
                id="different_filename_and_config_file_name_override",
            ),
            param(
                {"hydra": {"job": {"name": "name_from_config_file"}}},
                ["hydra.job.name=overridden_name"],
                "with_config.py",
                "overridden_name",
                id="different_filename_and_config_file_name_override_and_command_line_override",
            ),
        ],
    )
    def test_custom_task_name(
        self,
        tmpdir: Path,
        task_config: DictConfig,
        overrides: list[str],
        filename: str,
        expected_name: str,
        task_launcher_cfg: DictConfig,
        extra_flags: list[str],
    ) -> None:
        overrides = extra_flags + overrides
        task_launcher_cfg = OmegaConf.create(task_launcher_cfg or {})
        task_config = OmegaConf.create(task_config or {})
        cfg = OmegaConf.merge(task_launcher_cfg, task_config)
        assert isinstance(cfg, DictConfig)

        integration_test(
            tmpdir=self.get_test_scratch_dir(tmpdir),
            task_config=cfg,
            overrides=overrides,
            prints="HydraConfig.get().job.name",
            expected_outputs=expected_name,
            filename=filename,
            generate_custom_cmd=self.generate_custom_cmd(),
        )

    @mark.parametrize(
        "task_config, overrides, expected_dir",
        [
            param(
                {
                    "hydra": {
                        "sweep": {
                            "dir": "task_cfg",
                            "subdir": "task_cfg_${hydra.job.num}",
                        }
                    }
                },
                [],
                "task_cfg/task_cfg_0",
                id="sweep_dir_config_override",
            ),
            param(
                {},
                [
                    "hydra.sweep.dir=cli_dir",
                    "hydra.sweep.subdir=cli_dir_${hydra.job.num}",
                ],
                "cli_dir/cli_dir_0",
                id="sweep_dir_cli_override",
            ),
            param(
                {
                    "hydra": {
                        "sweep": {
                            "dir": "task_cfg",
                            "subdir": "task_cfg_${hydra.job.num}",
                        }
                    }
                },
                [
                    "hydra.sweep.dir=cli_dir",
                    "hydra.sweep.subdir=cli_dir_${hydra.job.num}",
                ],
                "cli_dir/cli_dir_0",
                id="sweep_dir_cli_overridding_config",
            ),
            param(
                {
                    "hydra": {
                        "sweep": {
                            "dir": "hydra_cfg",
                            "subdir": "${hydra_override_dirname:}",
                        }
                    },
                    "a": "hello",
                    "b": 20,
                },
                ["a=1", "b=2"],
                "hydra_cfg/a=1,b=2",
                id="subdir:override_dirname",
            ),
            param(
                # Test override_dirname integration
                {
                    "hydra": {
                        "sweep": {
                            "dir": "hydra_cfg",
                            "subdir": "${hydra_override_dirname:}",
                        },
                        "job": {
                            "config": {
                                "override_dirname": {
                                    "kv_sep": "_",
                                    "item_sep": "+",
                                    "exclude_keys": ["seed"],
                                }
                            }
                        },
                    },
                    "a": "hello",
                    "b": 20,
                    "seed": "???",
                },
                ["a=1", "b=2", "seed=10"],
                "hydra_cfg/a_1+b_2",
                id="subdir:custom_override_dirname",
            ),
        ],
    )
    def test_custom_sweeper_run_workdir(
        self,
        tmpdir: Path,
        task_config: str,
        overrides: list[str],
        expected_dir: str,
        task_launcher_cfg: DictConfig,
        extra_flags: list[str],
    ) -> None:
        overrides = extra_flags + overrides
        task_launcher_cfg = OmegaConf.create(task_launcher_cfg or {})
        task_config = OmegaConf.create(task_config or {})  # type: ignore
        cfg = OmegaConf.merge(task_launcher_cfg, task_config)
        assert isinstance(cfg, DictConfig)
        test_app_dir = self.get_test_app_working_dir()
        expected_outputs = (
            str(self.get_test_scratch_dir(test_app_dir) / expected_dir)
            if test_app_dir
            else str(self.get_test_scratch_dir(tmpdir) / expected_dir)
        )

        integration_test(
            tmpdir=self.get_test_scratch_dir(tmpdir),
            task_config=cfg,
            overrides=overrides + ["hydra.job.chdir=True"],
            prints="os.getcwd()",
            expected_outputs=re.escape(expected_outputs),
            generate_custom_cmd=self.generate_custom_cmd(),
        )

    def test_get_orig_dir_multirun(
        self, tmpdir: Path, task_launcher_cfg: DictConfig, extra_flags: list[str]
    ) -> None:
        overrides = extra_flags
        task_launcher_cfg = OmegaConf.create(task_launcher_cfg or {})
        task_config = OmegaConf.create()
        cfg = OmegaConf.merge(task_launcher_cfg, task_config)
        assert isinstance(cfg, DictConfig)

        integration_test(
            tmpdir=self.get_test_scratch_dir(tmpdir),
            task_config=cfg,
            overrides=overrides,
            prints="hydra.utils.get_original_cwd()",
            expected_outputs=re.escape(
                os.path.realpath(str(self.get_test_scratch_dir(tmpdir)))
            ),
            generate_custom_cmd=self.generate_custom_cmd(),
        )

    def test_to_absolute_path_multirun(
        self, tmpdir: Path, task_launcher_cfg: DictConfig, extra_flags: list[str]
    ) -> None:
        expected_dir = "cli_dir/cli_dir_0"
        overrides = extra_flags + [
            "hydra.job.chdir=True",
            "hydra.sweep.dir=cli_dir",
            "hydra.sweep.subdir=cli_dir_${hydra.job.num}",
        ]
        task_launcher_cfg = OmegaConf.create(task_launcher_cfg or {})
        task_config = OmegaConf.create()
        cfg = OmegaConf.merge(task_launcher_cfg, task_config)
        assert isinstance(cfg, DictConfig)
        path = str(Path("/foo/bar").absolute())
        # Hack to use the right drive on windows
        if path.startswith("D:"):
            path = path.replace("D:", "C:", 1)
        integration_test(
            tmpdir=self.get_test_scratch_dir(tmpdir),
            task_config=cfg,
            overrides=overrides,
            prints="hydra.utils.to_absolute_path('/foo/bar')",
            expected_outputs=re.escape(path),
            generate_custom_cmd=self.generate_custom_cmd(),
        )
        test_app_dir = self.get_test_app_working_dir()
        working_dir = test_app_dir if test_app_dir else tmpdir

        outputs = [
            os.path.realpath(str(self.get_test_scratch_dir(tmpdir) / "foo/bar")),
            str(self.get_test_scratch_dir(working_dir) / expected_dir),
        ]
        integration_test(
            tmpdir=self.get_test_scratch_dir(tmpdir),
            task_config=cfg,
            overrides=overrides,
            prints=["hydra.utils.to_absolute_path('foo/bar')", "os.getcwd()"],
            expected_outputs=[re.escape(output) for output in outputs],
            generate_custom_cmd=self.generate_custom_cmd(),
        )
