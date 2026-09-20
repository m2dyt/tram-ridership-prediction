"""OpenAPI validation shared by input adapters; never imported by the core."""

import json
import re
from datetime import datetime
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker


def strict_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON property")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("Non-finite JSON number")

    return json.loads(data, object_pairs_hook=unique, parse_constant=reject_constant)


class Contract:
    def __init__(self, path: Path):
        self.document = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.formats = FormatChecker()
        self.formats.checks("date-time", raises=(ValueError, TypeError))(self.timestamp)

    @staticmethod
    def timestamp(value):
        if not isinstance(value, str):
            return True  # Type validation belongs to the schema.
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)",
            value,
        ):
            return False
        return datetime.fromisoformat(value.upper().replace("Z", "+00:00")).tzinfo is not None

    def resolve(self, document):
        if "$ref" not in document:
            return document
        result = self.document
        for part in document["$ref"].removeprefix("#/").split("/"):
            result = result[part]
        return result

    def validator(self, schema):
        return Draft202012Validator(
            {"components": self.document["components"], **schema}, format_checker=self.formats
        )

    def validate(self, name, value):
        self.validator({"$ref": f"#/components/schemas/{name}"}).validate(value)
