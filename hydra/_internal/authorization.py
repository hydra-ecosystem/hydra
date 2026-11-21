# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
from typing import Any


class _InitializationFrame:
    """Restore Hydra-owned registry state without copying application objects."""

    def __init__(self) -> None:
        from hydra._internal.sources_registry import SourcesRegistry
        from hydra.core.global_hydra import GlobalHydra
        from hydra.core.plugins import Plugins
        from hydra.core.singleton import Singleton

        global_hydra = Singleton._instances.get(GlobalHydra)
        if isinstance(global_hydra, GlobalHydra) and global_hydra.is_initialized():
            raise ValueError(
                "GlobalHydra is already initialized, call GlobalHydra.instance().clear() if you want to re-initialize"
            )
        self._closed = False
        self._snapshots: list[tuple[type, Any, dict[str, Any]]] = []
        for kind in (GlobalHydra, Plugins, SourcesRegistry):
            instance = Singleton._instances.get(kind)
            state: dict[str, Any] = {}
            if instance is not None:
                if isinstance(instance, GlobalHydra):
                    state = {
                        "hydra": instance.hydra,
                        "_initialization_frame": instance._initialization_frame,
                    }
                elif isinstance(instance, Plugins):
                    state = {
                        "plugin_type_to_subclass_list": {
                            key: list(classes)
                            for key, classes in instance.plugin_type_to_subclass_list.items()
                        },
                        "class_name_to_class": dict(instance.class_name_to_class),
                        "stats": instance.stats,
                        "_discovery_complete": instance._discovery_complete,
                        "_explicit_plugins": list(instance._explicit_plugins),
                    }
                elif isinstance(instance, SourcesRegistry):
                    state = {"types": dict(instance.types)}
            self._snapshots.append((kind, instance, state))

    def __enter__(self) -> "_InitializationFrame":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        from hydra.core.global_hydra import GlobalHydra

        if exc_type is not None:
            self.close()
        else:
            GlobalHydra.instance()._initialization_frame = self

    def close(self) -> None:
        from hydra.core.singleton import Singleton

        if self._closed:
            return
        self._closed = True
        for kind, instance, state in self._snapshots:
            if instance is None:
                Singleton._instances.pop(kind, None)
            else:
                instance.__dict__.update(state)
                Singleton._instances[kind] = instance
