import inspect
import logging
import os
import pkgutil
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from textwrap import dedent
from typing import Any, cast, get_type_hints

import hydra
from jinja2 import Environment, PackageLoader, Template
from omegaconf import OmegaConf, ValidationError
from omegaconf._utils import (
    _resolve_optional,
    get_dict_key_value_types,
    get_list_element_type,
    is_dict_annotation,
    is_list_annotation,
    is_structured_config,
    is_union_annotation,
    type_str,
)

from configen.config import Config, ConfigenConf, ModuleConf
from configen.utils import (
    collect_imports,
    convert_imports,
    is_tuple_annotation,
)

# Adding the current working directory to the PYTHONPATH to allow generation of code
# that is not installed properly
sys.path.append(os.getcwd())

log = logging.getLogger(__name__)

# Configen renders Python source, not HTML, so Jinja autoescape is not applicable.
jinja_env = Environment(  # nosec B701
    loader=PackageLoader("configen", "templates"),
    keep_trailing_newline=True,
    trim_blocks=True,
)
cast(dict[str, Any], jinja_env.tests)["empty"] = lambda x: x == inspect.Signature.empty


def init_config(conf_dir: str) -> None:
    log.info(f"Initializing config in '{conf_dir}'")

    path = Path(hydra.utils.to_absolute_path(conf_dir))
    path.mkdir(parents=True, exist_ok=True)
    file = path / "configen.yaml"
    if file.exists():
        sys.stderr.write(f"Config file '{file}' already exists\n")
        sys.exit(1)

    sample_config = pkgutil.get_data(__name__, "templates/sample_config.yaml")
    assert sample_config is not None
    file.write_bytes(sample_config)


def save(cfg: ConfigenConf, module: str, code: str) -> None:
    module_path = module.replace(".", "/")

    module_path_pattern = Template(cfg.module_path_pattern).render(
        module_path=module_path
    )
    path = Path(cfg.output_dir) / module_path_pattern
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code)
    log.info(f"{module}.{module} -> {path}")


@dataclass
class Parameter:
    name: str
    type_str: str
    default: str | None


@dataclass
class ClassInfo:
    module: str
    name: str
    parameters: list[Parameter]
    target: str


def is_incompatible(type_: type[Any]) -> bool:
    opt = _resolve_optional(type_)
    # Unions are not supported (Except Optional)
    if not opt[0] and is_union_annotation(type_):
        return True

    type_ = opt[1]
    if type_ in (type(None), tuple, list, dict):
        return False

    try:
        if is_list_annotation(type_):
            lt = get_list_element_type(type_)
            return is_incompatible(lt)
        if is_dict_annotation(type_):
            kvt = get_dict_key_value_types(type_)
            if not issubclass(kvt[0], (str, Enum)):
                return True
            return is_incompatible(kvt[1])
        if is_tuple_annotation(type_):
            for arg in type_.__args__:
                if arg is not ... and is_incompatible(arg):
                    return True
            return False
    except ValidationError:
        return True

    if type_ is Any or issubclass(type_, (int, float, str, bool, Enum)):
        return False
    if is_structured_config(type_):
        try:
            OmegaConf.structured(type_)  # verify it's actually legal
        except ValidationError as e:
            log.debug(
                f"Failed to create DictConfig from ({type_.__name__}) : {e}, flagging as incompatible"
            )
            return True
        return False
    return True


def get_default_flags(module: ModuleConf) -> list[Parameter]:
    def_flags: list[Parameter] = []

    if module.default_flags._convert_ is not None:
        def_flags.append(
            Parameter(
                name="_convert_",
                type_str="str",
                default=f'"{module.default_flags._convert_.name}"',
            )
        )

    if module.default_flags._recursive_ is not None:
        def_flags.append(
            Parameter(
                name="_recursive_",
                type_str="bool",
                default=str(module.default_flags._recursive_),
            )
        )

    return def_flags


def generate_module(cfg: ConfigenConf, module: ModuleConf) -> str:
    classes_map: dict[str, ClassInfo] = {}
    imports: set[Any] = set()
    string_imports: set[str] = set()

    default_flags = get_default_flags(module)

    for class_name in module.classes:
        full_name = f"{module.name}.{class_name}"
        cls = hydra.utils.get_class(full_name)
        sig = inspect.signature(cls)
        resolved_hints = get_type_hints(cls.__init__)  # type: ignore
        params: list[Parameter] = []
        params = params + default_flags

        for name, p in sig.parameters.items():
            type_ = original_type = resolved_hints.get(name, sig.empty)
            default_ = p.default

            missing_value = default_ == sig.empty
            incompatible_value_type = not missing_value and is_incompatible(
                type(default_)
            )

            missing_annotation_type = type_ == sig.empty
            incompatible_annotation_type = (
                not missing_annotation_type and is_incompatible(type_)
            )

            if missing_annotation_type or incompatible_annotation_type:
                type_ = Any
                collect_imports(imports, Any)

            if not missing_value:
                if type_ is str or type(default_) is str:
                    default_ = f'"{default_}"'
                elif isinstance(default_, list):
                    default_ = f"field(default_factory=lambda: {default_})"
                elif isinstance(default_, dict):
                    default_ = f"field(default_factory=lambda: {default_})"

            missing_default = missing_value
            if (
                incompatible_annotation_type
                or incompatible_value_type
                or missing_default
            ):
                missing_default = True

            collect_imports(imports, type_)

            if missing_default:
                if incompatible_annotation_type:
                    default_ = f"MISSING  # {type_str(original_type)}"
                elif incompatible_value_type:
                    default_ = f"MISSING  # {type_str(type(p.default))}"
                else:
                    default_ = "MISSING"
                string_imports.add("from omegaconf import MISSING")

            params.append(
                Parameter(
                    name=name,
                    type_str=type_str(type_),
                    default=default_,
                )
            )
        classes_map[class_name] = ClassInfo(
            target=full_name,
            module=module.name,
            name=class_name,
            parameters=params,
        )

    template = jinja_env.get_template("module.j2")
    return template.render(
        imports=convert_imports(imports, string_imports),
        classes=module.classes,
        classes_map=classes_map,
        header=cfg.header,
    )


@hydra.main(config_name="configen_schema")
def main(cfg: Config):
    if cfg.init_config_dir is not None:
        init_config(cfg.init_config_dir)
        return

    if OmegaConf.is_missing(cfg.configen, "modules"):  # type: ignore
        log.error(
            dedent("""\

        Use --config-dir DIR --config-name NAME
        e.g:
        \tconfigen --config-dir conf --config-name configen

        If you have no config dir yet use init_config_dir=DIR to create an initial config dir.
        e.g:
        \tconfigen init_config_dir=conf
        """)
        )
        sys.exit(1)

    for module in cfg.configen.modules:
        code = generate_module(cfg=cfg.configen, module=module)
        save(cfg=cfg.configen, module=module.name, code=code)


if __name__ == "__main__":
    main()
