# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
# type: ignore
from pathlib import Path

from read_version import read_version
from setuptools import find_namespace_packages, setup

setup(
    name="hydra-ray-launcher",
    version=read_version("hydra_plugins/hydra_ray_launcher", "__init__.py"),
    author="Jieru Hu",
    description="Hydra Ray launcher plugin",
    license="MIT",
    long_description=(Path(__file__).parent / "README.md").read_text(),
    long_description_content_type="text/markdown",
    url="https://github.com/hydra-ecosystem/hydra/",
    packages=find_namespace_packages(include=["hydra_plugins.*"]),
    entry_points={
        "hydra.plugins": [
            "ray = hydra_plugins.hydra_ray_launcher.ray_launcher:RayLauncher",
            "ray_aws = hydra_plugins.hydra_ray_launcher.ray_aws_launcher:RayAWSLauncher",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Operating System :: MacOS",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires=">=3.10",
    install_requires=[
        "boto3",
        "hydra-core>=1.4.0.dev1,<1.5.0.dev0",
        "ray[default]>=2.55.0,<3",
        "aiohttp<4",
        "cloudpickle>=3.1.2,<4",
    ],
    include_package_data=True,
)
