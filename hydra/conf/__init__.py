# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from dataclasses import dataclass, field
from typing import Any

from omegaconf import MISSING

from hydra.core.config_store import ConfigStore
from hydra.types import RunMode


@dataclass
class HelpConf:
    app_name: str = MISSING
    header: str = MISSING
    footer: str = MISSING
    template: str = MISSING


@dataclass
class HydraHelpConf:
    hydra_help: str = MISSING
    template: str = MISSING


@dataclass
class RunDir:
    dir: str = MISSING


@dataclass
class SweepDir:
    dir: str = MISSING
    subdir: str = MISSING


@dataclass
class OverridesConf:
    # Overrides for the hydra configuration
    hydra: list[str] = field(default_factory=lambda: [])
    # Overrides for the task configuration
    task: list[str] = field(default_factory=lambda: [])


@dataclass
class OverrideConf:
    aliases: dict[str, str] = field(default_factory=dict)


# job runtime information will be populated here
@dataclass
class JobConf:
    # Job name, populated automatically unless specified by the user (in config or cli)
    name: str = MISSING

    # Change current working dir to the output dir.
    chdir: bool = False

    # Deprecated. Use the hydra_override_dirname resolver instead.
    override_dirname: str = "${hydra_override_dirname:}"

    # Job ID in underlying scheduling system
    id: str = MISSING

    # Job number if job is a part of a sweep
    num: int = MISSING

    # The config name used by the job
    config_name: str | None = MISSING

    # Environment variables to set remotely
    env_set: dict[str, str] = field(default_factory=dict)
    # Environment variables to copy from the launching machine
    env_copy: list[str] = field(default_factory=list)

    # Job config
    @dataclass
    class JobConfig:
        @dataclass
        # Default configuration for the ${hydra_override_dirname:} resolver.
        class OverrideDirname:
            kv_sep: str = "="
            item_sep: str = ","
            exclude_keys: list[str] = field(default_factory=list)

        override_dirname: OverrideDirname = field(default_factory=OverrideDirname)

    config: JobConfig = field(default_factory=JobConfig)


@dataclass
class ConfigSourceInfo:
    path: str
    schema: str
    provider: str


@dataclass
class RuntimeConf:
    version: str = MISSING
    version_base: str = MISSING
    cwd: str = MISSING
    config_sources: list[ConfigSourceInfo] = MISSING
    output_dir: str = MISSING

    # Composition choices dictionary
    # Ideally, the value type would be Union[str, List[str], None]
    choices: dict[str, Any] = field(default_factory=lambda: {})


@dataclass
class HydraConf:
    defaults: list[Any] = field(
        default_factory=lambda: [
            {"output": "default"},
            {"launcher": "basic"},
            {"sweeper": "basic"},
            {"help": "default"},
            {"hydra_help": "default"},
            {"hydra_logging": "default"},
            {"job_logging": "default"},
            {"callbacks": None},
            # env specific overrides
            {"env": "default"},
        ]
    )

    mode: RunMode | None = None
    # Elements to append to the config search path.
    # Note: This can only be configured in the primary config.
    searchpath: list[str] = field(default_factory=list)

    # Normal run output configuration
    run: RunDir = field(default_factory=RunDir)
    # Multi-run output configuration
    sweep: SweepDir = field(default_factory=SweepDir)
    # Logging configuration for Hydra
    hydra_logging: dict[str, Any] = MISSING
    # Logging configuration for the job
    job_logging: dict[str, Any] = MISSING

    # Sweeper configuration
    sweeper: Any = MISSING
    # Launcher configuration
    launcher: Any = MISSING
    # Callbacks configuration
    callbacks: dict[str, Any] = field(default_factory=dict)

    # Program Help template
    help: HelpConf = field(default_factory=HelpConf)
    # Hydra's Help template
    hydra_help: HydraHelpConf = field(default_factory=HydraHelpConf)

    # Output directory for produced configuration files and overrides.
    # E.g., hydra.yaml, overrides.yaml will go here. Useful for debugging
    # and extra context when looking at past runs.
    # Setting to None will prevent the creation of the output subdir.
    output_subdir: str | None = ".hydra"

    # Those lists will contain runtime overrides
    override: OverrideConf = field(default_factory=OverrideConf)
    overrides: OverridesConf = field(default_factory=OverridesConf)

    job: JobConf = field(default_factory=JobConf)

    # populated at runtime
    runtime: RuntimeConf = field(default_factory=RuntimeConf)

    # Can be a boolean, string or a list of strings
    # If a boolean, setting to true will set the log level for the root logger to debug
    # If a string, it's interpreted as a the list [string]
    # If a list, each element is interpreted as a logger to have logging level set to debug.
    # Typical command lines to manipulate hydra.verbose:
    # hydra.verbose=true
    # hydra.verbose=[hydra,__main__]
    # TODO: good use case for Union support in OmegaConf
    verbose: Any = False


cs = ConfigStore.instance()

cs.store(
    group="hydra",
    name="config",
    node=HydraConf(),
    provider="hydra",
)
