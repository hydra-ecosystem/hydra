# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from dataclasses import dataclass, field

from hydra.core.config_store import ConfigStore
from omegaconf import II


@dataclass
class RedisConf:
    # host address via REDIS_HOST environment variable, default: localhost
    host: str = II("oc.env:REDIS_HOST,localhost")
    # port via REDIS_PORT environment variable, default: 6379
    port: int = II("oc.env:REDIS_PORT,'6379'")
    # database via REDIS_DB environment variable, default: 0
    db: str | None = II("oc.env:REDIS_DB,'0'")
    # password via REDIS_PASSWORD environment variable, default: no password
    password: str | None = II("oc.env:REDIS_PASSWORD,null")
    # enable/disable SSL, via REDIS_SSL environment variable, default False
    ssl: bool = II("oc.env:REDIS_SSL,'False'")
    # path to custom certs, via REDIS_SSL_CA_CERTS env veriable, default none
    ssl_ca_certs: str | None = II("oc.env:REDIS_SSL_CA_CERTS,null")
    # switch to run without redis server in single thread, for testing purposes only
    mock: bool = II("oc.env:REDIS_MOCK,'False'")


@dataclass
class EnqueueConf:
    # maximum runtime of the job before it's killed (e.g. "1d" for 1 day, units: d/h/m/s), default: no limit
    job_timeout: str | None = None
    # maximum queued time before the job before is discarded (e.g. "1d" for 1 day, units: d/h/m/s), default: no limit
    ttl: str | None = None
    # how long successful jobs and their results are kept (e.g. "1d" for 1 day, units: d/h/m/s), default: no limit
    result_ttl: str | None = None
    # specifies how long failed jobs are kept (e.g. "1d" for 1 day, units: d/h/m/s), default: no limit
    failure_ttl: str | None = None
    # place job at the front of the queue, instead of the back
    at_front: bool = False
    # job id, will be overidden automatically by a uuid unless specified explicitly
    job_id: str | None = None
    # description, will be overidden automatically unless specified explicitly
    description: str | None = None


@dataclass
class RQLauncherConf:
    _target_: str = "hydra_plugins.hydra_rq_launcher.rq_launcher.RQLauncher"
    # enqueue configuration
    enqueue: EnqueueConf = field(default_factory=EnqueueConf)
    # queue name
    queue: str = "default"
    # redis configuration
    redis: RedisConf = field(default_factory=RedisConf)
    # stop after enqueueing by raising custom exception
    stop_after_enqueue: bool = False
    # wait time in seconds when polling results
    wait_polling: float = 1.0


ConfigStore.instance().store(
    group="hydra/launcher", name="rq", node=RQLauncherConf, provider="rq_launcher"
)
