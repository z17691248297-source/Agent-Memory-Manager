from __future__ import annotations

from pathlib import Path

from common import RESULTS_DIR, optimized_memory_factory, run_agent_benchmark


def main() -> None:
    path = run_agent_benchmark(
        memory_factory=optimized_memory_factory,
        output_csv=RESULTS_DIR / "optimized.csv",
        experiment="full_agentmem_tool_system",
    )
    print(f"optimized metrics written to {Path(path)}")


if __name__ == "__main__":
    main()
