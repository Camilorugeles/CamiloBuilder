from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


SCHEMA = Path(__file__).resolve().parent / "schemas/deployment-connectors.schema.json"


class DeploymentConfigurationError(ValueError): pass


def load_deployment_configuration(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise DeploymentConfigurationError("Unsafe or missing deployment configuration")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DeploymentConfigurationError("Invalid deployment configuration") from error
    errors = sorted(Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).iter_errors(document), key=lambda e: tuple(e.path))
    if errors:
        raise DeploymentConfigurationError(errors[0].message)
    aliases = [item["alias"] for item in document["connectors"]]
    if aliases != sorted(set(aliases)):
        raise DeploymentConfigurationError("Connector aliases must be sorted and unique")
    for item in document["connectors"]:
        permissions = item["permissions"]
        if permissions != sorted(set(permissions)):
            raise DeploymentConfigurationError("Connector permissions must be sorted and unique")
    return document
