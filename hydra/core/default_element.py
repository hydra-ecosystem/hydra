# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import re
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Optional, Pattern, Union

from omegaconf import AnyNode, DictConfig, OmegaConf

from hydra.errors import ConfigCompositionException

_defaults_list_interpolation_pattern: Pattern[str] = re.compile(r"\${\s*([^{}]*?)\s*}")
_legacy_interpolation_pattern: Pattern[str] = re.compile(r"\${defaults\.\d+\.")


@dataclass
class ResultDefault:
    config_path: str | None = None
    parent: str | None = None
    package: str | None = None
    is_self: bool = False
    primary: bool = field(default=False, compare=False)

    override_key: str | None = field(default=None, compare=False)

    def __repr__(self) -> str:
        attrs = []
        attr_names = "config_path", "package", "parent"
        for attr in attr_names:
            value = getattr(self, attr)
            if value is not None:
                attrs.append(f'{attr}="{value}"')

        flags = []
        flag_names = ["is_self", "primary"]
        for flag in flag_names:
            value = getattr(self, flag)
            if value:
                flags.append(f"{flag}=True")

        ret = f"{','.join(attrs + flags)}"
        return f"{type(self).__name__}({ret})"


@dataclass
class InputDefault:
    package: str | None = None
    parent_base_dir: str | None = field(default=None, compare=False, repr=False)
    parent_package: str | None = field(default=None, compare=False, repr=False)
    package_header: str | None = field(default=None, compare=False)
    primary: bool = field(default=False, compare=False)

    def is_self(self) -> bool:
        raise NotImplementedError()

    def update_parent(
        self, parent_base_dir: str | None, parent_package: str | None
    ) -> None:
        assert self.parent_package is None or self.parent_package == parent_package
        assert self.parent_base_dir is None or self.parent_base_dir == parent_base_dir
        self.parent_base_dir = parent_base_dir
        self.parent_package = parent_package

    def is_optional(self) -> bool:
        raise NotImplementedError()

    def get_group_path(self) -> str:
        raise NotImplementedError()

    def get_config_path(self) -> str:
        raise NotImplementedError()

    def get_default_package(self) -> str:
        return self.get_group_path().replace("/", ".")

    def get_final_package(self, default_to_package_header: bool = True) -> str:
        """
        :param default_to_package_header: if package is not present, fallback to package header
        :return:
        """
        raise NotImplementedError()

    def _relative_group_path(self) -> str:
        raise NotImplementedError()

    def get_name(self) -> str | None:
        raise NotImplementedError()

    def _get_attributes(self) -> list[str]:
        raise NotImplementedError()

    def _get_flags(self) -> list[str]:
        raise NotImplementedError()

    def _get_parent_package(self) -> str | None:
        ret = self.__dict__["parent_package"]
        assert ret is None or isinstance(ret, str)
        return ret

    def is_virtual(self) -> bool:
        return False

    def is_deleted(self) -> bool:
        if "deleted" in self.__dict__:
            return bool(self.__dict__["deleted"])
        else:
            return False

    def set_package_header(self, package_header: str | None) -> None:
        assert self.__dict__["package_header"] is None

        if package_header is None:
            return

        # package header is always interpreted as absolute.
        # if it does not have a _global_ prefix, add it.
        if package_header != "_global_" and not package_header.startswith("_global_."):
            if package_header == "":
                package_header = "_global_"
            else:
                package_header = f"_global_.{package_header}"

        self.__dict__["package_header"] = package_header

    def get_package_header(self) -> str | None:
        ret = self.__dict__["package_header"]
        assert ret is None or isinstance(ret, str)
        return ret

    def get_package(self, default_to_package_header: bool = True) -> str | None:
        if self.__dict__["package"] is None and default_to_package_header:
            ret = self.__dict__["package_header"]
        else:
            ret = self.__dict__["package"]
        assert ret is None or isinstance(ret, str)
        return ret

    def _get_final_package(
        self,
        parent_package: str | None,
        package: str | None,
        name: str | None,
    ) -> str:
        assert parent_package is not None

        if package is None:
            package = self._relative_group_path().replace("/", ".")

        if parent_package == "":
            ret = package
        else:
            if package == "":
                ret = parent_package
            else:
                ret = f"{parent_package}.{package}"

        lgi = ret.rfind("_global_")
        if lgi == -1:
            return ret
        else:
            return ret[lgi + len("_global_") + 1 :]

    def __repr__(self) -> str:
        attrs = []
        attr_names = self._get_attributes()
        for attr in attr_names:
            value = getattr(self, attr)
            if value is not None:
                if isinstance(value, str):
                    svalue = f'"{value}"'
                else:
                    svalue = value
                attrs.append(f"{attr}={svalue}")

        flags = []
        flag_names = self._get_flags()
        for flag in flag_names:
            value = getattr(self, flag)
            if value:
                flags.append(f"{flag}=True")

        ret = f"{','.join(attrs)}"

        if len(flags) > 0:
            ret = f"{ret},{','.join(flags)}"
        return f"{type(self).__name__}({ret})"

    def is_interpolation(self) -> bool:
        raise NotImplementedError()

    def is_legacy_interpolation(self) -> bool:
        name = self.get_name()
        return (
            isinstance(name, str)
            and re.search(_legacy_interpolation_pattern, name) is not None
        )

    def is_missing(self) -> bool:
        """
        True if the name of the config is '???'
        :return:
        """
        raise NotImplementedError()

    def resolve_interpolation(self, known_choices: DictConfig) -> None:
        raise NotImplementedError()

    def _resolve_interpolation_impl(
        self, known_choices: DictConfig, val: str | None
    ) -> tuple[str, str]:
        """Resolve the path and retain its final choice's literal identity."""
        assert val is not None
        was_missing = OmegaConf.is_missing(
            val if "/" not in val else val.rsplit("/", 1)[-1]
        )

        def replace(match: re.Match[str]) -> str:
            key = match.group(1).strip()
            if key in known_choices:
                choice = known_choices[key]
                if isinstance(choice, str):
                    return choice
            return match.group(0)

        ret = _defaults_list_interpolation_pattern.sub(replace, val)
        if "${" in ret:
            options = [
                x
                for x in known_choices.keys()
                if x != "defaults" and isinstance(x, str)
            ]
            if len(options) > 0:
                options_str = ", ".join(options)
                msg = f"Error resolving interpolation '{val}', possible interpolation keys: {options_str}"
            else:
                msg = f"Error resolving interpolation '{val}'"
            raise ConfigCompositionException(msg)

        name = ret.rsplit("/", 1)[-1]
        if not was_missing and OmegaConf.is_missing(name):
            # Missing choices cannot resolve, so a new missing suffix is literal.
            name = OmegaConf.create({"name": "\\" + name}).name
        return ret, name

    def get_override_key(self) -> str:
        default_pkg = self.get_default_package()
        final_pkg = self.get_final_package(default_to_package_header=False)
        key = self.get_group_path()
        if default_pkg != final_pkg:
            if final_pkg == "":
                final_pkg = "_global_"
            key = f"{key}@{final_pkg}"
        return key

    def get_relative_override_key(self) -> str:
        raise NotImplementedError()

    def is_override(self) -> bool:
        raise NotImplementedError()

    def is_external_append(self) -> bool:
        raise NotImplementedError()


