# Contributing

- Keep benchmarks reproducible: record config, seed, model endpoint, git commit, and validation output.
- Do not commit private model paths, public IPs, or API keys.
- Do not use mock/fake data for release claims.
- Run `python -m pytest -q`, `git diff --check`, and `bash scripts/reproduce_all.sh --smoke` before submitting changes.
