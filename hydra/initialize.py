# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import copy
import os
from typing import Any, Callable, Optional

from hydra import version
from hydra._internal.hydra import Hydra
from hydra._internal.utils import (
    create_config_search_path,
    detect_calling_file_or_module_from_stack_frame,
    detect_task_name,
)
from hydra.core.global_hydra import GlobalHydra
from hydra.core.singleton import Singleton
from hydra.errors import HydraException


def get_gh_backup() -> Any:
    gh = Singleton._instances.get(GlobalHydra)
    if gh is None:
        return None
    assert isinstance(gh, GlobalHydra)
    if not gh.is_initialized():
        return copy.deepcopy(gh)
    return gh


def restore_gh_from_backup(_gh_backup: Any) -> Any:
    Singleton._instances.pop(GlobalHydra, None)
    if _gh_backup is not None:
        Singleton._instances[GlobalHydra] = _gh_backup


def _initialize_hydra(create_hydra: Callable[[], Any]) -> Any:
    gh_backup = get_gh_backup()
    try:
        create_hydra()
    except BaseException:
        restore_gh_from_backup(gh_backup)
        raise
    return gh_backup


class _ScopedInitializer:
    def __init__(
        self, create_hydra: Callable[[], Any], version_base: Optional[str]
    ) -> None:
        self._create_hydra = create_hydra
        self._version_base = version_base
        self._gh_backup: Any = None
        self._version_base_backup: Optional[str] = None

    def __enter__(self, *args: Any, **kwargs: Any) -> None:
        self._gh_backup = Singleton._instances.pop(GlobalHydra, None)
        self._version_base_backup = version.getbase()
        try:
            version.setbase(self._version_base)
            self._create_hydra()
        except BaseException:
            restore_gh_from_backup(self._gh_backup)
            assert self._version_base_backup is not None
            version.VersionBase.instance().setbase(self._version_base_backup)
            raise

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        restore_gh_from_backup(self._gh_backup)
        assert self._version_base_backup is not None
        version.VersionBase.instance().setbase(self._version_base_backup)


class initialize:
    """
    Initializes Hydra and add the config_path to the config search path.
    config_path is relative to the parent of the caller.
    Hydra detects the caller type automatically at runtime.

    Supported callers:
    - Python scripts
    - Python modules
    - Unit tests
    - Jupyter notebooks.
    :param config_path: path relative to the parent of the caller
    :param job_name: the value for hydra.job.name (By default it is automatically detected based on the caller)
    :param caller_stack_depth: stack depth of the caller, defaults to 1 (direct caller).
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        job_name: Optional[str] = None,
        caller_stack_depth: int = 1,
        version_base: Optional[str] = version._UNSPECIFIED_,
    ) -> None:
        version.setbase(version_base)

        if config_path is not None and os.path.isabs(config_path):
            raise HydraException("config_path in initialize() must be relative")
        calling_file, calling_module = detect_calling_file_or_module_from_stack_frame(
            caller_stack_depth + 1
        )
        if job_name is None:
            job_name = detect_task_name(
                calling_file=calling_file, calling_module=calling_module
            )

        self._gh_backup = _initialize_hydra(
            lambda: Hydra.create_main_hydra_file_or_module(
                calling_file=calling_file,
                calling_module=calling_module,
                config_path=config_path,
                job_name=job_name,
            )
        )

    @classmethod
    def scoped(
        cls,
        config_path: Optional[str] = None,
        job_name: Optional[str] = None,
        caller_stack_depth: int = 1,
        version_base: Optional[str] = version._UNSPECIFIED_,
    ) -> _ScopedInitializer:
        if config_path is not None and os.path.isabs(config_path):
            raise HydraException("config_path in initialize() must be relative")
        calling_file, calling_module = detect_calling_file_or_module_from_stack_frame(
            caller_stack_depth + 1
        )
        if job_name is None:
            job_name = detect_task_name(
                calling_file=calling_file, calling_module=calling_module
            )

        return _ScopedInitializer(
            lambda: Hydra.create_main_hydra_file_or_module(
                calling_file=calling_file,
                calling_module=calling_module,
                config_path=config_path,
                job_name=job_name,
            ),
            version_base,
        )

    def __enter__(self, *args: Any, **kwargs: Any) -> None: ...

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        restore_gh_from_backup(self._gh_backup)

    def __repr__(self) -> str:
        return "hydra.initialize()"


class initialize_config_module:
    """
    Initializes Hydra and add the config_module to the config search path.
    The config module must be importable (an __init__.py must exist at its top level)
    :param config_module: absolute module name, for example "foo.bar.conf".
    :param job_name: the value for hydra.job.name (default is 'app')
    """

    def __init__(
        self,
        config_module: str,
        job_name: str = "app",
        version_base: Optional[str] = version._UNSPECIFIED_,
    ):
        version.setbase(version_base)

        self._gh_backup = _initialize_hydra(
            lambda: Hydra.create_main_hydra_file_or_module(
                calling_file=None,
                calling_module=f"{config_module}.{job_name}",
                config_path=None,
                job_name=job_name,
            )
        )

    @classmethod
    def scoped(
        cls,
        config_module: str,
        job_name: str = "app",
        version_base: Optional[str] = version._UNSPECIFIED_,
    ) -> _ScopedInitializer:
        return _ScopedInitializer(
            lambda: Hydra.create_main_hydra_file_or_module(
                calling_file=None,
                calling_module=f"{config_module}.{job_name}",
                config_path=None,
                job_name=job_name,
            ),
            version_base,
        )

    def __enter__(self, *args: Any, **kwargs: Any) -> None: ...

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        restore_gh_from_backup(self._gh_backup)

    def __repr__(self) -> str:
        return "hydra.initialize_config_module()"


class initialize_config_dir:
    """
    Initializes Hydra and add an absolute config dir to the to the config search path.
    The config_dir is always a path on the file system and is must be an absolute path.
    Relative paths will result in an error.
    :param config_dir: absolute file system path
    :param job_name: the value for hydra.job.name (default is 'app')
    """

    def __init__(
        self,
        config_dir: str,
        job_name: str = "app",
        version_base: Optional[str] = version._UNSPECIFIED_,
    ) -> None:
        version.setbase(version_base)

        # Relative here would be interpreted as relative to cwd, which - depending on when it run
        # may have unexpected meaning. best to force an absolute path to avoid confusion.
        # Can consider using hydra.utils.to_absolute_path() to convert it at a future point if there is demand.
        if not os.path.isabs(config_dir):
            raise HydraException(
                "initialize_config_dir() requires an absolute config_dir as input"
            )
        csp = create_config_search_path(search_path_dir=config_dir)
        self._gh_backup = _initialize_hydra(
            lambda: Hydra.create_main_hydra2(task_name=job_name, config_search_path=csp)
        )

    @classmethod
    def scoped(
        cls,
        config_dir: str,
        job_name: str = "app",
        version_base: Optional[str] = version._UNSPECIFIED_,
    ) -> _ScopedInitializer:
        if not os.path.isabs(config_dir):
            raise HydraException(
                "initialize_config_dir() requires an absolute config_dir as input"
            )
        csp = create_config_search_path(search_path_dir=config_dir)
        return _ScopedInitializer(
            lambda: Hydra.create_main_hydra2(
                task_name=job_name, config_search_path=csp
            ),
            version_base,
        )

    def __enter__(self, *args: Any, **kwargs: Any) -> None: ...

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        restore_gh_from_backup(self._gh_backup)

    def __repr__(self) -> str:
        return "hydra.initialize_config_dir()"
