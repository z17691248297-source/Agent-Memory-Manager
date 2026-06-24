from __future__ import annotations

from pathlib import Path

from common import RESULTS_DIR, baseline_memory_factory, run_agent_benchmark


def main() -> None:
    path = run_agent_benchmark(
        memory_factory=baseline_memory_factory,
        output_csv=RESULTS_DIR / "baseline.csv",
        experiment="baseline",
    )
    print(f"baseline metrics written to {Path(path)}")


if __name__ == "__main__":
    main()
