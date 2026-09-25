# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import copy
import os
import sys
import warnings
from textwrap import dedent
from typing import Any, List, MutableSequence, Optional, Tuple, Union

from omegaconf import (
    Container,
    DictConfig,
    ListConfig,
    OmegaConf,
    flag_override,
    open_dict,
)
from omegaconf.errors import (
    ConfigAttributeError,
    ConfigKeyError,
    MissingMandatoryValue,
    OmegaConfBaseException,
)

from hydra._internal.config_repository import (
    CachingConfigRepository,
    ConfigRepository,
    IConfigRepository,
)
from hydra._internal.defaults_list import DefaultsList, create_defaults_list
from hydra.conf import ConfigSourceInfo
from hydra.core.config_loader import ConfigLoader
from hydra.core.config_search_path import ConfigSearchPath
from hydra.core.default_element import ResultDefault
from hydra.core.object_type import ObjectType
from hydra.core.override_parser.overrides_parser import OverridesParser
from hydra.core.override_parser.types import Override, ValueType
from hydra.core.utils import JobRuntime
from hydra.errors import ConfigCompositionException, MissingConfigException
from hydra.plugins.config_source import ConfigResult, ConfigSource
from hydra.types import RunMode


class ConfigLoaderImpl(ConfigLoader):
    """
    Configuration loader
    """

    def __init__(
        self,
        config_search_path: ConfigSearchPath,
    ) -> None:
        self.config_search_path = config_search_path
        self.repository = ConfigRepository(config_search_path=config_search_path)
        self._active_repository: Optional[IConfigRepository] = None

    @staticmethod
    def validate_sweep_overrides_legal(
        overrides: List[Override],
        run_mode: RunMode,
        from_shell: bool,
    ) -> None:
        for x in overrides:
            if x.is_sweep_override():
                if run_mode == RunMode.MULTIRUN:
                    if x.is_hydra_override():
                        raise ConfigCompositionException(
                            "Sweeping over Hydra's configuration is not supported :"
                            f" '{x.input_line}'"
                        )
                elif run_mode == RunMode.RUN:
                    if x.value_type == ValueType.SIMPLE_CHOICE_SWEEP:
                        vals = "value1,value2"
                        if from_shell:
                            example_override = f"key=\\'{vals}\\'"
                        else:
                            example_override = f"key='{vals}'"

                        msg = dedent(f"""\
                            Ambiguous value for argument '{x.input_line}'
                            1. To use it as a list, use key=[value1,value2]
                            2. To use it as string, quote the value: {example_override}
                            3. To sweep over it, add --multirun to your command line""")
                        raise ConfigCompositionException(msg)
                    else:
                        raise ConfigCompositionException(
                            f"Sweep parameters '{x.input_line}' requires --multirun"
                        )
                else:
                    assert False

    def _missing_config_error(
        self, config_name: Optional[str], msg: str, with_search_path: bool
    ) -> None:
        def add_search_path() -> str:
            descs = []
            for src in self.repository.get_sources():
                if src.provider != "schema":
                    descs.append(f"\t{repr(src)}")
            lines = "\n".join(descs)

            if with_search_path:
                return msg + "\nSearch path:" + f"\n{lines}"
            else:
                return msg

        raise MissingConfigException(
            missing_cfg_file=config_name, message=add_search_path()
        )

    def ensure_main_config_source_available(self) -> None:
        for source in self.get_sources():
            # if specified, make sure main config search path exists
            if source.provider == "main":
                if not source.available():
                    if source.scheme() == "pkg":
                        if source.path == "":
                            msg = (
                                "Primary config module is empty.\nPython requires"
                                " resources to be in a module with an __init__.py file"
                            )
                        else:
                            msg = (
                                f"Primary config module '{source.path}' not"
                                " found.\nCheck that it's correct and contains an"
                                " __init__.py file"
                            )
                    else:
                        msg = (
                            "Primary config directory not found.\nCheck that the"
                            f" config directory '{source.path}' exists and readable"
                        )

                    self._missing_config_error(
                        config_name=None, msg=msg, with_search_path=False
                    )

    def load_configuration(
        self,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode,
        from_shell: bool = True,
        validate_sweep_overrides: bool = True,
        skip_missing_defaults: bool = False,
    ) -> DictConfig:
        return self._load_configuration(
            config_name=config_name,
            overrides=overrides,
            run_mode=run_mode,
            from_shell=from_shell,
            validate_sweep_overrides=validate_sweep_overrides,
            skip_missing_defaults=skip_missing_defaults,
            activate_config_repository=False,
        )

    def _load_configuration_with_active_repository(
        self,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode,
        from_shell: bool = True,
        validate_sweep_overrides: bool = True,
    ) -> DictConfig:
        return self._load_configuration(
            config_name=config_name,
            overrides=overrides,
            run_mode=run_mode,
            from_shell=from_shell,
            validate_sweep_overrides=validate_sweep_overrides,
            skip_missing_defaults=False,
            activate_config_repository=True,
        )

    def _load_configuration(
        self,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode,
        from_shell: bool,
        validate_sweep_overrides: bool,
        skip_missing_defaults: bool,
        activate_config_repository: bool,
    ) -> DictConfig:
        try:
            return self._load_configuration_impl(
                config_name=config_name,
                overrides=overrides,
                run_mode=run_mode,
                from_shell=from_shell,
                validate_sweep_overrides=validate_sweep_overrides,
                skip_missing_defaults=skip_missing_defaults,
                activate_config_repository=activate_config_repository,
            )
        except OmegaConfBaseException as e:
            raise ConfigCompositionException().with_traceback(sys.exc_info()[2]) from e

    def _process_config_searchpath(
        self,
        config_name: Optional[str],
        parsed_overrides: List[Override],
        repo: CachingConfigRepository,
    ) -> None:
        if config_name is not None:
            loaded = repo.load_config(config_path=config_name)
            primary_config: Container
            if loaded is None:
                primary_config = OmegaConf.create()
            else:
                primary_config = loaded.config
        else:
            primary_config = OmegaConf.create()

        if not OmegaConf.is_dict(primary_config):
            raise ConfigCompositionException(
                f"primary config '{config_name}' must be a DictConfig, got"
                f" {type(primary_config).__name__}"
            )

        def is_searchpath_override(v: Override) -> bool:
            return v.get_key_element() == "hydra.searchpath"

        override = None
        for v in parsed_overrides:
            if is_searchpath_override(v):
                override = v.value()
                break

        searchpath = OmegaConf.select(primary_config, "hydra.searchpath")
        if override is not None:
            provider = "hydra.searchpath in command-line"
            searchpath = override
        else:
            provider = "hydra.searchpath in main"

        def _err() -> None:
            raise ConfigCompositionException(
                f"hydra.searchpath must be a list of strings. Got: {searchpath}"
            )

        if searchpath is None:
            return

        # validate hydra.searchpath.
        # Note that we cannot rely on OmegaConf validation here because we did not yet merge with the Hydra schema node
        if not isinstance(searchpath, MutableSequence):
            _err()
        for v in searchpath:
            if not isinstance(v, str):
                _err()

        new_csp = copy.deepcopy(self.config_search_path)
        schema = new_csp.get_path().pop(-1)
        assert schema.provider == "schema"
        for sp in searchpath:
            new_csp.append(provider=provider, path=sp)
        new_csp.append("schema", "structured://")
        repo.initialize_sources(new_csp)

        for source in repo.get_sources():
            if not source.available():
                warnings.warn(
                    category=UserWarning,
                    message=(
                        f"provider={source.provider}, path={source.path} is not"
                        " available."
                    ),
                )

    def _parse_overrides_and_create_caching_repo(
        self, config_name: Optional[str], overrides: List[str]
    ) -> Tuple[List[Override], CachingConfigRepository]:
        parser = OverridesParser.create()
        parsed_overrides = parser.parse_overrides(overrides=overrides)
        caching_repo = CachingConfigRepository(self.repository)
        self._process_config_searchpath(config_name, parsed_overrides, caching_repo)
        return parsed_overrides, caching_repo

    def _load_configuration_impl(
        self,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode,
        from_shell: bool = True,
        validate_sweep_overrides: bool = True,
        skip_missing_defaults: bool = False,
        activate_config_repository: bool = False,
    ) -> DictConfig:
        from hydra import __version__, version

        self.ensure_main_config_source_available()
        parsed_overrides, caching_repo = self._parse_overrides_and_create_caching_repo(
            config_name, overrides
        )

        if validate_sweep_overrides:
            self.validate_sweep_overrides_legal(
                overrides=parsed_overrides, run_mode=run_mode, from_shell=from_shell
            )

        defaults_list = create_defaults_list(
            repo=caching_repo,
            config_name=config_name,
            overrides_list=parsed_overrides,
            prepend_hydra=True,
            skip_missing=skip_missing_defaults or run_mode == RunMode.MULTIRUN,
        )

        config_overrides = defaults_list.config_overrides

        cfg = self._compose_config_from_defaults_list(
            defaults=defaults_list.defaults, repo=caching_repo
        )

        # Set config root to struct mode.
        # Note that this will close any dictionaries (including dicts annotated as Dict[K, V].
        # One must use + to add new fields to them.
        OmegaConf.set_struct(cfg, True)

        # The Hydra node should not be read-only even if the root config is read-only.
        OmegaConf.set_readonly(cfg.hydra, False)

        # Apply command line overrides after enabling struct mode
        ConfigLoaderImpl._apply_overrides_to_config(config_overrides, cfg)
        for override in parsed_overrides:
            if override.is_hydra_override():
                cfg.hydra.overrides.hydra.append(override.input_line)
            else:
                cfg.hydra.overrides.task.append(override.input_line)

        with open_dict(cfg.hydra):
            cfg.hydra.runtime.choices.update(defaults_list.overrides.known_choices)
            for key in cfg.hydra.job.env_copy:
                cfg.hydra.job.env_set[key] = os.environ[key]

        cfg.hydra.runtime.version = __version__
        cfg.hydra.runtime.version_base = version.getbase()
        cfg.hydra.runtime.cwd = os.getcwd()

        cfg.hydra.runtime.config_sources = [
            ConfigSourceInfo(path=x.path, schema=x.scheme(), provider=x.provider)
            for x in caching_repo.get_sources()
        ]

        if "name" not in cfg.hydra.job:
            cfg.hydra.job.name = JobRuntime().get("name")

        cfg.hydra.job.config_name = config_name

        if activate_config_repository:
            self._active_repository = caching_repo

        return cfg

    def load_sweep_config(
        self, master_config: DictConfig, sweep_overrides: List[str]
    ) -> DictConfig:
        # Recreate the config for this sweep instance with the appropriate overrides
        overrides = OmegaConf.to_container(master_config.hydra.overrides.hydra)
        assert isinstance(overrides, list)
        overrides = overrides + sweep_overrides
        sweep_config = self.load_configuration(
            config_name=master_config.hydra.job.config_name,
            overrides=overrides,
            run_mode=RunMode.RUN,
        )
        ConfigLoaderImpl._ensure_sweep_config_controller_unchanged(
            master_config=master_config,
            sweep_config=sweep_config,
        )

        # Copy old config cache to ensure we get the same resolved values (for things
        # like timestamps etc). Since `oc.env` does not cache environment variables
        # (but the deprecated `env` resolver did), the entire config should be copied
        OmegaConf.copy_cache(from_config=master_config, to_config=sweep_config)

        return sweep_config

    @staticmethod
    def _ensure_sweep_config_controller_unchanged(
        master_config: DictConfig, sweep_config: DictConfig
    ) -> None:
        controller_groups = (
            ("hydra/launcher", "launcher"),
            ("hydra/sweeper", "sweeper"),
        )
        master_choices = master_config.hydra.runtime.choices
        sweep_choices = sweep_config.hydra.runtime.choices
        for group, node in controller_groups:
            master_choice = master_choices.get(group)
            sweep_choice = sweep_choices.get(group)
            if master_choice != sweep_choice:
                # Bandit mistakes this user-facing message for a SQL snippet.
                raise ConfigCompositionException(
                    f"'{group}' must be selected before the sweep starts, "  # nosec B608
                    f"but a swept job config changed it from "
                    f"'{master_choice}' to '{sweep_choice}'. Select it in "
                    "the primary config or from the command line."
                )
            if not OmegaConf.structural_equality(
                master_config.hydra[node], sweep_config.hydra[node]
            ):
                raise ConfigCompositionException(
                    f"'hydra.{node}' must be configured before the sweep starts, "
                    "but a swept job config changed it. Configure it in the "
                    "primary config or from the command line."
                )

    def get_search_path(self) -> ConfigSearchPath:
        return self.config_search_path

    @staticmethod
    def _apply_overrides_to_config(overrides: List[Override], cfg: DictConfig) -> None:
        for override in overrides:
            if override.package is not None:
                raise ConfigCompositionException(
                    f"Override {override.input_line} looks like a config group"
                    f" override, but config group '{override.key_or_group}' does not"
                    " exist."
                )

            key = override.key_or_group
            value = override.value()
            try:
                if override.is_delete():
                    config_val_not_found = object()
                    config_val_missing = object()
                    last_dot = key.rfind(".")
                    parent: Container = cfg
                    parent_missing = False
                    if last_dot != -1:
                        parent_key = key[0:last_dot]
                        selected_parent = OmegaConf.select(
                            cfg,
                            parent_key,
                            default=config_val_not_found,
                            throw_on_missing=False,
                        )
                        if isinstance(selected_parent, Container):
                            parent = selected_parent
                        else:
                            parent_missing = True

                    try:
                        config_val = OmegaConf.select(
                            cfg,
                            key,
                            default=config_val_not_found,
                            throw_on_missing=True,
                        )
                    except MissingMandatoryValue:
                        config_val = config_val_missing

                    if parent_missing or config_val is config_val_not_found:
                        # Bandit mistakes this user-facing message for a SQL snippet.
                        raise ConfigCompositionException(
                            f"Could not delete from config. '{override.key_or_group}'"  # nosec B608
                            " does not exist."
                        )
                    config_val_for_match = (
                        "???" if config_val is config_val_missing else config_val
                    )
                    if (
                        override.value_type is not None
                        and value != config_val_for_match
                    ):
                        # Bandit mistakes this user-facing message for a SQL snippet.
                        raise ConfigCompositionException(
                            "Could not delete from config. The value of"  # nosec B608
                            f" '{override.key_or_group}' is {config_val_for_match} and not"
                            f" {value}."
                        )

                    with open_dict(cfg):
                        if last_dot == -1:
                            del cfg[key]
                        else:
                            node_key: Union[str, int] = key[last_dot + 1 :]
                            if isinstance(parent, ListConfig):
                                node_key = int(node_key)
                            del parent[node_key]

                elif override.is_add():
                    if OmegaConf.select(
                        cfg, key, throw_on_missing=False
                    ) is None or isinstance(value, (dict, list)):
                        OmegaConf.update(cfg, key, value, merge=True, force_add=True)
                    else:
                        assert override.input_line is not None
                        raise ConfigCompositionException(
                            dedent(f"""\
                        Could not append to config. An item is already at '{override.key_or_group}'.
                        Either remove + prefix: '{override.input_line[1:]}'
                        Or add a second + to add or override '{override.key_or_group}': '+{override.input_line}'
                        """)
                        )
                elif override.is_force_add():
                    OmegaConf.update(cfg, key, value, merge=True, force_add=True)
                elif override.is_list_extend():
                    config_val = OmegaConf.select(cfg, key, throw_on_missing=True)
                    if not OmegaConf.is_list(config_val):
                        raise ConfigCompositionException(
                            "Could not append to config list. The existing value of"
                            f" '{override.key_or_group}' is {config_val} which is not"
                            f" a list."
                        )
                    config_val.extend(value)
                else:
                    try:
                        OmegaConf.update(cfg, key, value, merge=True)
                    except (ConfigAttributeError, ConfigKeyError) as ex:
                        raise ConfigCompositionException(
                            f"Could not override '{override.key_or_group}'."
                            f"\nTo append to your config use +{override.input_line}"
                        ) from ex
            except OmegaConfBaseException as ex:
                raise ConfigCompositionException(
                    f"Error merging override {override.input_line}"
                ).with_traceback(sys.exc_info()[2]) from ex

    def _load_single_config(
        self, default: ResultDefault, repo: IConfigRepository
    ) -> ConfigResult:
        config_path = default.config_path

        assert config_path is not None
        ret = repo.load_config(config_path=config_path)
        assert ret is not None

        if not OmegaConf.is_config(ret.config):
            raise ValueError(
                f"Config {config_path} must be an OmegaConf config, got"
                f" {type(ret.config).__name__}"
            )

        res = self._embed_result_config(ret, default.package)
        if (
            not default.primary
            and config_path != "hydra/config"
            and isinstance(res.config, DictConfig)
            and OmegaConf.select(res.config, "hydra.searchpath") is not None
        ):
            raise ConfigCompositionException(
                f"In '{config_path}': Overriding hydra.searchpath is only supported"
                " from the primary config"
            )

        return res

    @staticmethod
    def _embed_result_config(
        ret: ConfigResult, package_override: Optional[str]
    ) -> ConfigResult:
        package = ret.header["package"]
        if package_override is not None:
            package = package_override

        if package is not None and package != "":
            cfg = OmegaConf.create()
            OmegaConf.update(cfg, package, ret.config, merge=False)
            ret = copy.copy(ret)
            ret.config = cfg

        return ret

    def list_groups(self, parent_name: str) -> List[str]:
        return self.get_group_options(
            group_name=parent_name, results_filter=ObjectType.GROUP
        )

    def get_group_options(
        self,
        group_name: str,
        results_filter: Optional[ObjectType] = ObjectType.CONFIG,
        config_name: Optional[str] = None,
        overrides: Optional[List[str]] = None,
    ) -> List[str]:
        if (
            config_name is None
            and overrides is None
            and self._active_repository is not None
        ):
            return self._active_repository.get_group_options(group_name, results_filter)
        if overrides is None:
            overrides = []
        _, caching_repo = self._parse_overrides_and_create_caching_repo(
            config_name, overrides
        )
        return caching_repo.get_group_options(group_name, results_filter)

    def _compose_config_from_defaults_list(
        self,
        defaults: List[ResultDefault],
        repo: IConfigRepository,
    ) -> DictConfig:
        cfg = OmegaConf.create()
        with flag_override(cfg, "no_deepcopy_set_nodes", True):
            for default in defaults:
                loaded = self._load_single_config(default=default, repo=repo)
                try:
                    cfg.merge_with(loaded.config)
                except OmegaConfBaseException as e:
                    raise ConfigCompositionException(
                        f"In '{default.config_path}': {type(e).__name__} raised while"
                        f" composing config:\n{e}"
                    ).with_traceback(sys.exc_info()[2])

        # # remove remaining defaults lists from all nodes.
        def strip_defaults(cfg: Any) -> None:
            if isinstance(cfg, DictConfig):
                if cfg._is_missing() or cfg._is_none():
                    return
                with flag_override(cfg, ["readonly", "struct"], False):
                    if cfg._get_flag("HYDRA_REMOVE_TOP_LEVEL_DEFAULTS"):
                        cfg._set_flag("HYDRA_REMOVE_TOP_LEVEL_DEFAULTS", None)
                        cfg.pop("defaults", None)

                for _key, value in cfg.items_ex(resolve=False):
                    strip_defaults(value)

        strip_defaults(cfg)

        return cfg

    def get_sources(self) -> List[ConfigSource]:
        if self._active_repository is not None:
            return self._active_repository.get_sources()
        return self.repository.get_sources()

    def compute_defaults_list(
        self,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode,
    ) -> DefaultsList:
        parsed_overrides, caching_repo = self._parse_overrides_and_create_caching_repo(
            config_name, overrides
        )
        defaults_list = create_defaults_list(
            repo=caching_repo,
            config_name=config_name,
            overrides_list=parsed_overrides,
            prepend_hydra=True,
            skip_missing=run_mode == RunMode.MULTIRUN,
        )
        return defaults_list
