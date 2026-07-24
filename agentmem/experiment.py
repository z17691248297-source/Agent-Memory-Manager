from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4


OrderMode = Literal["baseline-first", "optimized-first", "randomized", "counterbalanced"]


IDENTITY_FIELDS = [
    "experiment_id",
    "run_id",
    "trial_id",
    "agent_id",
    "session_id",
    "scenario",
    "variant",
    "model",
    "seed",
    "timestamp",
    "git_commit",
]


@dataclass(frozen=True)
class ExperimentIdentity:
    experiment_id: str
    run_id: str
    trial_id: str
    agent_id: str
    session_id: str
    scenario: str
    variant: str
    model: str
    seed: int
    timestamp: str
    git_commit: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExperimentIdGenerator:
    def __init__(
        self,
        *,
        experiment_id: str | None = None,
        seed: int | None = None,
        git_commit: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        self.seed = int(seed if seed is not None else int(time.time()))
        self.rng = random.Random(self.seed)
        self.git_commit = git_commit or get_git_commit()
        self.timestamp = timestamp or utc_timestamp()
        self.experiment_id = experiment_id or self._id("exp", self.timestamp, self.git_commit, self.seed, uuid4().hex[:8])

    def identity(
        self,
        *,
        scenario: str,
        variant: str,
        model: str,
        trial_index: int,
        agent_index: int = 1,
    ) -> ExperimentIdentity:
        scenario_safe = safe_id(scenario)
        variant_safe = safe_id(variant)
        model_safe = safe_id(model)[:32] or "model"
        run_id = self._id("run", self.experiment_id, scenario_safe, variant_safe, model_safe)
        trial_id = self._id("trial", run_id, str(trial_index))
        agent_id = self._id("agent", trial_id, str(agent_index))
        session_id = self._id("session", trial_id, variant_safe, str(agent_index))
        return ExperimentIdentity(
            experiment_id=self.experiment_id,
            run_id=run_id,
            trial_id=trial_id,
            agent_id=agent_id,
            session_id=session_id,
            scenario=scenario,
            variant=variant,
            model=model,
            seed=self.seed,
            timestamp=utc_timestamp(),
            git_commit=self.git_commit,
        )

    def ordered_variants(self, variants: list[str], *, order: OrderMode, trial_index: int) -> list[str]:
        items = list(variants)
        if order == "baseline-first":
            return sorted(items, key=lambda value: 0 if value in {"baseline", "full_history"} else 1)
        if order == "optimized-first":
            return sorted(items, key=lambda value: 0 if value in {"optimized", "event_sourced_memory"} else 1)
        if order == "counterbalanced":
            return items if trial_index % 2 else list(reversed(items))
        if order == "randomized":
            local = random.Random(self.seed + trial_index)
            local.shuffle(items)
            return items
        raise ValueError(f"unsupported order: {order}")

    def _id(self, prefix: str, *parts: Any) -> str:
        raw = "|".join(str(part) for part in parts)
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        return f"{prefix}_{digest}"


def identity_from_env_or_new(
    *,
    scenario: str,
    variant: str,
    model: str,
    trial_index: int = 1,
    agent_index: int = 1,
) -> ExperimentIdentity:
    generator = ExperimentIdGenerator(
        experiment_id=os.getenv("AGENTMEM_EXPERIMENT_ID") or None,
        seed=int(os.getenv("AGENTMEM_SEED", "0") or 0),
        git_commit=os.getenv("AGENTMEM_GIT_COMMIT") or None,
    )
    return generator.identity(
        scenario=scenario,
        variant=variant,
        model=model,
        trial_index=trial_index,
        agent_index=agent_index,
    )


def identity_csv_fields(existing: list[str]) -> list[str]:
    fields = [field for field in existing if field not in IDENTITY_FIELDS]
    return [*IDENTITY_FIELDS, *fields]


def attach_identity(row: dict[str, Any], identity: ExperimentIdentity | dict[str, Any] | None) -> dict[str, Any]:
    output = dict(row)
    if identity is None:
        return output
    values = identity.to_dict() if hasattr(identity, "to_dict") else dict(identity)
    for field in IDENTITY_FIELDS:
        # Benchmark rows already use fields such as session_id and agent_id for
        # scenario-level isolation. Preserve those values and only fill missing
        # identity fields so the hardening pass stays backward compatible.
        output[field] = output.get(field) or values.get(field, "")
    return output


def manifest_base(
    *,
    experiment_id: str,
    config: dict[str, Any],
    config_hash: str,
    output_dir: Path,
    seed: int,
    models: list[str],
    scenarios: list[str],
    repeat: int,
) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "git_commit": get_git_commit(),
        "config_hash": config_hash,
        "dataset_hash": dataset_hash(Path("benchmarks/tasks")),
        "models": models,
        "model": models[0] if len(models) == 1 else "",
        "vllm_version": "",
        "scenarios": scenarios,
        "repeat": repeat,
        "seed": seed,
        "start_time": utc_timestamp(),
        "end_time": None,
        "validation_passed": False,
        "real_model": str(dict(config.get("llm") or {}).get("backend", "")).lower() not in {"mock", "fake", "local"},
        "real_gpu_metrics": False,
        "openEuler_userspace_container_verified": False,
        "openEuler_native_host_verified": False,
        "Ubuntu_model_server_verified": False,
        "full_openEuler_gpu_deployment_verified": False,
        "output_dir": str(output_dir),
    }


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return output


def utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def get_git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unavailable"


def dataset_hash(path: Path) -> str:
    if not path.exists():
        return "unavailable"
    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    for item in files:
        digest.update(str(item.relative_to(path)).encode("utf-8"))
        digest.update(item.read_bytes())
    return digest.hexdigest()


def safe_id(value: str) -> str:
    text = "".join(ch if ch.isalnum() else "_" for ch in str(value).strip())
    return "_".join(part for part in text.split("_") if part).lower()
