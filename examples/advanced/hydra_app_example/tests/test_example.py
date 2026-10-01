# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import unittest

from pytest import mark

import hydra_app.main
from hydra import compose, initialize, initialize_config_module


# 1. initialize will add config_path the config search path within the context
# 2. The module with your configs should be importable. it needs to have a __init__.py (can be empty).
# 3. The config path is relative to the file calling initialize (this file)
def test_with_initialize() -> None:
    with initialize(config_path="../hydra_app/conf"):
        # config is relative to a module
        cfg = compose(config_name="config", overrides=["app.user=test_user"])
        assert cfg == {
            "app": {"user": "test_user", "num1": 10, "num2": 20},
            "db": {"host": "localhost", "port": 3306},
        }


# 1. initialize_with_module will add the config module to the config search path within the context
# 2. The module with your configs should be importable. it needs to have a __init__.py (can be empty).
# 3. The module should be absolute
# 4. This approach is not sensitive to the location of this file, the test can be relocated freely.
def test_with_initialize_config_module() -> None:
    with initialize_config_module(config_module="hydra_app.conf"):
        # config is relative to a module
        cfg = compose(config_name="config", overrides=["app.user=test_user"])
        assert cfg == {
            "app": {"user": "test_user", "num1": 10, "num2": 20},
            "db": {"host": "localhost", "port": 3306},
        }


# Usage in unittest style tests is similar.
class TestWithUnittest(unittest.TestCase):
    def test_generated_config(self) -> None:
        with initialize_config_module(config_module="hydra_app.conf"):
            cfg = compose(config_name="config", overrides=["app.user=test_user"])
            assert cfg == {
                "app": {"user": "test_user", "num1": 10, "num2": 20},
                "db": {"host": "localhost", "port": 3306},
            }


# This example drives some user logic with the composed config.
# In this case it calls hydra_app.main.add(), passing it the composed config.
@mark.parametrize(
    "overrides, expected",
    [
        (["app.user=test_user"], 30),
        (["app.user=test_user", "app.num1=20", "app.num2=100"], 120),
        (["app.user=test_user", "app.num1=-1001", "app.num2=1000"], -1),
    ],
)
def test_user_logic(overrides: list[str], expected: int) -> None:
    with initialize_config_module(config_module="hydra_app.conf"):
        cfg = compose(config_name="config", overrides=overrides)
        assert hydra_app.main.add(cfg.app, "num1", "num2") == expected
