# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
# type: ignore
from pathlib import Path

from read_version import read_version
from setuptools import find_namespace_packages, setup

setup(
    name="hydra-joblib-launcher",
    version=read_version("hydra_plugins/hydra_joblib_launcher", "__init__.py"),
    author="Jan-Matthis Lueckmann, Omry Yadan",
    author_email="mail@jan-matthis.de, omry@yadan.net",
    description="Joblib Launcher for Hydra apps",
    license="MIT",
    long_description=(Path(__file__).parent / "README.md").read_text(),
    long_description_content_type="text/markdown",
    url="https://github.com/hydra-ecosystem/hydra/",
    packages=find_namespace_packages(include=["hydra_plugins.*"]),
    entry_points={
        "hydra.plugins": [
            "joblib = hydra_plugins.hydra_joblib_launcher.joblib_launcher:JoblibLauncher"
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Operating System :: MacOS",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires=">=3.10",
    install_requires=[
        "hydra-core>=1.4.0.dev1,<1.5.0.dev0",
        "joblib>=1.5.3",
        "cloudpickle>=3.1.2",
    ],
    include_package_data=True,
)
