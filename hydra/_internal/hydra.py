# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import copy
import logging
import string
import sys
from argparse import ArgumentParser
from collections import defaultdict
from typing import Any, Callable, DefaultDict, List, Optional, Sequence, Type, Union

from omegaconf import (
    MISSING,
    Container,
    DictConfig,
    ListConfig,
    OmegaConf,
    flag_override,
)
from omegaconf.errors import InterpolationToMissingValueError

from hydra._internal.target_policy import _get_active_target_whitelist
from hydra._internal.utils import get_column_widths, run_and_report
from hydra.core.config_loader import ConfigLoader
from hydra.core.config_search_path import ConfigSearchPath
from hydra.core.hydra_config import HydraConfig
from hydra.core.plugins import Plugins
from hydra.core.utils import (
    JobReturn,
    JobRuntime,
    JobStatus,
    configure_log,
    run_job,
    setup_globals,
    simple_stdout_log_config,
)
from hydra.plugins.completion_plugin import CompletionPlugin
from hydra.plugins.config_source import ConfigSource
from hydra.plugins.launcher import Launcher
from hydra.plugins.search_path_plugin import SearchPathPlugin
from hydra.plugins.sweeper import Sweeper
from hydra.types import HydraContext, RunMode, TaskFunction

from ..core.default_element import DefaultsTreeNode, InputDefault
from .callbacks import Callbacks
from .config_loader_impl import ConfigLoaderImpl
from .utils import create_automatic_config_search_path

log: Optional[logging.Logger] = None


def _resolve_node_interpolations(cfg: Any) -> None:
    if cfg._is_missing() or cfg._is_none():
        return

    if isinstance(cfg, DictConfig):
        keys: Sequence[Any] = list(cfg.keys())
    else:
        assert isinstance(cfg, ListConfig)
        keys = range(len(cfg))

    for key in keys:
        if OmegaConf.is_missing(cfg, key):
            continue

        node = cfg._get_node(key)
        if isinstance(node, Container):
            _resolve_node_interpolations(node)
            continue

        try:
            cfg[key] = cfg[key]
        except InterpolationToMissingValueError:
            cfg[key] = MISSING


def _resolve_for_cfg_output(cfg: Container) -> None:
    try:
        OmegaConf.resolve(cfg)
    except InterpolationToMissingValueError:
        with flag_override(cfg, ["readonly", "struct"], False):
            _resolve_node_interpolations(cfg)


