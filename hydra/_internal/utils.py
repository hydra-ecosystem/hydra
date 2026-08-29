# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import argparse
import inspect
import logging.config
import os
import sys
import traceback
import warnings
from os.path import dirname, join, normpath, realpath
from types import TracebackType
from typing import Any, List, Optional, Sequence, Tuple

from omegaconf.errors import OmegaConfBaseException

from hydra._internal._locate import _locate as _locate_impl
from hydra._internal.config_search_path_impl import ConfigSearchPathImpl
from hydra.core.config_search_path import ConfigSearchPath, SearchPathQuery
from hydra.core.utils import get_valid_filename, validate_config_path
from hydra.errors import (
    CompactHydraException,
    InstantiationException,
    SearchPathException,
)
from hydra.types import RunMode, TaskFunction

log = logging.getLogger(__name__)


def _get_module_name_override() -> Optional[str]:
    module_envs = ["HYDRA_MAIN_MODULE", "FB_PAR_MAIN_MODULE", "FB_XAR_MAIN_MODULE"]
    for module_env in module_envs:
        if module_env in os.environ:
            return os.environ[module_env]
    return None


def detect_calling_file_or_module_from_task_function(
    task_function: Any,
) -> Tuple[Optional[str], Optional[str]]:
    # if function is decorated, unwrap it
    while hasattr(task_function, "__wrapped__"):
        task_function = task_function.__wrapped__

    mdl = task_function.__module__
    override = _get_module_name_override()
    if override is not None:
        mdl = override

    calling_file: Optional[str]
    calling_module: Optional[str]
    if mdl not in (None, "__main__"):
        calling_file = None
        calling_module = mdl
    else:
        try:
            calling_file = inspect.getfile(task_function)
        except TypeError:
            calling_file = None
        calling_module = None

    return calling_file, calling_module


def detect_calling_file_or_module_from_stack_frame(
    stack_depth: int,
) -> Tuple[Optional[str], Optional[str]]:
    stack = inspect.stack()
    frame = stack[stack_depth]
    if is_notebook() and "_dh" in frame[0].f_globals:
        pynb_dir = frame[0].f_globals["_dh"][0]
        calling_file = join(pynb_dir, "notebook.ipynb")
        return calling_file, None

    calling_file = frame.filename
    calling_module = None
    try:
        calling_module = _get_module_name_override()
        if calling_module is None:
            calling_module = frame[0].f_globals[frame[3]].__module__
    except KeyError:
        try:
            calling_module = frame[0].f_locals["self"].__module__
        except KeyError:
            pass

    return calling_file, calling_module


def is_notebook() -> bool:
    try:
        shell = get_ipython().__class__.__name__  # type: ignore
        if shell == "ZMQInteractiveShell":
            return True  # Jupyter notebook or qtconsole
        elif shell == "TerminalInteractiveShell":
            return False  # Terminal running IPython
        else:
            return False  # Other type (?)
    except NameError:
        return False


def detect_task_name(calling_file: Optional[str], calling_module: Optional[str]) -> str:
    if calling_file is not None:
        target_file = os.path.basename(calling_file)
        task_name = get_valid_filename(os.path.splitext(target_file)[0])
    elif calling_module is not None:
        last_dot = calling_module.rfind(".")
        if last_dot != -1:
            task_name = calling_module[last_dot + 1 :]
        else:
            task_name = calling_module
    else:
        raise ValueError()

    return task_name


def compute_search_path_dir(
    calling_file: Optional[str],
    calling_module: Optional[str],
    config_path: Optional[str],
) -> Optional[str]:
    if config_path is not None:
        if os.path.isabs(config_path):
            return config_path
        if config_path.startswith("pkg://"):
            return config_path

    if calling_file is not None:
        abs_base_dir = realpath(dirname(calling_file))

        if config_path is not None:
            search_path_dir = join(abs_base_dir, config_path)
        else:
            return None

        search_path_dir = normpath(search_path_dir)
    elif calling_module is not None:
        last_dot = calling_module.rfind(".")
        if last_dot != -1:
            calling_module = calling_module[0:last_dot]
        else:
            calling_module = ""

        if config_path is not None:
            config_path = config_path.replace(os.path.sep, "/")
            while str.startswith(config_path, "../"):
                config_path = config_path[len("../") :]
                last_dot = calling_module.rfind(".")
                if last_dot != -1:
                    calling_module = calling_module[0:last_dot]
                else:
                    calling_module = ""

        search_path_dir = "pkg://" + calling_module

        if config_path is not None:
            if calling_module != "":
                search_path_dir = search_path_dir + "/" + config_path
            else:
                search_path_dir = search_path_dir + config_path
    else:
        raise ValueError()

    return search_path_dir


