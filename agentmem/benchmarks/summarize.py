from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentmem.metrics.summarizer import summarize_results


def main() -> None:
    outputs = summarize_results(ROOT / "results")
    print(f"summary written to {outputs['summary_csv']}")
    print(f"report written to {outputs['report_md']}")


if __name__ == "__main__":
    main()
