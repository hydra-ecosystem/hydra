# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import pickle
from pathlib import Path
from typing import Any

import submitit
from hydra._internal.cloudpickle import SourcePickler


class SourceSubmission(submitit.helpers.DelayedSubmission):
    def dump(self, filepath: str | Path) -> None:
        with open(filepath, "wb") as stream:
            SourcePickler(stream, protocol=pickle.HIGHEST_PROTOCOL).dump(self)

    def __reduce__(self) -> Any:
        # Workers load Submitit's ordinary submission type, including its
        # complete timeout/checkpoint state and shared function/argument graph.
        return (
            submitit.helpers.DelayedSubmission,
            (self.function, *self.args),
            self.__dict__,
        )


class SourceExecutor(submitit.AutoExecutor):
    def _internal_process_submissions(
        self, delayed_submissions: list[submitit.helpers.DelayedSubmission]
    ) -> list[submitit.Job[Any]]:
        submissions: list[submitit.helpers.DelayedSubmission] = []
        for original in delayed_submissions:
            submission = SourceSubmission.__new__(SourceSubmission)
            submission.__dict__.update(original.__dict__)
            submissions.append(submission)
        return super()._internal_process_submissions(submissions)