def is_under_debugger() -> bool:
    """
    Attempts to detect if running under a debugger
    """
    frames = inspect.stack()
    if len(frames) >= 3:
        filename = frames[-3].filename
        if filename.endswith("/pdb.py"):
            return True
        elif filename.endswith("/pydevd.py"):
            return True

    # unknown debugging will sometimes set sys.trace
    return sys.gettrace() is not None


def create_automatic_config_search_path(
    calling_file: Optional[str],
    calling_module: Optional[str],
    config_path: Optional[str],
) -> ConfigSearchPath:
    search_path_dir = compute_search_path_dir(calling_file, calling_module, config_path)
    return create_config_search_path(search_path_dir)


def create_config_search_path(search_path_dir: Optional[str]) -> ConfigSearchPath:
    from hydra.core.plugins import Plugins
    from hydra.plugins.search_path_plugin import SearchPathPlugin

    search_path = ConfigSearchPathImpl()
    search_path.append("hydra", "pkg://hydra.conf")

    if search_path_dir is not None:
        search_path.append("main", search_path_dir)

    search_path_plugins = Plugins.instance().discover(SearchPathPlugin)
    for spp in search_path_plugins:
        plugin = spp()
        assert isinstance(plugin, SearchPathPlugin)
        plugin.manipulate_search_path(search_path)

    search_path.append("schema", "structured://")

    return search_path


def _is_env_set(name: str) -> bool:
    return name in os.environ and os.environ[name] == "1"


def run_and_report(func: Any) -> Any:
    try:
        return func()
    except Exception as ex:
        if _is_env_set("HYDRA_FULL_ERROR") or is_under_debugger():
            raise ex
        else:
            try:
                if isinstance(ex, CompactHydraException):
                    sys.stderr.write(str(ex) + os.linesep)
                    if isinstance(ex.__cause__, OmegaConfBaseException):
                        sys.stderr.write(str(ex.__cause__) + os.linesep)
                else:
                    # Custom printing that strips the Hydra related stack frames from the top
                    # And any omegaconf frames from the bottom.
                    # It is possible to add additional libraries to sanitize from the bottom later,
                    # maybe even make it configurable.

                    tb = ex.__traceback__
                    search_max = 10
                    # strip Hydra frames from start of stack
                    # will strip until it hits run_job()
                    while search_max > 0:
                        if tb is None:
                            break
                        frame = tb.tb_frame
                        tb = tb.tb_next
                        search_max = search_max - 1
                        if inspect.getframeinfo(frame).function in {
                            "run_job",
                            "_run_job",
                        }:
                            break

                    if search_max == 0 or tb is None:
                        # could not detect run_job, probably a runtime exception before we got there.
                        # do not sanitize the stack trace.
                        traceback.print_exc()
                        sys.exit(1)

                    # strip OmegaConf frames from bottom of stack
                    filtered_traceback: List[TracebackType] = []
                    current_tb: Optional[TracebackType] = tb
                    while current_tb is not None:
                        frame = current_tb.tb_frame
                        mdl = inspect.getmodule(frame)
                        name = mdl.__name__ if mdl is not None else ""
                        if name.startswith("omegaconf."):
                            break
                        filtered_traceback.append(current_tb)
                        current_tb = current_tb.tb_next

                    final_tb: Optional[TracebackType] = None
                    for traceback_frame in reversed(filtered_traceback):
                        final_tb = TracebackType(
                            final_tb,
                            traceback_frame.tb_frame,
                            traceback_frame.tb_lasti,
                            traceback_frame.tb_lineno,
                        )
                    assert final_tb is not None

                    exception_hook = sys.excepthook
                    if exception_hook is sys.__excepthook__ or not callable(
                        exception_hook
                    ):
                        traceback.print_exception(None, value=ex, tb=final_tb)
                    else:
                        try:
                            exception_hook(type(ex), ex, final_tb)
                        except Exception:
                            traceback.print_exception(None, value=ex, tb=final_tb)
            except Exception as ex2:
                sys.stderr.write(
                    "An error occurred during Hydra's exception formatting:"
                    + os.linesep
                    + repr(ex2)
                    + os.linesep
                )
                raise ex
        sys.exit(1)


