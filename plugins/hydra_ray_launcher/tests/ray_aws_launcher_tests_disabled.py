# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
"""Legacy Ray AWS tests disabled from automatic pytest collection.

Hydra no longer has the AWS test infrastructure required to run these tests.
"""

import logging
import os
import random
import string
import subprocess
import sys
import tempfile
from importlib.metadata import version as metadata_version
from pathlib import Path
from typing import Any, Generator

import boto3  # type: ignore
from botocore.exceptions import (  # type: ignore
    ClientError,
    NoCredentialsError,
    NoRegionError,
)
from hydra.core.plugins import Plugins
from hydra.plugins.launcher import Launcher
from hydra.test_utils.launcher_common_tests import (
    IntegrationTestSuite,
    LauncherTestSuite,
)
from hydra.test_utils.test_utils import chdir_hydra_root, chdir_plugin_root
from omegaconf import OmegaConf
from pytest import fixture, mark

from hydra_plugins.hydra_ray_launcher.ray_aws_launcher import RayAWSLauncher

# Static type checkers can complain about "unused type: ignore comment" on macos
# workaround adapted from: https://github.com/twisted/twisted/pull/1416
try:
    import importlib

    sdk: Any = importlib.import_module("ray.autoscaler.sdk")
except ModuleNotFoundError as e:
    raise ImportError(e)


temp_remote_dir = "/tmp/hydra_test/"  # nosec
temp_remote_wheel_dir = "/tmp/wheels/"  # nosec
sweep_dir = "tmp_pytest_dir"  # nosec

cluster_name = "IntegrationTest-" + "".join(
    [random.choice(string.ascii_letters + string.digits) for n in range(5)]
)
win_msg = "Ray doesn't support Windows."
cur_py_version = f"{sys.version_info.major}.{sys.version_info.minor}"

aws_not_configured_msg = "AWS credentials not configured correctly. Skipping AWS tests."
try:
    ec2 = boto3.client("ec2")
    ec2.describe_regions()
    aws_not_configured = False
except (ClientError, NoCredentialsError, NoRegionError):
    aws_not_configured = True


ami = os.environ.get("AWS_RAY_AMI", "ami-05783271555147544")
security_group_id = os.environ.get("AWS_RAY_SECURITY_GROUP", "sg-0a12b09a5ff961aee")
subnet_id = os.environ.get("AWS_RAY_SUBNET", "subnet-acd2cfe7")
instance_role = os.environ.get(
    "INSTANCE_ROLE_ARN", "arn:aws:iam::135937774131:instance-profile/ray-autoscaler-v1"
)

assert (
    ami != "" and security_group_id != "" and subnet_id != "" and instance_role != ""
), (
    f"Missing variable for test, ami={ami}, security_group_id={security_group_id}, subnet_id={subnet_id}, "
    f"instance_role={instance_role}"
)

node_config = {
    "InstanceType": "m5.large",
    "ImageId": ami,
    "SubnetId": f"{subnet_id}",
    "SecurityGroupIds": [security_group_id],
    "IamInstanceProfile": {"Arn": instance_role},
}

ray_nodes_conf = {
    "ray.head.default": {
        "resources": {},
        "node_config": node_config,
    },
    "ray.worker.default": {
        "min_workers": 0,
        "max_workers": 2,
        "resources": {},
        "node_config": node_config,
    },
}


ray_nodes_conf_override = str(ray_nodes_conf).replace("'", "").replace(" ", "")

pip_lib_skip = [
    "omegaconf",
    "hydra_core",
    "ray",
    "cloudpickle",
    "pickle5",
    "hydra_ray_launcher",
]

