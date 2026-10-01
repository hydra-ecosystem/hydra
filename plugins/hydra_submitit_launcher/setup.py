# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
# type: ignore
from pathlib import Path

from read_version import read_version
from setuptools import find_namespace_packages, setup

setup(
    name="hydra-submitit-launcher",
    version=read_version("hydra_plugins/hydra_submitit_launcher", "__init__.py"),
    author="Jeremy Rapin, Jieru Hu, Omry Yadan",
    author_email="jrapin@meta.com, jieru@meta.com, omry@yadan.net",
    description="Submitit Launcher for Hydra apps",
    license="MIT",
    long_description=(Path(__file__).parent / "README.md").read_text(),
    long_description_content_type="text/markdown",
    url="https://github.com/facebookincubator/submitit",
    packages=find_namespace_packages(include=["hydra_plugins.*"]),
    entry_points={
        "hydra.plugins": [
            "submitit_local = hydra_plugins.hydra_submitit_launcher.submitit_launcher:LocalLauncher",
            "submitit_slurm = hydra_plugins.hydra_submitit_launcher.submitit_launcher:SlurmLauncher",
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
        "Development Status :: 4 - Beta",
    ],
    python_requires=">=3.10",
    install_requires=[
        "hydra-core>=1.4.0.dev1,<1.5.0.dev0",
        "submitit>=1.5.0",
    ],
    include_package_data=True,
)
