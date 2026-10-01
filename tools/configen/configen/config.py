# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from dataclasses import dataclass, field

from hydra.core.config_store import ConfigStore
from hydra.utils import ConvertMode
from omegaconf import MISSING


@dataclass
class Flags:
    _convert_: ConvertMode | None = None
    _recursive_: bool | None = None


@dataclass
class ModuleConf:
    name: str = MISSING
    classes: list[str] = MISSING
    default_flags: Flags = field(default_factory=Flags)


@dataclass
class ConfigenConf:
    # output dir
    output_dir: str = MISSING

    module_path_pattern: str = MISSING

    modules: list[ModuleConf] = MISSING

    # Generated file header
    header: str = MISSING


@dataclass
class Config:
    init_config_dir: str | None = None
    configen: ConfigenConf = field(default_factory=ConfigenConf)


config_store = ConfigStore.instance()
config_store.store(name="configen_schema", node=Config)
