from __future__ import annotations

import json
from pathlib import Path


class SensitiveDataError(ValueError):
    pass


SENSITIVE_KEY_FRAGMENTS = (
    "guid",
    "email",
    "oauth",
    "access_token",
    "refresh_token",
    "authorization",
    "client_secret",
    "client_id",
    "github_token",
    "gh_secret_token",
)


def assert_public_data(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if any(fragment in normalized for fragment in SENSITIVE_KEY_FRAGMENTS):
                raise SensitiveDataError(f"sensitive key detected at {path}.{key}")
            assert_public_data(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_public_data(child, f"{path}[{index}]")


def _serialized(value: object) -> bytes:
    assert_public_data(value)
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def write_json(path: Path, value: object) -> bool:
    content = _serialized(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return False
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_bytes(content)
    temp.replace(path)
    return True
