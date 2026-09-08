# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
# type: ignore
from pathlib import Path

from read_version import read_version
from setuptools import find_namespace_packages, setup

setup(
    name="hydra-optuna-sweeper",
    version=read_version("hydra_plugins/hydra_optuna_sweeper", "__init__.py"),
    author="Toshihiko Yanase, Hiroyuki Vincent Yamazaki",
    author_email="toshihiko.yanase@gmail.com, hiroyuki.vincent.yamazaki@gmail.com",
    description="Hydra Optuna Sweeper plugin",
    license="MIT",
    long_description=(Path(__file__).parent / "README.md").read_text(),
    long_description_content_type="text/markdown",
    url="https://github.com/hydra-ecosystem/hydra/",
    packages=find_namespace_packages(include=["hydra_plugins.*"]),
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Development Status :: 4 - Beta",
    ],
    python_requires=">=3.10",
    install_requires=[
        "hydra-core>=1.1.0.dev7",
        "optuna>=4.9.0,<6.0.0",
    ],
    include_package_data=True,
)
