# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import logging

from hydra.core.config_loader import ConfigLoader
from hydra.plugins.completion_plugin import CompletionPlugin

log = logging.getLogger(__name__)


class ZshCompletion(CompletionPlugin):
    def __init__(self, config_loader: ConfigLoader):
        super().__init__(config_loader)
        from hydra._internal.core_plugins.bash_completion import BashCompletion

        self.delegate = BashCompletion(config_loader)

    def install(self) -> None:
        self.delegate.install()

    def uninstall(self) -> None:
        self.delegate.uninstall()

    @staticmethod
    def provides() -> str:
        return "zsh"

    def query(self, config_name: str | None) -> None:
        self.delegate.query(config_name)

    @staticmethod
    def help(command: str) -> str:
        assert command in ["install", "uninstall"]
        extra_description = (
            "Zsh is compatible with the Bash shell completion, see the [documentation]"
            "(https://hydra.cc/docs/1.2/tutorials/basic/running_your_app/tab_completion#zsh-instructions)"
            " for details.\n    "
        )
        command_text = f'eval "$({{}} -sc {command}=bash)"'
        if command == "install":
            return extra_description + command_text
        return command_text

    @staticmethod
    def _get_exec() -> str:
        from hydra._internal.core_plugins.bash_completion import BashCompletion

        return BashCompletion._get_exec()
