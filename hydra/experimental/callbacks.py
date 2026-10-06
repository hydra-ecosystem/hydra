# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

from hydra._internal.deprecation_warning import deprecation_warning
from hydra.errors import Hydra15MigrationWarning
from hydra.experimental.callback import Callback


class LogJobReturnCallback(Callback):
    """Deprecated no-op compatibility stub; removed in Hydra 1.5."""

    def __init__(self) -> None:
        deprecation_warning(
            "LogJobReturnCallback no longer has any effect and will be removed "
            "in Hydra 1.5. Hydra logs task exceptions to per-job logs without it.",
            stacklevel=2,
            category=Hydra15MigrationWarning,
        )
