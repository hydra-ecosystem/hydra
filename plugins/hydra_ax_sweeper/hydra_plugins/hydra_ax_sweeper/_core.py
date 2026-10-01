# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import logging
from dataclasses import dataclass
from typing import (
    Any,
    Iterable,
    Literal,
    Mapping,
    cast,
)

from ax.api.client import Client  # type: ignore
from ax.api.configs import ChoiceParameterConfig, RangeParameterConfig  # type: ignore
from ax.core import types as ax_types  # type: ignore
from ax.exceptions.core import SearchSpaceExhausted, UnsupportedError  # type: ignore
from hydra.core.override_parser.overrides_parser import OverridesParser
from hydra.core.override_parser.types import IntervalSweep, Override, Transformer
from hydra.core.plugins import Plugins
from hydra.plugins.launcher import Launcher
from hydra.plugins.sweeper import Sweeper
from hydra.types import HydraContext, TaskFunction
from omegaconf import DictConfig, OmegaConf

from ._earlystopper import EarlyStopper
from .config import AxConfig, ClientConfig, ExperimentConfig

log = logging.getLogger(__name__)

AxRangeParameterType = Literal["float", "int"]
AxChoiceParameterType = Literal["float", "int", "str", "bool"]
AxParameterConfig = RangeParameterConfig | ChoiceParameterConfig
AxMetricValue = float | tuple[float, float]
AxRawData = Mapping[str, AxMetricValue]


@dataclass
class Trial:
    overrides: list[str]
    trial_index: int


@dataclass
class TrialBatch:
    list_of_trials: list[Trial]
    is_search_space_exhausted: bool


def encoder_parameters_into_string(parameters: list[dict[str, Any]]) -> str:
    """Convert a list of params into a string"""
    mandatory_keys = {"name", "type", "bounds", "values", "value"}
    parameter_log_string = ""
    for parameter in parameters:
        parameter_log_string += "\n"
        parameter_log_string += f"{parameter['name']}: {parameter['type']}="
        if parameter["type"] == "range":
            parameter_log_string += f"{parameter['bounds']}"
        elif parameter["type"] == "choice":
            parameter_log_string += f"{parameter['values']}"
        elif parameter["type"] == "fixed":
            parameter_log_string += f"{parameter['value']}"

        for key, value in parameter.items():
            if key not in mandatory_keys:
                parameter_log_string += f", {key} = {value}"
    return parameter_log_string


def map_params_to_arg_list(
    params: Mapping[str, str | float | int | bool],
) -> list[str]:
    """Method to map a dictionary of params to a list of string arguments"""
    arg_list = []
    for key in params:
        arg_list.append(str(key) + "=" + str(params[key]))
    return arg_list


def get_ax_choice_parameter_type(values: Iterable[Any]) -> AxChoiceParameterType:
    value_types = {type(value) for value in values}
    if value_types == {bool}:
        return "bool"
    if value_types <= {int}:
        return "int"
    if value_types <= {int, float}:
        return "float"
    if value_types == {str}:
        return "str"
    raise ValueError(f"Unsupported mixed Ax parameter value types: {value_types}")


def create_ax_parameter_config(param: dict[Any, Any]) -> AxParameterConfig:
    name = param["name"]
    if param["type"] == "range":
        bounds = param["bounds"]
        range_parameter_type: AxRangeParameterType = (
            "int" if all(type(bound) is int for bound in bounds) else "float"
        )
        return RangeParameterConfig(
            name=name,
            bounds=cast(tuple[float, float], tuple(bounds)),
            parameter_type=range_parameter_type,
            scaling="log" if param.get("log_scale") else None,
        )

    if param["type"] == "choice":
        values = param["values"]
        choice_parameter_type = get_ax_choice_parameter_type(values)
        is_ordered = param.get("is_ordered", choice_parameter_type != "str")
    elif param["type"] == "fixed":
        values = [param["value"]]
        choice_parameter_type = get_ax_choice_parameter_type(values)
        is_ordered = None
    else:
        raise ValueError(f"Unexpected Ax parameter type: {param['type']}")

    if choice_parameter_type == "float":
        values = [float(value) for value in values]
    return ChoiceParameterConfig(
        name=name,
        values=cast(Any, values),
        parameter_type=choice_parameter_type,
        is_ordered=is_ordered,
    )


def create_ax_raw_data(value: Any, objective_name: str, is_noisy: bool) -> AxRawData:
    def normalize_metric(metric_value: Any) -> AxMetricValue:
        assert isinstance(metric_value, (int, float, tuple))
        if isinstance(metric_value, (int, float)):
            mean = float(metric_value)
            return mean if is_noisy else (mean, 0.0)

        assert len(metric_value) == 2
        mean, sem = metric_value
        assert isinstance(mean, (int, float))
        assert sem is None or isinstance(sem, (int, float))
        return (float(mean), float("nan") if sem is None else float(sem))

    assert isinstance(value, (int, float, tuple, dict))
    if isinstance(value, dict):
        raw_data: dict[str, AxMetricValue] = {}
        for metric_name, metric_value in value.items():
            assert isinstance(metric_name, str)
            raw_data[metric_name] = normalize_metric(metric_value)
        return raw_data

    return {objective_name: normalize_metric(value)}