@dataclass
class VirtualRoot(InputDefault):
    def is_virtual(self) -> bool:
        return True

    def is_self(self) -> bool:
        return False

    def is_optional(self) -> bool:
        raise NotImplementedError()

    def get_group_path(self) -> str:
        raise NotImplementedError()

    def get_config_path(self) -> str:
        return "<root>"

    def get_final_package(self, default_to_package_header: bool = True) -> str:
        raise NotImplementedError()

    def _relative_group_path(self) -> str:
        raise NotImplementedError()

    def get_name(self) -> str:
        raise NotImplementedError()

    def is_missing(self) -> bool:
        return False

    def _get_attributes(self) -> list[str]:
        raise NotImplementedError()

    def _get_flags(self) -> list[str]:
        raise NotImplementedError()

    def __repr__(self) -> str:
        return "VirtualRoot()"

    def resolve_interpolation(self, known_choices: DictConfig) -> None:
        raise NotImplementedError()

    def is_override(self) -> bool:
        return False

    def is_external_append(self) -> bool:
        return False


@dataclass(repr=False)
class ConfigDefault(InputDefault):
    path: str | None = None
    optional: bool = False
    deleted: bool | None = None
    # Preserve OmegaConf value identity before constructing a qualified path.
    _name: str | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.is_self() and self.package is not None:
            raise ValueError("_self_@PACKAGE is not supported")
        if self.package == "_here_":
            self.package = ""

    def is_self(self) -> bool:
        return self.path == "_self_"

    def is_optional(self) -> bool:
        return self.optional

    def get_group_path(self) -> str:
        assert self.parent_base_dir is not None
        assert self.path is not None

        if self.path.startswith("/"):
            path = self.path[1:]
            absolute = True
        else:
            path = self.path
            absolute = False

        idx = path.rfind("/")
        if idx == -1:
            group = ""
        else:
            group = path[0:idx]

        if not absolute:
            if self.parent_base_dir == "":
                return group
            else:
                if group == "":
                    return f"{self.parent_base_dir}"
                else:
                    return f"{self.parent_base_dir}/{group}"
        else:
            return group

    def get_name(self) -> str | None:
        path = self.path if self._name is None else self._name
        assert path is not None
        idx = path.rfind("/")
        if idx == -1:
            return path
        else:
            return path[idx + 1 :]

    def get_config_path(self) -> str:
        assert self.parent_base_dir is not None
        assert self.path is not None
        if self.path.startswith("/"):
            path = self.path[1:]
            absolute = True
        else:
            path = self.path
            absolute = False

        if not absolute:
            if self.parent_base_dir == "":
                return path
            else:
                return f"{self.parent_base_dir}/{path}"
        else:
            return path

    def get_final_package(self, default_to_package_header: bool = True) -> str:
        return self._get_final_package(
            self.parent_package,
            self.get_package(default_to_package_header),
            self.get_name(),
        )

    def _relative_group_path(self) -> str:
        assert self.path is not None
        if self.path.startswith("/"):
            path = self.path[1:]
        else:
            path = self.path

        idx = path.rfind("/")
        if idx == -1:
            return ""
        else:
            return path[0:idx]

    def _get_attributes(self) -> list[str]:
        return ["path", "package", "deleted"]

    def _get_flags(self) -> list[str]:
        return ["optional"]

    def is_interpolation(self) -> bool:
        path = self.get_config_path()
        node = AnyNode(path)
        return node._is_interpolation()

    def is_legacy_interpolation(self) -> bool:
        assert self.path is not None
        return re.search(_legacy_interpolation_pattern, self.path) is not None

    def resolve_interpolation(self, known_choices: DictConfig) -> None:
        assert self.path is not None
        absolute = self.path.startswith("/")
        path = self.path[1:] if absolute else self.path
        resolved, self._name = self._resolve_interpolation_impl(known_choices, path)
        self.path = f"/{resolved.lstrip('/')}" if absolute else resolved

    def is_missing(self) -> bool:
        return OmegaConf.is_missing(self.get_name())

    def is_override(self) -> bool:
        return False

    def is_external_append(self) -> bool:
        return False


