# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from base64 import b64encode
from pickle import UnpicklingError

import pytest
from hydra.core.plugins import Plugins
from hydra.errors import CompactHydraException
from hydra.plugins.launcher import Launcher
from hydra.test_utils.launcher_common_tests import (
    IntegrationTestSuite,
    LauncherTestSuite,
)
from hydra.test_utils.test_utils import TSweepRunner, chdir_plugin_root
from pytest import mark
from rq.serializers import DefaultSerializer

from hydra_plugins.hydra_rq_launcher._core import _get_job_result
from hydra_plugins.hydra_rq_launcher.rq_launcher import RQLauncher
from hydra_plugins.hydra_rq_launcher.serializer import CloudpickleSerializer

chdir_plugin_root()


def test_discovery() -> None:
    # Tests that this plugin can be discovered via the plugins subsystem when looking for Launchers
    assert RQLauncher.__name__ in [
        x.__name__ for x in Plugins.instance().discover(Launcher)
    ]


# https://github.com/rq/rq/issues/1244
@mark.filterwarnings("ignore::DeprecationWarning")
@mark.parametrize("launcher_name, overrides", [("rq", [])])
class TestRQLauncher(LauncherTestSuite):
    """
    Run the Launcher test suite on this launcher.
    """

    pass


# https://github.com/rq/rq/issues/1244
@mark.filterwarnings("ignore::DeprecationWarning")
@mark.parametrize(
    "task_launcher_cfg, extra_flags",
    [({}, ["-m", "hydra/launcher=rq"])],
)
class TestRQLauncherIntegration(IntegrationTestSuite):
    """
    Run this launcher through the integration test suite.
    """

    pass


# https://github.com/rq/rq/issues/1244
@mark.filterwarnings("ignore::DeprecationWarning")
@mark.parametrize("params_overrides", [[], ["hydra.launcher.redis.ssl=true"]])
def test_example_app(
    hydra_sweep_runner: TSweepRunner, params_overrides: list[str]
) -> None:
    with hydra_sweep_runner(
        calling_file="example/my_app.py",
        calling_module=None,
        task_function=None,
        config_path=".",
        config_name="config",
        overrides=["task=1,2,3,4"] + params_overrides,
    ) as sweep:
        overrides = {("task=1",), ("task=2",), ("task=3",), ("task=4",)}

        assert sweep.returns is not None and len(sweep.returns[0]) == 4
        for ret in sweep.returns[0]:
            assert tuple(ret.overrides) in overrides


def test_cloudpickle_serializer() -> None:
    def value(x: int) -> int:
        return x + 1

    assert CloudpickleSerializer.loads(CloudpickleSerializer.dumps(value))(41) == 42


def test_unserializable_rq_result_error() -> None:
    class Connection:
        def hget(self, key: str, field: str) -> bytes:
            assert key == "rq:job:123"
            assert field == "result"
            return b"Unserializable return value"

    class Job:
        key = "rq:job:123"
        connection = Connection()

        def get_id(self) -> str:
            return "123"

        @property
        def result(self) -> object:
            raise UnpicklingError("pickle data was truncated")

    with pytest.raises(CompactHydraException, match="cloudpickle serializer"):
        _get_job_result(Job())


def test_unserializable_rq_result_stream_error() -> None:
    class Connection:
        def hget(self, key: str, field: str) -> None:
            assert key == "rq:job:123"
            assert field == "result"
            return None

        def xrevrange(self, key: str, start: str, end: str, count: int) -> list[object]:
            assert key == "rq:results:123"
            assert start == "+"
            assert end == "-"
            assert count == 1
            return [
                (
                    b"1-0",
                    {
                        b"return_value": b64encode(
                            DefaultSerializer.dumps("Unserializable return value")
                        ),
                    },
                )
            ]

    class Job:
        id = "123"
        key = "rq:job:123"
        connection = Connection()

        def return_value(self) -> object:
            raise UnpicklingError("pickle data was truncated")

    with pytest.raises(CompactHydraException, match="cloudpickle serializer"):
        _get_job_result(Job())