def get_one_batch_of_trials(
    ax_client: Client,
    num_max_trials_to_do: int,
) -> TrialBatch:
    """Returns a TrialBatch that contains a list of trials that can be
    run in parallel. TrialBatch also flags if the search space is exhausted."""

    try:
        trials = ax_client.get_next_trials(max_trials=num_max_trials_to_do)
    except SearchSpaceExhausted:
        return TrialBatch(list_of_trials=[], is_search_space_exhausted=True)

    list_of_trials = [
        Trial(
            overrides=map_params_to_arg_list(params=parameters),
            trial_index=trial_index,
        )
        for trial_index, parameters in trials.items()
    ]
    return TrialBatch(
        list_of_trials=list_of_trials,
        is_search_space_exhausted=len(list_of_trials) == 0,
    )


class CoreAxSweeper(Sweeper):
    """Class to interface with the Ax Platform"""

    def __init__(self, ax_config: AxConfig, max_batch_size: int | None):
        self.config: DictConfig | None = None
        self.launcher: Launcher | None = None
        self.hydra_context: HydraContext | None = None

        self.job_results = None
        self.experiment: ExperimentConfig = ax_config.experiment
        self.early_stopper: EarlyStopper = EarlyStopper(
            max_epochs_without_improvement=ax_config.early_stop.max_epochs_without_improvement,
            epsilon=ax_config.early_stop.epsilon,
            minimize=ax_config.early_stop.minimize,
        )
        self.ax_client_config: ClientConfig = ax_config.client
        self.max_trials = ax_config.max_trials
        self.ax_params: DictConfig = OmegaConf.create({})
        if hasattr(ax_config, "params"):
            self.ax_params.update(ax_config.params)
        self.sweep_dir: str
        self.job_idx: int | None = None
        self.max_batch_size = max_batch_size
        self.is_noisy: bool = ax_config.is_noisy

    def setup(
        self,
        *,
        hydra_context: HydraContext,
        task_function: TaskFunction,
        config: DictConfig,
    ) -> None:
        self.config = config
        self.hydra_context = hydra_context
        self.launcher = Plugins.instance().instantiate_launcher(
            config=config, hydra_context=hydra_context, task_function=task_function
        )
        self.sweep_dir = config.hydra.sweep.dir

    def sweep(self, arguments: list[str]) -> None:
        self.job_idx = 0
        ax_client = self.setup_ax_client(arguments)

        num_trials_left = self.max_trials
        is_search_space_exhausted = False
        # Ax throws an exception if the search space is exhausted. We catch
        # the exception and set the flag to True

        best_parameters = {}
        while num_trials_left > 0 and not is_search_space_exhausted:
            num_trials_to_request = min(num_trials_left, self.max_batch_size or 5)
            trial_batch = get_one_batch_of_trials(
                ax_client=ax_client,
                num_max_trials_to_do=num_trials_to_request,
            )

            list_of_trials_to_launch = trial_batch.list_of_trials[:num_trials_left]
            is_search_space_exhausted = trial_batch.is_search_space_exhausted

            log.info(
                "AxSweeper is launching {} jobs".format(len(list_of_trials_to_launch))
            )

            self.sweep_over_batches(
                ax_client=ax_client, list_of_trials=list_of_trials_to_launch
            )

            num_trials_left -= len(list_of_trials_to_launch)

            best_point = self.get_best_point(ax_client)
            if best_point is not None:
                best_parameters, metric = best_point
                if self.early_stopper.should_stop(metric, best_parameters):
                    break

            if is_search_space_exhausted:
                log.info("Ax has exhausted the search space")
                break

        results_to_serialize = {"optimizer": "ax", "ax": best_parameters}
        OmegaConf.save(
            OmegaConf.create(results_to_serialize),
            f"{self.sweep_dir}/optimization_results.yaml",
        )
        log.info("Best parameters: " + str(best_parameters))

    def sweep_over_batches(
        self, ax_client: Client, list_of_trials: list[Trial]
    ) -> None:
        assert self.launcher is not None
        assert self.job_idx is not None

        chunked_batches = self.chunks(list_of_trials, self.max_batch_size)
        for batch in chunked_batches:
            overrides = [x.overrides for x in batch]
            self.validate_batch_is_legal(overrides)
            rets = self.launcher.launch(
                job_overrides=overrides, initial_job_idx=self.job_idx
            )
            self.job_idx += len(rets)
            for idx in range(len(batch)):
                val: Any = rets[idx].return_value
                # Ax expects a measured value (int or float), which can optionally
                # be given in a tuple along with the error of that measurement.
                # Alternatively, the task function can return a dict whose values
                # represent multiple metrics, where each key is the name of the metric
                # and the item can be an int, float or tuple.
                # is_noisy specifies how Ax should behave when not given an
                # error value: true means unknown error, false means zero error.
                raw_data = create_ax_raw_data(
                    val, self.experiment.objective_name, self.is_noisy
                )
                ax_client.complete_trial(
                    trial_index=batch[idx].trial_index, raw_data=raw_data
                )

    def get_best_point(
        self, ax_client: Client
    ) -> tuple[Mapping[str, Any], float] | None:
        try:
            best_parameters, metrics, _, _ = ax_client.get_best_parameterization(
                use_model_predictions=False
            )
        except (AssertionError, UnsupportedError):
            return None

        metric = metrics.get(self.experiment.objective_name)
        if metric is None:
            return None
        if isinstance(metric, tuple):
            metric = metric[0]
        return best_parameters, float(metric)

    def setup_ax_client(self, arguments: list[str]) -> Client:
        """Method to setup the Ax Client"""
        parameters: list[dict[Any, Any]] = []
        for key, value in self.ax_params.items():
            param = OmegaConf.to_container(value, resolve=True)
            assert isinstance(param, dict)
            if param["type"] == "range":
                bounds = param["bounds"]
                if not (all(isinstance(x, int) for x in bounds)):
                    # Type mismatch. Promote all to float
                    param["bounds"] = [float(x) for x in bounds]
            parameters.append(param)
            parameters[-1]["name"] = key
        commandline_params = self.parse_commandline_args(arguments)
        for cmd_param in commandline_params:
            for param in parameters:
                if param["name"] == cmd_param["name"]:
                    for key, value in cmd_param.items():
                        param[key] = value
                    break
            else:
                parameters.append(cmd_param)

        log.info(
            f"AxSweeper is optimizing the following parameters: {encoder_parameters_into_string(parameters)}"
        )

        if not self.ax_client_config.verbose_logging:
            logging.getLogger("ax.api.client").setLevel(logging.WARNING)
        ax_client = Client(random_seed=self.ax_client_config.random_seed)
        ax_client.configure_experiment(
            parameters=[create_ax_parameter_config(param) for param in parameters],
            parameter_constraints=self.experiment.parameter_constraints,
            name=self.experiment.name,
        )
        if self.experiment.status_quo is not None:
            ax_client.attach_baseline(
                parameters=cast(Mapping[str, Any], self.experiment.status_quo)
            )
        ax_client.configure_optimization(
            objective=(
                f"-{self.experiment.objective_name}"
                if self.experiment.minimize
                else self.experiment.objective_name
            ),
            outcome_constraints=self.experiment.outcome_constraints,
        )

        return ax_client

    def parse_commandline_args(
        self, arguments: list[str]
    ) -> list[dict[str, ax_types.TParamValue | list[ax_types.TParamValue]]]:
        """Method to parse the command line arguments and convert them into Ax parameters"""
        parser = OverridesParser.create()
        parsed = parser.parse_overrides(arguments)
        parameters: list[dict[str, Any]] = []
        for override in parsed:
            if override.is_sweep_override():
                if override.is_choice_sweep():
                    param = create_choice_param_from_choice_override(override)
                elif override.is_range_sweep():
                    param = create_choice_param_from_range_override(override)
                elif override.is_interval_sweep():
                    param = create_range_param_using_interval_override(override)
                else:
                    raise ValueError(f"Unsupported sweep override: {override}")
            elif not override.is_hydra_override():
                param = create_fixed_param_from_element_override(override)
            else:
                continue
            parameters.append(param)

        return parameters

    @staticmethod
    def chunks(batch: list[Any], n: int | None) -> Iterable[list[Any]]:
        """
        Chunk the batch into chunks of upto to n items (each)
        """
        if n is None:
            n = len(batch)
        if n < 1:
            raise ValueError("n must be an integer greater than 0")
        for i in range(0, len(batch), n):
            yield batch[i : i + n]


def create_range_param_using_interval_override(override: Override) -> dict[str, Any]:
    key = override.get_key_element()
    value = override.value()
    assert isinstance(value, IntervalSweep)
    param = {
        "name": key,
        "type": "range",
        "bounds": [value.start, value.end],
        "log_scale": "log" in value.tags,
    }
    return param


def create_choice_param_from_choice_override(override: Override) -> dict[str, Any]:
    key = override.get_key_element()
    param = {
        "name": key,
        "type": "choice",
        "values": list(override.sweep_iterator(transformer=Transformer.encode)),
    }
    return param


def create_choice_param_from_range_override(override: Override) -> dict[str, Any]:
    key = override.get_key_element()
    param = {
        "name": key,
        "type": "choice",
        "values": [val for val in override.sweep_iterator()],
    }

    return param


def create_fixed_param_from_element_override(override: Override) -> dict[str, Any]:
    key = override.get_key_element()
    param = {
        "name": key,
        "type": "fixed",
        "value": override.value(),
    }

    return param
