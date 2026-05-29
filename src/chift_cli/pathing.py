from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schema import Operation


def path_parameter_names(operation: "Operation") -> list[str]:
    declared = {
        parameter["name"]
        for parameter in operation.raw.get("parameters", [])
        if parameter.get("in") == "path" and "name" in parameter
    }
    return [
        part[1:-1]
        for part in operation.path.split("/")
        if part.startswith("{") and part.endswith("}") and part[1:-1] in declared
    ]
