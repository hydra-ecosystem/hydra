# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import logging
import os
import sys

from hydra.plugins.completion_plugin import CompletionPlugin

log = logging.getLogger(__name__)


class BashCompletion(CompletionPlugin):
    def install(self) -> None:
        # Record the old rule for uninstalling
        script = (
            f"export _HYDRA_OLD_COMP=$(complete -p {self._get_exec()} 2> /dev/null)\n"
        )
        script += """hydra_bash_completion()
{
    words=($COMP_LINE)
    if [ "${words[0]}" == "python" ]; then
        if (( ${#words[@]} < 2 )); then
            return
        fi
        if [[ "${words[1]}" == -* ]]; then
            return
        fi
        file_path=$(pwd)/${words[1]}
        if [ ! -f "$file_path" ]; then
            return
        fi
        if ! grep -Fq -- "@hydra.main" "$file_path"; then
            return
        fi
        helper="${words[0]} ${words[1]}"
    else
        helper="${words[0]}"
        true
    fi

    EXECUTABLE=($(command -v $helper))
    if [ "$HYDRA_COMP_DEBUG" == "1" ]; then
        printf "EXECUTABLE_FIRST='${EXECUTABLE[0]}'\\n"
    fi
    if ! [ -x "${EXECUTABLE[0]}" ]; then
        false
    fi

    if [ $? == 0 ]; then
        choices=$( COMP_POINT=$COMP_POINT COMP_LINE=$COMP_LINE $helper -sc query=bash)
        word=${words[$COMP_CWORD]}

        if [ "$HYDRA_COMP_DEBUG" == "1" ]; then
            printf "\\n"
            printf "COMP_LINE='$COMP_LINE'\\n"
            printf "COMP_POINT='$COMP_POINT'\\n"
            printf "Word='$word'\\n"
            printf "Output suggestions:\\n"
            printf "\\t%s\\n" ${choices[@]}
        fi
        COMPREPLY=($( compgen -o nospace -o default -W "$choices" -- "$word" ));
    fi
}

COMP_WORDBREAKS=${COMP_WORDBREAKS//=}
COMP_WORDBREAKS=$COMP_WORDBREAKS complete -o nospace -o default -F hydra_bash_completion """
        print(script + self._get_exec())

    def uninstall(self) -> None:
        print("unset hydra_bash_completion")
        print(os.environ.get("_HYDRA_OLD_COMP", ""))
        print("unset _HYDRA_OLD_COMP")

    @staticmethod
    def provides() -> str:
        return "bash"

    def query(self, config_name: str | None) -> None:
        line = os.environ["COMP_LINE"]
        # key = os.environ["COMP_POINT "] if "COMP_POINT " in os.environ else len(line)

        # if key == "":
        #     key = 0
        # if isinstance(key, str):
        #     key = int(key)

        # currently key is ignored.
        line = self.strip_python_or_app_name(line)
        print(" ".join(self._query(config_name=config_name, line=line)))

    @staticmethod
    def help(command: str) -> str:
        assert command in ["install", "uninstall"]
        return f'eval "$({{}} -sc {command}=bash)"'

    @staticmethod
    def _get_exec() -> str:
        if sys.argv[0].endswith(".py"):
            return "python"
        else:
            # Running as an installed app (setuptools entry point)
            executable = os.path.basename(sys.argv[0])
            return executable