def _run_hydra(
    args: argparse.Namespace,
    args_parser: argparse.ArgumentParser,
    task_function: TaskFunction,
    config_path: Optional[str],
    config_name: Optional[str],
    caller_stack_depth: int = 2,
) -> None:
    from hydra.core.global_hydra import GlobalHydra

    from .hydra import Hydra

    if args.config_name is not None:
        config_name = args.config_name

    if args.config_path is not None:
        config_path = args.config_path

    (
        calling_file,
        calling_module,
    ) = detect_calling_file_or_module_from_task_function(task_function)
    if calling_file is None and calling_module is None:
        (
            calling_file,
            calling_module,
        ) = detect_calling_file_or_module_from_stack_frame(caller_stack_depth + 1)
    task_name = detect_task_name(calling_file, calling_module)

    validate_config_path(config_path)

    search_path = create_automatic_config_search_path(
        calling_file, calling_module, config_path
    )

    def add_conf_dir() -> None:
        if args.config_dir is not None:
            abs_config_dir = os.path.abspath(args.config_dir)
            if not os.path.isdir(abs_config_dir):
                raise SearchPathException(
                    f"Additional config directory '{abs_config_dir}' not found"
                )
            search_path.prepend(
                provider="command-line",
                path=f"file://{abs_config_dir}",
                anchor=SearchPathQuery(provider="schema"),
            )

    run_and_report(add_conf_dir)
    hydra = run_and_report(
        lambda: Hydra.create_main_hydra2(
            task_name=task_name, config_search_path=search_path
        )
    )

    try:
        if args.help:
            hydra.app_help(config_name=config_name, args_parser=args_parser, args=args)
            sys.exit(0)
        has_show_cfg = args.cfg is not None
        if args.resolve and (not has_show_cfg and not args.help):
            raise ValueError(
                "The --resolve flag can only be used in conjunction with --cfg or --help"
            )
        if args.hydra_help:
            hydra.hydra_help(
                config_name=config_name, args_parser=args_parser, args=args
            )
            sys.exit(0)

        num_commands = (
            args.run
            + has_show_cfg
            + args.multirun
            + args.shell_completion
            + (args.info is not None)
        )
        if num_commands > 1:
            raise ValueError(
                "Only one of --run, --multirun, --cfg, --info and --shell_completion can be specified"
            )
        if num_commands == 0:
            args.run = True

        overrides = args.overrides

        if args.run or args.multirun:
            run_mode = hydra.get_mode(config_name=config_name, overrides=overrides)
            _run_app(
                run=args.run,
                multirun=args.multirun,
                mode=run_mode,
                hydra=hydra,
                config_name=config_name,
                task_function=task_function,
                overrides=overrides,
            )
        elif args.cfg:
            run_and_report(
                lambda: hydra.show_cfg(
                    config_name=config_name,
                    overrides=args.overrides,
                    cfg_type=args.cfg,
                    package=args.package,
                    resolve=args.resolve,
                )
            )
        elif args.shell_completion:
            run_and_report(
                lambda: hydra.shell_completion(
                    config_name=config_name, overrides=args.overrides
                )
            )
        elif args.info:
            hydra.show_info(
                args.info, config_name=config_name, overrides=args.overrides
            )
        else:
            sys.stderr.write("Command not specified\n")
            sys.exit(1)
    finally:
        GlobalHydra.instance().clear()


def _run_app(
    run: bool,
    multirun: bool,
    mode: Optional[RunMode],
    hydra: Any,
    config_name: Optional[str],
    task_function: TaskFunction,
    overrides: List[str],
) -> None:
    if mode is None:
        if run:
            mode = RunMode.RUN
            overrides.extend(["hydra.mode=RUN"])
        else:
            mode = RunMode.MULTIRUN
            overrides.extend(["hydra.mode=MULTIRUN"])
    else:
        if multirun and mode == RunMode.RUN:
            warnings.warn(
                message="\n"
                "\tRunning Hydra app with --multirun, overriding with `hydra.mode=MULTIRUN`.",
                category=UserWarning,
            )
            mode = RunMode.MULTIRUN
            overrides.extend(["hydra.mode=MULTIRUN"])

    if mode == RunMode.RUN:
        run_and_report(
            lambda: hydra.run(
                config_name=config_name,
                task_function=task_function,
                overrides=overrides,
            )
        )
    else:
        run_and_report(
            lambda: hydra.multirun(
                config_name=config_name,
                task_function=task_function,
                overrides=overrides,
            )
        )


def _get_exec_command() -> str:
    if sys.argv[0].endswith(".py"):
        return f"python {sys.argv[0]}"
    else:
        # Running as an installed app (setuptools entry point)
        executable = os.path.basename(sys.argv[0])
        return executable