class Hydra:
    @classmethod
    def create_main_hydra_file_or_module(
        cls: Type["Hydra"],
        calling_file: Optional[str],
        calling_module: Optional[str],
        config_path: Optional[str],
        job_name: str,
    ) -> "Hydra":
        config_search_path = create_automatic_config_search_path(
            calling_file, calling_module, config_path
        )

        return Hydra.create_main_hydra2(job_name, config_search_path)

    @classmethod
    def create_main_hydra2(
        cls,
        task_name: str,
        config_search_path: ConfigSearchPath,
    ) -> "Hydra":
        config_loader: ConfigLoader = ConfigLoaderImpl(
            config_search_path=config_search_path
        )

        hydra = cls(task_name=task_name, config_loader=config_loader)
        from hydra.core.global_hydra import GlobalHydra

        GlobalHydra.instance().initialize(hydra)
        return hydra

    def __init__(self, task_name: str, config_loader: ConfigLoader) -> None:
        """
        :param task_name: task name
        :param config_loader: config loader
        """
        setup_globals()

        self.config_loader = config_loader
        JobRuntime().set("name", task_name)

    def get_mode(
        self,
        config_name: Optional[str],
        overrides: List[str],
    ) -> Any:
        try:
            cfg = self.compose_config(
                config_name=config_name,
                overrides=overrides,
                with_log_configuration=False,
                run_mode=RunMode.MULTIRUN,
                validate_sweep_overrides=False,
            )
            return cfg.hydra.mode
        except Exception:
            return None

    def run(
        self,
        config_name: Optional[str],
        task_function: TaskFunction,
        overrides: List[str],
        with_log_configuration: bool = True,
    ) -> JobReturn:
        cfg = self.compose_config(
            config_name=config_name,
            overrides=overrides,
            with_log_configuration=with_log_configuration,
            run_mode=RunMode.RUN,
            activate_config_repository=True,
        )
        if cfg.hydra.mode is None:
            cfg.hydra.mode = RunMode.RUN
        else:
            assert cfg.hydra.mode == RunMode.RUN

        callbacks = Callbacks(cfg)
        callbacks.on_run_start(config=cfg, config_name=config_name)

        try:
            ret = run_job(
                hydra_context=HydraContext(
                    config_loader=self.config_loader,
                    callbacks=callbacks,
                    target_whitelist=_get_active_target_whitelist(),
                ),
                task_function=task_function,
                config=cfg,
                job_dir_key="hydra.run.dir",
                job_subdir_key=None,
                configure_logging=with_log_configuration,
            )
        except KeyboardInterrupt as e:
            # run_job attaches its populated JobReturn to the interrupt before
            # re-raising; fall back to a minimal one if the interrupt happened
            # before the job ran (e.g. during on_job_start)
            job_return = getattr(e, "job_return", None)
            if not isinstance(job_return, JobReturn):
                job_return = JobReturn()
                job_return.status = JobStatus.FAILED
                job_return.return_value = e
            callbacks.on_run_end(
                config=cfg, config_name=config_name, job_return=job_return
            )
            raise
        callbacks.on_run_end(config=cfg, config_name=config_name, job_return=ret)

        # access the result to trigger an exception in case the job failed.
        _ = ret.return_value

        return ret

    def multirun(
        self,
        config_name: Optional[str],
        task_function: TaskFunction,
        overrides: List[str],
        with_log_configuration: bool = True,
    ) -> Any:
        cfg = self.compose_config(
            config_name=config_name,
            overrides=overrides,
            with_log_configuration=with_log_configuration,
            run_mode=RunMode.MULTIRUN,
            activate_config_repository=True,
        )

        callbacks = Callbacks(cfg)
        callbacks.on_multirun_start(config=cfg, config_name=config_name)

        sweeper = Plugins.instance().instantiate_sweeper(
            config=cfg,
            hydra_context=HydraContext(
                config_loader=self.config_loader,
                callbacks=callbacks,
                target_whitelist=_get_active_target_whitelist(),
            ),
            task_function=task_function,
        )
        task_overrides = OmegaConf.to_container(cfg.hydra.overrides.task, resolve=False)
        assert isinstance(task_overrides, list)
        ret = sweeper.sweep(arguments=task_overrides)
        callbacks.on_multirun_end(config=cfg, config_name=config_name)
        return ret

    @staticmethod
    def get_sanitized_hydra_cfg(src_cfg: DictConfig) -> DictConfig:
        cfg = copy.deepcopy(src_cfg)
        with flag_override(cfg, ["struct", "readonly"], [False, False]):
            for key in list(cfg.keys()):
                if key != "hydra":
                    del cfg[key]
        with flag_override(cfg.hydra, ["struct", "readonly"], False):
            del cfg.hydra["hydra_help"]
            del cfg.hydra["help"]
        return cfg

    def get_sanitized_cfg(self, cfg: DictConfig, cfg_type: str) -> DictConfig:
        assert cfg_type in ["job", "hydra", "all"]
        if cfg_type == "job":
            with flag_override(cfg, ["struct", "readonly"], [False, False]):
                del cfg["hydra"]
        elif cfg_type == "hydra":
            cfg = self.get_sanitized_hydra_cfg(cfg)
        return cfg

    def show_cfg(
        self,
        config_name: Optional[str],
        overrides: List[str],
        cfg_type: str,
        package: Optional[str],
        resolve: bool = False,
    ) -> None:
        cfg = self.compose_config(
            config_name=config_name,
            overrides=overrides,
            run_mode=RunMode.RUN,
            with_log_configuration=False,
        )
        HydraConfig.instance().set_config(cfg)
        OmegaConf.set_readonly(cfg.hydra, None)
        cfg = self.get_sanitized_cfg(cfg, cfg_type)
        if package == "_global_":
            package = None

        if package is None:
            ret = cfg
        else:
            ret = OmegaConf.select(cfg, package)
            if ret is None:
                sys.stderr.write(f"package '{package}' not found in config\n")
                sys.exit(1)

        if not isinstance(ret, Container):
            print(ret)
        else:
            if package is not None:
                print(f"# @package {package}")
            if resolve:
                _resolve_for_cfg_output(ret)
            sys.stdout.write(OmegaConf.to_yaml(ret))

    @staticmethod
    def get_shell_to_plugin_map(
        config_loader: ConfigLoader,
    ) -> DefaultDict[str, List[CompletionPlugin]]:
        shell_to_plugin: DefaultDict[str, List[CompletionPlugin]] = defaultdict(list)
        for clazz in Plugins.instance().discover(CompletionPlugin):
            assert issubclass(clazz, CompletionPlugin)
            plugin = clazz(config_loader)
            shell_to_plugin[plugin.provides()].append(plugin)

        for shell, plugins in shell_to_plugin.items():
            if len(plugins) > 1:
                lst = ",".join(type(plugin).__name__ for plugin in plugins)
                raise ValueError(f"Multiple plugins installed for {shell} : {lst}")

        return shell_to_plugin

    def shell_completion(
        self, config_name: Optional[str], overrides: List[str]
    ) -> None:
        subcommands = ["install", "uninstall", "query"]
        arguments = OmegaConf.from_dotlist(overrides)
        num_commands = sum(1 for key in subcommands if key in arguments)
        if num_commands != 1:
            raise ValueError(f"Expecting one subcommand from {subcommands} to be set")

        shell_to_plugin = self.get_shell_to_plugin_map(self.config_loader)

        def find_plugin(cmd: str) -> CompletionPlugin:
            if cmd not in shell_to_plugin:
                lst = "\n".join("\t" + x for x in shell_to_plugin.keys())
                raise ValueError(
                    f"No completion plugin for '{cmd}' found, available : \n{lst}"
                )
            return shell_to_plugin[cmd][0]

        if "install" in arguments:
            plugin = find_plugin(arguments.install)
            plugin.install()
        elif "uninstall" in arguments:
            plugin = find_plugin(arguments.uninstall)
            plugin.uninstall()
        elif "query" in arguments:
            plugin = find_plugin(arguments.query)
            plugin.query(config_name=config_name)

    @staticmethod
    def format_args_help(args_parser: ArgumentParser) -> str:
        s = ""
        overrides: Any = None
        for action in args_parser._actions:
            if len(action.option_strings) == 0:
                overrides = action
            else:
                s += f"{','.join(action.option_strings)} : {action.help}\n"
        overrides_help = overrides.help
        assert isinstance(overrides_help, str)
        s += "Overrides : " + overrides_help
        return s

    def list_all_config_groups(self, parent: str = "") -> Sequence[str]:
        from hydra.core.object_type import ObjectType

        groups: List[str] = []
        for group in self.config_loader.list_groups(parent):
            if parent == "":
                group_name = group
            else:
                group_name = f"{parent}/{group}"
            files = self.config_loader.get_group_options(group_name, ObjectType.CONFIG)
            dirs = self.config_loader.get_group_options(group_name, ObjectType.GROUP)
            if len(files) > 0:
                groups.append(group_name)
            if len(dirs) > 0:
                groups.extend(self.list_all_config_groups(group_name))
        return groups

    def format_config_groups(
        self, predicate: Callable[[str], bool], compact: bool = True
    ) -> str:
        groups = [x for x in self.list_all_config_groups() if predicate(x)]
        s = ""
        for group in sorted(groups):
            options = sorted(self.config_loader.get_group_options(group))
            if compact:
                items = ", ".join(options)
                line = f"{group}: {items}"
            else:
                items = "\n".join("  " + o for o in options)
                line = f"{group}:\n{items}"
            s += line + "\n"

        return s

    def get_help(
        self,
        help_cfg: DictConfig,
        cfg: DictConfig,
        args_parser: ArgumentParser,
        resolve: bool,
    ) -> str:
        s = string.Template(help_cfg.template)

        def is_hydra_group(x: str) -> bool:
            return x.startswith("hydra/") or x == "hydra"

        def is_not_hydra_group(x: str) -> bool:
            return not is_hydra_group(x)

        help_text = s.substitute(
            FLAGS_HELP=self.format_args_help(args_parser),
            HYDRA_CONFIG_GROUPS=self.format_config_groups(is_hydra_group),
            APP_CONFIG_GROUPS=self.format_config_groups(is_not_hydra_group),
            CONFIG=OmegaConf.to_yaml(cfg, resolve=resolve),
        )
        return help_text

    def hydra_help(
        self, config_name: Optional[str], args_parser: ArgumentParser, args: Any
    ) -> None:
        cfg = self.compose_config(
            config_name=None,
            overrides=args.overrides,
            run_mode=RunMode.RUN,
            with_log_configuration=True,
        )
        help_cfg = cfg.hydra.hydra_help
        cfg = self.get_sanitized_hydra_cfg(cfg)
        help_text = self.get_help(help_cfg, cfg, args_parser, resolve=False)
        print(help_text)

    def app_help(
        self, config_name: Optional[str], args_parser: ArgumentParser, args: Any
    ) -> None:
        cfg = self.compose_config(
            config_name=config_name,
            overrides=args.overrides,
            run_mode=RunMode.RUN,
            with_log_configuration=True,
        )
        HydraConfig.instance().set_config(cfg)
        help_cfg = cfg.hydra.help
        clean_cfg = copy.deepcopy(cfg)

        clean_cfg = self.get_sanitized_cfg(clean_cfg, "job")
        help_text = self.get_help(
            help_cfg, clean_cfg, args_parser, resolve=args.resolve
        )
        print(help_text)

    @staticmethod
    def _log_header(header: str, prefix: str = "", filler: str = "-") -> None:
        assert log is not None
        log.debug(prefix + header)
        log.debug(prefix + "".ljust(len(header), filler))

    @staticmethod
    def _log_footer(header: str, prefix: str = "", filler: str = "-") -> None:
        assert log is not None
        log.debug(prefix + "".ljust(len(header), filler))

    def _print_plugins(self) -> None:
        assert log is not None
        self._log_header(header="Installed Hydra Plugins", filler="*")
        all_plugins = {p.__name__ for p in Plugins.instance().discover()}
        for plugin_type in [
            ConfigSource,
            CompletionPlugin,
            Launcher,
            Sweeper,
            SearchPathPlugin,
        ]:
            # Mypy false positive?
            plugins = Plugins.instance().discover(plugin_type)  # type: ignore
            if len(plugins) > 0:
                Hydra._log_header(header=f"{plugin_type.__name__}:", prefix="\t")
                for plugin in plugins:
                    log.debug(f"\t\t{plugin.__name__}")
                    if plugin.__name__ in all_plugins:
                        all_plugins.remove(plugin.__name__)

        if len(all_plugins) > 0:
            Hydra._log_header(header="Generic plugins: ", prefix="\t")
            for plugin_name in all_plugins:
                log.debug(f"\t\t{plugin_name}")

    def _print_search_path(
        self,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode = RunMode.RUN,
    ) -> None:
        assert log is not None
        log.debug("")
        self._log_header(header="Config search path", filler="*")

        box: List[List[str]] = [["Provider", "Search path"]]

        cfg = self.compose_config(
            config_name=config_name,
            overrides=overrides,
            run_mode=run_mode,
            with_log_configuration=False,
        )
        HydraConfig.instance().set_config(cfg)
        cfg = self.get_sanitized_cfg(cfg, cfg_type="hydra")

        sources = cfg.hydra.runtime.config_sources

        for sp in sources:
            box.append([sp.provider, f"{sp.schema}://{sp.path}"])

        provider_pad, search_path_pad = get_column_widths(box)
        header = "| {} | {} |".format(
            "Provider".ljust(provider_pad), "Search path".ljust(search_path_pad)
        )
        self._log_header(header=header, filler="-")

        for source in sources:
            log.debug(
                "| {} | {} |".format(
                    source.provider.ljust(provider_pad),
                    f"{source.schema}://{source.path}".ljust(search_path_pad),
                )
            )
        self._log_footer(header=header, filler="-")

    def _print_plugins_profiling_info(self, top_n: int) -> None:
        assert log is not None
        stats = Plugins.instance().get_stats()
        if stats is None:
            return

        items = list(stats.modules_import_time.items())
        # hide anything that took less than 5ms
        filtered = filter(lambda x: x[1] > 0.0005, items)
        sorted_items = sorted(filtered, key=lambda x: x[1], reverse=True)

        top_n = max(len(sorted_items), top_n)
        box: List[List[str]] = [["Module", "Sec"]]

        for item in sorted_items[0:top_n]:
            box.append([item[0], f"{item[1]:.3f}"])
        padding = get_column_widths(box)

        log.debug("")
        self._log_header(header="Profiling information", filler="*")
        self._log_header(
            header=f"Total plugins scan time : {stats.total_time:.3f} seconds",
            filler="-",
        )

        header = f"| {box[0][0].ljust(padding[0])} | {box[0][1].ljust(padding[1])} |"
        self._log_header(header=header, filler="-")
        del box[0]

        for row in box:
            a = row[0].ljust(padding[0])
            b = row[1].ljust(padding[1])
            log.debug(f"| {a} | {b} |")

        self._log_footer(header=header, filler="-")

    def _print_config_info(
        self,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode = RunMode.RUN,
    ) -> None:
        assert log is not None
        self._print_search_path(
            config_name=config_name, overrides=overrides, run_mode=run_mode
        )
        self._print_defaults_tree(config_name=config_name, overrides=overrides)
        self._print_defaults_list(config_name=config_name, overrides=overrides)

        cfg = run_and_report(
            lambda: self.compose_config(
                config_name=config_name,
                overrides=overrides,
                run_mode=run_mode,
                with_log_configuration=False,
            )
        )
        HydraConfig.instance().set_config(cfg)
        self._log_header(header="Config", filler="*")
        with flag_override(cfg, ["struct", "readonly"], [False, False]):
            del cfg["hydra"]
        log.info(OmegaConf.to_yaml(cfg))

    def _print_defaults_list(
        self,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode = RunMode.RUN,
    ) -> None:
        assert log is not None
        defaults = self.config_loader.compute_defaults_list(
            config_name=config_name,
            overrides=overrides,
            run_mode=run_mode,
        )

        box: List[List[str]] = [
            [
                "Config path",
                "Package",
                "_self_",
                "Parent",
            ]
        ]
        for d in defaults.defaults:
            row = [
                d.config_path,
                d.package,
                "True" if d.is_self else "False",
                d.parent,
            ]
            row = [x if x is not None else "" for x in row]
            box.append(row)
        padding = get_column_widths(box)
        del box[0]
        log.debug("")
        self._log_header("Defaults List", filler="*")
        header = "| {} | {} | {} | {} | ".format(
            "Config path".ljust(padding[0]),
            "Package".ljust(padding[1]),
            "_self_".ljust(padding[2]),
            "Parent".ljust(padding[3]),
        )
        self._log_header(header=header, filler="-")

        for row in box:
            log.debug(
                "| {} | {} | {} | {} |".format(
                    row[0].ljust(padding[0]),
                    row[1].ljust(padding[1]),
                    row[2].ljust(padding[2]),
                    row[3].ljust(padding[3]),
                )
            )

        self._log_footer(header=header, filler="-")

    def _print_debug_info(
        self,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode = RunMode.RUN,
    ) -> None:
        assert log is not None
        if log.isEnabledFor(logging.DEBUG):
            self._print_all_info(config_name, overrides, run_mode)

    def compose_config(
        self,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode,
        with_log_configuration: bool = False,
        from_shell: bool = True,
        validate_sweep_overrides: bool = True,
        activate_config_repository: bool = False,
    ) -> DictConfig:
        """
        :param config_name:
        :param overrides:
        :param run_mode: compose config for run or for multirun?
        :param with_log_configuration: True to configure logging subsystem from the loaded config
        :param from_shell: True if the parameters are passed from the shell. used for more helpful error messages
        :param validate_sweep_overrides: True if sweep overrides should be validated
        :param activate_config_repository: True to retain the effective repository on the invocation loader
        :return:
        """

        if activate_config_repository and isinstance(
            self.config_loader, ConfigLoaderImpl
        ):
            cfg = self.config_loader._load_configuration_with_active_repository(
                config_name=config_name,
                overrides=overrides,
                run_mode=run_mode,
                from_shell=from_shell,
                validate_sweep_overrides=validate_sweep_overrides,
            )
        else:
            cfg = self.config_loader.load_configuration(
                config_name=config_name,
                overrides=overrides,
                run_mode=run_mode,
                from_shell=from_shell,
                validate_sweep_overrides=validate_sweep_overrides,
            )
        if with_log_configuration:
            configure_log(cfg.hydra.hydra_logging, cfg.hydra.verbose)
            global log
            log = logging.getLogger(__name__)
            self._print_debug_info(config_name, overrides, run_mode)
        return cfg

    def _print_plugins_info(
        self,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode = RunMode.RUN,
    ) -> None:
        self._print_plugins()
        self._print_plugins_profiling_info(top_n=10)

    def _print_all_info(
        self,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode = RunMode.RUN,
    ) -> None:
        from .. import __version__

        self._log_header(f"Hydra {__version__}", filler="=")
        self._print_plugins()
        self._print_config_info(config_name, overrides, run_mode)

    def _print_defaults_tree_impl(
        self,
        tree: Union[DefaultsTreeNode, InputDefault],
        indent: int = 0,
    ) -> None:
        assert log is not None
        from ..core.default_element import GroupDefault, InputDefault, VirtualRoot

        def to_str(node: InputDefault) -> str:
            if isinstance(node, VirtualRoot):
                return node.get_config_path()
            elif isinstance(node, GroupDefault):
                name = node.get_name()
                if name is None:
                    name = "null"
                return node.get_override_key() + ": " + name
            else:
                return node.get_config_path()

        pad = "  " * indent

        if isinstance(tree, DefaultsTreeNode):
            node_str = to_str(tree.node)
            if tree.children is not None and len(tree.children) > 0:
                log.info(pad + node_str + ":")
                for child in tree.children:
                    self._print_defaults_tree_impl(tree=child, indent=indent + 1)
            else:
                log.info(pad + node_str)
        else:
            assert isinstance(tree, InputDefault)
            log.info(pad + to_str(tree))

    def _print_defaults_tree(
        self,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode = RunMode.RUN,
    ) -> None:
        assert log is not None
        defaults = self.config_loader.compute_defaults_list(
            config_name=config_name,
            overrides=overrides,
            run_mode=run_mode,
        )
        log.info("")
        self._log_header("Defaults Tree", filler="*")
        self._print_defaults_tree_impl(defaults.defaults_tree)

    def show_info(
        self,
        info: str,
        config_name: Optional[str],
        overrides: List[str],
        run_mode: RunMode = RunMode.RUN,
    ) -> None:
        options = {
            "all": self._print_all_info,
            "defaults": self._print_defaults_list,
            "defaults-tree": self._print_defaults_tree,
            "config": self._print_config_info,
            "plugins": self._print_plugins_info,
            "searchpath": self._print_search_path,
        }
        simple_stdout_log_config(level=logging.DEBUG)
        global log
        log = logging.getLogger(__name__)

        if info not in options:
            opts = sorted(options.keys())
            log.error(f"Info usage: --info [{'|'.join(opts)}]")
        else:
            options[info](
                config_name=config_name, overrides=overrides, run_mode=run_mode
            )
