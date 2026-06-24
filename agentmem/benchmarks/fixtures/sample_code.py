from pathlib import Path


class DemoAgent:
    def run(self, text: str) -> str:
        return text.strip()


def helper_with_a_very_long_function_name_that_should_be_reviewed() -> bool:
    # TODO: split this helper when logic becomes real.
    return Path(".").exists()