common_overrides = [
    f"hydra.launcher.ray.cluster.cluster_name={cluster_name}",
    "hydra.launcher.stop_cluster=False",
    "hydra.launcher.logging.log_style='auto'",
    "hydra.launcher.logging.color_mode='auto'",
    "hydra.launcher.logging.verbosity=1",
    "hydra.launcher.create_update_cluster.no_restart=False",
    "hydra.launcher.create_update_cluster.restart_only=False",
    "hydra.launcher.create_update_cluster.no_config_cache=False",
    "hydra.launcher.teardown_cluster.workers_only=False",
    "hydra.launcher.teardown_cluster.keep_min_workers=False",
    f"hydra.launcher.ray.cluster.provider.key_pair.key_name=hydra_test_{cluster_name}",
    # Port 443 is blocked for testing instance, as a result, pip install would fail.
    # To get around this, we pre-install all the dependencies on the test AMI.
    "hydra.launcher.ray.cluster.setup_commands=[]",
    "hydra.launcher.env_setup.commands=[]",
    f"+hydra.launcher.ray.cluster.available_node_types={ray_nodes_conf_override}",
]
common_overrides.extend(
    [f"~hydra.launcher.env_setup.pip_packages.{lib}" for lib in pip_lib_skip]
)

log = logging.getLogger(__name__)

chdir_plugin_root()


def run_command(commands: str) -> str:
    log.info(f"running: {commands}")
    output = subprocess.getoutput(commands)  # nosec B605
    log.info(f"outputs: {output}")
    return output


def build_ray_launcher_wheel(tmp_wheel_dir: str) -> str:
    chdir_hydra_root()
    plugin = "hydra_ray_launcher"
    os.chdir(Path("plugins") / plugin)
    log.info(f"Build wheel for {plugin}, save wheel to {tmp_wheel_dir}.")
    run_command("python setup.py sdist bdist_wheel")
    run_command(f"cp dist/*.whl {tmp_wheel_dir}")
    log.info("Download all plugin dependency wheels.")
    run_command(f"pip download . -d {tmp_wheel_dir}")
    plugin_wheel = run_command("ls dist/*.whl").split("/")[-1]
    chdir_hydra_root()
    return plugin_wheel


def build_core_wheel(tmp_wheel_dir: str) -> str:
    chdir_hydra_root()
    run_command("python setup.py sdist bdist_wheel")
    run_command(f"cp dist/*.whl {tmp_wheel_dir}")

    # download dependency wheel for hydra-core
    run_command(f"pip download -r requirements/requirements.txt -d {tmp_wheel_dir}")
    wheel = run_command("ls dist/*.whl").split("/")[-1]
    return wheel


def upload_and_install_wheels(
    tmp_wheel_dir: str,
    connect_config: dict[Any, Any],
    core_wheel: str,
    plugin_wheel: str,
) -> None:
    sdk.rsync(
        connect_config,
        source=tmp_wheel_dir + "/",
        target=temp_remote_wheel_dir,
        down=False,
    )
    log.info(f"Install hydra-core wheel {core_wheel}")
    sdk.run_on_cluster(
        connect_config,
        cmd=f"pip install --no-index --find-links={temp_remote_wheel_dir} {temp_remote_wheel_dir}{core_wheel}",
        with_output=True,
    )
    log.info(f"Install plugin wheel {plugin_wheel} ")
    log.info(
        f"pip install --no-index --find-links={temp_remote_wheel_dir} {temp_remote_wheel_dir}{plugin_wheel}"
    )
    sdk.run_on_cluster(
        connect_config,
        cmd=f"pip install --no-index --find-links={temp_remote_wheel_dir} {temp_remote_wheel_dir}{plugin_wheel}",
        with_output=True,
    )


def parse_python_minor_version(version: str) -> str:
    micro_start = version.rfind(".")
    return version[:micro_start]


def validate_lib_version(connect_config: dict[Any, Any]) -> None:
    # a few lib versions that we care about
    libs = ["ray", "cloudpickle", "pickle5"]
    for lib in libs:
        local_version = metadata_version(lib)
        out = sdk.run_on_cluster(
            connect_config, cmd=f"pip show {lib} | grep Version", with_output=True
        ).decode()
        assert local_version in out, f"{lib} version mismatch"

    # validate python version
    info = sys.version_info
    local_python = f"{info.major}.{info.minor}.{info.micro}"
    out = sdk.run_on_cluster(
        connect_config, cmd="python --version", with_output=True
    ).decode()
    remote_python = out.split()[1]

    assert parse_python_minor_version(local_python) == parse_python_minor_version(
        remote_python
    ), f"Python version mismatch, local={local_python}, remote={remote_python}"


