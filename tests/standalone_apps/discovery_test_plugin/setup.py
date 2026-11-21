# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from setuptools import find_namespace_packages, setup

setup(
    name="hydra-discovery-test-plugin",
    version="0.1.0",
    author="Omry Yadan",
    author_email="omry@yadan.net",
    url="https://github.com/hydra-ecosystem/hydra/",
    packages=find_namespace_packages(include=["hydra_plugins.*"]),
    entry_points={
        "hydra.plugins": [
            "discovery_test = hydra_plugins.discovery_test.discovery_test:DiscoveryTestPlugin",
            "not_hidden_test = hydra_plugins.discovery_test.__not_hidden_plugin:NotHiddenTestPlugin",
        ]
    },
    install_requires=["hydra-core"],
)
