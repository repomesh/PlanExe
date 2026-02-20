from collections.abc import Mapping, MutableMapping

ENV_PLANEXE_WORKER_ID = "PLANEXE_WORKER_ID"
ENV_RAILWAY_REPLICA_REGION = "RAILWAY_REPLICA_REGION"
ENV_RAILWAY_REPLICA_ID = "RAILWAY_REPLICA_ID"


def _normalized_env_value(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def resolve_worker_id(env: Mapping[str, str]) -> str:
    """Resolve a stable worker id from explicit or Railway replica variables."""
    explicit_worker_id = _normalized_env_value(env.get(ENV_PLANEXE_WORKER_ID))
    if explicit_worker_id:
        return explicit_worker_id

    replica_region = _normalized_env_value(env.get(ENV_RAILWAY_REPLICA_REGION))
    replica_id = _normalized_env_value(env.get(ENV_RAILWAY_REPLICA_ID))
    if replica_region and replica_id:
        return f"{replica_region}_{replica_id}"

    raise ValueError(
        "Unable to determine worker identity. "
        f"Set {ENV_PLANEXE_WORKER_ID}, or provide both "
        f"{ENV_RAILWAY_REPLICA_REGION} and {ENV_RAILWAY_REPLICA_ID}."
    )


def resolve_and_set_worker_id(env: MutableMapping[str, str]) -> str:
    worker_id = resolve_worker_id(env)
    env[ENV_PLANEXE_WORKER_ID] = worker_id
    return worker_id