@mark.skipif(sys.platform.startswith("win"), reason=win_msg)
def test_discovery() -> None:
    # Tests that this plugin can be discovered via the plugins subsystem when
    # looking for Launchers
    assert RayAWSLauncher.__name__ in [
        x.__name__ for x in Plugins.instance().discover(Launcher)
    ]


@fixture(scope="module")
def manage_cluster() -> Generator[None, None, None]:
    # first assert the SHA of requirements hasn't changed
    # if changed, means we need to update test AMI.

    # build all the wheels
    tmpdir = tempfile.mkdtemp()
    core_wheel = build_core_wheel(tmpdir)
    plugin_wheel = build_ray_launcher_wheel(tmpdir)
    connect_config = {
        "cluster_name": cluster_name,
        "provider": {
            "type": "aws",
            "region": "us-west-2",
            "availability_zone": "us-west-2a,us-west-2b",
            "cache_stopped_nodes": False,
            "key_pair": {"key_name": f"hydra_test_{cluster_name}"},
        },
        "auth": {"ssh_user": "ubuntu"},
        "setup_commands": [
            f"echo 'export PATH=\"$HOME/anaconda3/envs/hydra_{cur_py_version}/bin:$PATH\"' >> ~/.bashrc"
        ],
        "head_setup_commands": [],
        "available_node_types": ray_nodes_conf,
        "head_node_type": "ray.head.default",
        "head_start_ray_commands": [
            "ray stop",
            "ray start --head",
        ],
    }

    # save connect_config as yaml, this could be useful for debugging
    # you can run `ray attach <connect_config>.yaml` and log on to the AWS cluster for debugging.
    conf = OmegaConf.create(connect_config)
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as fp:
        OmegaConf.save(config=conf, f=fp.name, resolve=True)
        log.info(f"Saving config to {fp.name}")

    sdk.create_or_update_cluster(
        connect_config,
    )
    sdk.run_on_cluster(
        connect_config,
        run_env="auto",
        cmd=f"mkdir -p {temp_remote_dir}",
        with_output=True,
    )
    sdk.run_on_cluster(
        connect_config,
        run_env="auto",
        cmd=f"mkdir -p {temp_remote_wheel_dir}",
        with_output=True,
    )
    upload_and_install_wheels(tmpdir, connect_config, core_wheel, plugin_wheel)
    validate_lib_version(connect_config)
    yield
    sdk.teardown_cluster(connect_config)


launcher_test_suites_overrides = [
    f"hydra.launcher.sync_down.source_dir={sweep_dir}/",
    f"hydra.launcher.sync_down.target_dir={sweep_dir}",
]
launcher_test_suites_overrides.extend(common_overrides)


@mark.skipif(sys.platform.startswith("win"), reason=win_msg)
@mark.skipif(aws_not_configured, reason=aws_not_configured_msg)
@mark.usefixtures("manage_cluster")
@mark.parametrize(
    "launcher_name, overrides, tmpdir",
    [
        (
            "ray_aws",
            launcher_test_suites_overrides,
            Path(sweep_dir),
        )
    ],
)
class TestRayAWSLauncher(LauncherTestSuite):
    pass


integration_tests_override = [
    "-m",
    "hydra/launcher=ray_aws",
    f"hydra.launcher.sync_down.source_dir={temp_remote_dir}/",
    f"hydra.launcher.sync_down.target_dir={temp_remote_dir}",
]
integration_tests_override.extend(common_overrides)


@mark.skipif(sys.platform.startswith("win"), reason=win_msg)
@mark.skipif(aws_not_configured, reason=aws_not_configured_msg)
@mark.usefixtures("manage_cluster")
@mark.parametrize(
    "tmpdir,task_launcher_cfg,extra_flags",
    [
        (
            Path(temp_remote_dir),
            {},
            integration_tests_override,
        )
    ],
)
class TestRayAWSLauncherIntegration(IntegrationTestSuite):
    """
    Run this launcher through the integration test suite.
    """

    def get_test_app_working_dir(self) -> Path | None:
        """
        By default test applications working dir is tmpdir, override this method if that's not the case.
        This could be helpful when the tests kick off applications on remote machines.
        """
        return Path("/home/ubuntu")
