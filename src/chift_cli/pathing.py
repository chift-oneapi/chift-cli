from __future__ import annotations


def path_parameter_names(path: str) -> list[str]:
    return [
        part[1:-1]
        for part in path.split("/")
        if part.startswith("{") and part.endswith("}")
    ]