@dataclass(repr=False)
class GroupDefault(InputDefault):
    # config group name if present
    group: str | None = None
    # config file name
    value: str | list[str] | None = None
    optional: bool = False

    override: bool = False
    deleted: bool | None = None

    config_name_overridden: bool = field(default=False, compare=False, repr=False)
    # True if this item was added using +foo=bar from the external overrides
    external_append: bool = field(default=False, compare=False, repr=False)

    normalized_shorthand: bool = field(default=False, compare=False, repr=False)
    original_group: str | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        assert self.group is not None and self.group != ""
        if self.package == "_here_":
            self.package = ""

    def is_self(self) -> bool:
        return self.value == "_self_"

    def is_optional(self) -> bool:
        return self.optional

    def is_override(self) -> bool:
        return self.override

    def get_group_path(self) -> str:
        assert self.parent_base_dir is not None
        assert self.group is not None

        if self.group.startswith("/"):
            group = self.group[1:]
            absolute = True
        else:
            group = self.group
            absolute = self.external_append

        if self.parent_base_dir == "" or absolute:
            return group
        else:
            return f"{self.parent_base_dir}/{group}"

    def get_config_path(self) -> str:
        group_path = self.get_group_path()
        assert group_path != ""

        return f"{group_path}/{self.get_name()}"

    def is_name(self) -> bool:
        return self.value is None or isinstance(self.value, str)

    def is_options(self) -> bool:
        return isinstance(self.value, list)

    def get_name(self) -> str | None:
        assert self.value is None or isinstance(self.value, str)
        return self.value

    def get_options(self) -> list[str]:
        assert isinstance(self.value, list)
        return self.value

    def get_final_package(self, default_to_package_header: bool = True) -> str:
        name = self.get_name() if self.is_name() else None
        return self._get_final_package(
            "" if self.external_append else self._get_parent_package(),
            self.get_package(default_to_package_header=default_to_package_header),
            name,
        )

    def _relative_group_path(self) -> str:
        assert self.group is not None
        if self.group.startswith("/"):
            return self.group[1:]
        else:
            return self.group

    def _get_attributes(self) -> list[str]:
        return ["group", "value", "package", "deleted"]

    def _get_flags(self) -> list[str]:
        return ["optional", "override"]

    def is_interpolation(self) -> bool:
        """
        True if config_name is an interpolation
        """
        if not self.is_name():
            return False

        name = self.get_name()
        if isinstance(name, str):
            node = AnyNode(name)
            return node._is_interpolation()
        else:
            return False

    def resolve_interpolation(self, known_choices: DictConfig) -> None:
        name = self.get_name()
        if name is not None:
            if self.is_legacy_interpolation():
                msg = dedent(
                    f"""
Defaults list element '{self.get_override_key()}={name}' is using a deprecated interpolation form.
See http://hydra.cc/docs/1.1/upgrades/1.0_to_1.1/defaults_list_interpolation for migration information."""
                )
                raise ConfigCompositionException(msg)

            resolved, suffix = self._resolve_interpolation_impl(known_choices, name)
            self.value = suffix if "/" not in resolved else resolved

            if isinstance(resolved, str) and "/" in resolved:
                segments = resolved.split("/")
                if ".." not in segments and resolved != "???" and "${" not in resolved:
                    last_slash_idx = resolved.rfind("/")
                    prefix = resolved[:last_slash_idx]
                    self.original_group = self.group
                    self.normalized_shorthand = True
                    self.group = f"{self.group}/{prefix}"
                    self.value = suffix

    def is_missing(self) -> bool:
        if self.is_name():
            return OmegaConf.is_missing(self.get_name())
        else:
            return False

    def get_relative_override_key(self) -> str:
        assert self.group is not None
        default_pkg = self.get_default_package()
        key = self.group
        if default_pkg != self.get_package() and self.package is not None:
            key = f"{key}@{self.package}"
        return key

    def is_external_append(self) -> bool:
        return self.external_append


@dataclass
class DefaultsTreeNode:
    node: InputDefault
    children: list[Union["DefaultsTreeNode", InputDefault]] | None = None

    parent: Optional["DefaultsTreeNode"] = field(
        default=None,
        repr=False,
        compare=False,
    )

    def parent_node(self) -> InputDefault | None:
        if self.parent is None:
            return None
        else:
            return self.parent.node