def _get_completion_help() -> str:
    from hydra.core.plugins import Plugins
    from hydra.plugins.completion_plugin import CompletionPlugin

    completion_plugins = Plugins.instance().discover(CompletionPlugin)
    completion_info: List[str] = []
    for plugin_cls in completion_plugins:
        assert issubclass(plugin_cls, CompletionPlugin)
        for cmd in ["install", "uninstall"]:
            head = f"{plugin_cls.provides().capitalize()} - {cmd.capitalize()}:"
            completion_info.append(head)
            completion_info.append(plugin_cls.help(cmd).format(_get_exec_command()))
        completion_info.append("")

    completion_help = "\n".join(f"    {x}" if x else x for x in completion_info)
    return completion_help


def get_args_parser() -> argparse.ArgumentParser:
    from .. import __version__

    parser = argparse.ArgumentParser(add_help=False, description="Hydra")
    parser.add_argument("--help", "-h", action="store_true", help="Application's help")
    parser.add_argument("--hydra-help", action="store_true", help="Hydra's help")
    parser.add_argument(
        "--version",
        action="version",
        help="Show Hydra's version and exit",
        version=f"Hydra {__version__}",
    )
    parser.add_argument(
        "overrides",
        nargs="*",
        help="Any key=value arguments to override config values (use dots for.nested=overrides)",
    )

    parser.add_argument(
        "--cfg",
        "-c",
        choices=["job", "hydra", "all"],
        help="Show config instead of running [job|hydra|all]",
    )
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="Used in conjunction with --cfg, resolve config interpolations before printing.",
    )

    parser.add_argument("--package", "-p", help="Config package to show")

    parser.add_argument("--run", "-r", action="store_true", help="Run a job")

    parser.add_argument(
        "--multirun",
        "-m",
        action="store_true",
        help="Run multiple jobs with the configured launcher and sweeper",
    )

    # defer building the completion help string until we actually need to render it
    class LazyCompletionHelp:
        def __repr__(self) -> str:
            return f"Install or Uninstall shell completion:\n{_get_completion_help()}"

    if sys.version_info >= (3, 14):
        # Python 3.14+ adds help message validation via ArgumentParser._check_help,
        # which calls formatter._expand_help(action) to validate that action.help
        # is a string that can be used in string formatting (e.g., "text %(prog)s").
        # This breaks our LazyCompletionHelp because `_expand_help` expects an actual
        # string.
        # It is safe to disable this validation temporarily because LazyCompletionHelp.
        # __repr__() returns a plain string (no % formatting)
        original_check_help = argparse.ArgumentParser._check_help  # type: ignore
        argparse.ArgumentParser._check_help = (  # type: ignore
            lambda self, action: None
        )
        try:
            parser.add_argument(
                "--shell-completion",
                "-sc",
                action="store_true",
                help=LazyCompletionHelp(),  # type: ignore
            )
        finally:
            # Immediately restore normal validation
            argparse.ArgumentParser._check_help = original_check_help  # type: ignore
    else:
        parser.add_argument(
            "--shell-completion",
            "-sc",
            action="store_true",
            help=LazyCompletionHelp(),  # type: ignore
        )

    parser.add_argument(
        "--config-path",
        "-cp",
        help="""Overrides the config_path specified in hydra.main().
                    The config_path is absolute or relative to the Python file declaring @hydra.main()""",
    )

    parser.add_argument(
        "--config-name",
        "-cn",
        help="Overrides the config_name specified in hydra.main()",
    )

    parser.add_argument(
        "--config-dir",
        "-cd",
        help="Adds an additional config dir to the config search path",
    )

    parser.add_argument(
        "--experimental-rerun",
        help="Rerun a job from a previous config pickle",
    )

    info_choices = [
        "all",
        "config",
        "defaults",
        "defaults-tree",
        "plugins",
        "searchpath",
    ]
    parser.add_argument(
        "--info",
        "-i",
        const="all",
        nargs="?",
        action="store",
        choices=info_choices,
        help=f"Print Hydra information [{'|'.join(info_choices)}]",
    )
    return parser


def get_args(args: Optional[Sequence[str]] = None) -> Any:
    return get_args_parser().parse_intermixed_args(args=args)


def get_column_widths(matrix: List[List[str]]) -> List[int]:
    num_cols = 0
    for row in matrix:
        num_cols = max(num_cols, len(row))
    widths: List[int] = [0] * num_cols
    for row in matrix:
        for idx, col in enumerate(row):
            widths[idx] = max(widths[idx], len(col))

    return widths


def _locate(path: str) -> Any:
    return _locate_impl(path)


def _get_cls_name(config: Any, pop: bool = True) -> str:
    if "_target_" not in config:
        raise InstantiationException("Input config does not have a `_target_` field")

    if pop:
        classname = config.pop("_target_")
    else:
        classname = config["_target_"]
    if not isinstance(classname, str):
        raise InstantiationException("_target_ field type must be a string")
    return classname
