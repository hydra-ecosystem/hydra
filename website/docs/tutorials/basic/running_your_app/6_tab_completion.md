---
id: tab_completion
title: Tab completion
sidebar_label: Tab completion
---

Tab completion can complete config groups, config nodes and values.
To complete paths, start them with `/` or `./`.

Completion also suggests [override aliases](/advanced/override_aliases.md).
Key aliases are suggested with `=`, while complete-expression aliases are
suggested as bare tokens. Completing a key alias's value uses its target key or
config group and preserves the alias spelling.

See this short video demonstration of tab completion:

import Script from '@site/src/components/Script.jsx';

<Script id="asciicast-272604" src="https://asciinema.org/a/272604.js" async></Script>


### Install tab completion
Get the exact command to install the completion from `--hydra-help`.
Currently, Bash, zsh and Fish are supported.
We are relying on the community to implement tab completion plugins for additional shells.

Hydra tab completion supports applications invoked as a Python script, such as
`python my_app.py`, or through an installed console entry point, such as
`my_app`. The `python -m my_app` invocation form is not supported because Hydra
cannot determine passively whether a module launches a Hydra application. A
module does not necessarily correspond to a regular source file and may, for
example, be loaded from a zip archive. For a packaged application, follow the
[Application packaging](/advanced/packaging.md) guidance to define and use a
console entry point instead.

#### Fish instructions
Fish support requires version >= 3.1.2.
Previous versions will work but add an extra space after `.`.

Because the fish shell implements special behavior for expanding words prefixed
with a tilde character '~', command-line completion does not work for
[tilde deletions](/advanced/override_grammar/basic.md#modifying-the-defaults-list).

#### Zsh instructions
Zsh is compatible with the existing Bash shell completion by appending
```
autoload -Uz bashcompinit && bashcompinit
```
to the `.zshrc` file after `compinit`, restarting the shell and then using the commands provided for Bash.

Because the zsh shell implements special behavior for expanding words prefixed
with a tilde character '~', command-line completion does not work for
[tilde deletions](/advanced/override_grammar/basic.md#modifying-the-defaults-list).
