"""Migrations must match the models.

The test suite builds its schema with `Base.metadata.create_all`, but production
builds it with Alembic. Nothing else in the suite would notice if the two drifted,
and that drift only ever surfaces as a production incident — so compare the
Postgres DDL each one produces, column by column.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base

BACKEND_ROOT = Path(__file__).resolve().parent.parent
NON_COLUMN_LINES = ("CREATE TABLE", "PRIMARY KEY", "FOREIGN KEY", "UNIQUE (", "CONSTRAINT", ")")
COLUMN_RE = re.compile(r"^(\w+)\s+([A-Z].*?),?$")


def _parse_columns(body: str) -> dict[str, str]:
    columns = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or line.upper().startswith(NON_COLUMN_LINES):
            continue
        match = COLUMN_RE.match(line)
        if match:
            columns[match.group(1)] = re.sub(r"\s+", " ", match.group(2)).strip().lower()
    return columns


def _model_schema() -> dict[str, dict[str, str]]:
    dialect = postgresql.dialect()
    schema = {}
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        schema[table.name] = _parse_columns(ddl.split("(", 1)[1])
    return schema


def _migration_schema() -> dict[str, dict[str, str]]:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic offline render failed:\n{result.stderr}")

    schema: dict[str, dict[str, str]] = {}
    for name, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", result.stdout, re.S):
        schema[name] = _parse_columns(body)
    for table, column, definition in re.findall(
        r"ALTER TABLE (\w+) ADD COLUMN (\w+) (.*?);", result.stdout
    ):
        schema.setdefault(table, {})[column] = re.sub(r"\s+", " ", definition).strip().lower()
    schema.pop("alembic_version", None)
    return schema


def _type_of(definition: str) -> str:
    """Column type, ignoring server defaults and nullability."""
    return re.sub(r" default '.*?'::\w+", "", definition).replace(" not null", "").strip()


def _is_not_null(definition: str) -> bool:
    return "not null" in definition


def test_migrations_match_models():
    models_schema = _model_schema()
    migrations_schema = _migration_schema()

    assert set(models_schema) == set(migrations_schema), (
        f"table drift: models-only={set(models_schema) - set(migrations_schema)}, "
        f"migrations-only={set(migrations_schema) - set(models_schema)}"
    )

    problems = []
    for table, model_columns in models_schema.items():
        migration_columns = migrations_schema[table]
        assert set(model_columns) == set(migration_columns), (
            f"{table} column drift: models-only={set(model_columns) - set(migration_columns)}, "
            f"migrations-only={set(migration_columns) - set(model_columns)}"
        )
        for column, model_definition in model_columns.items():
            migration_definition = migration_columns[column]
            if _type_of(model_definition) != _type_of(migration_definition):
                problems.append(
                    f"{table}.{column} type: model={_type_of(model_definition)!r} "
                    f"migration={_type_of(migration_definition)!r}"
                )
            elif _is_not_null(model_definition) != _is_not_null(migration_definition):
                problems.append(
                    f"{table}.{column} nullability: model={model_definition!r} "
                    f"migration={migration_definition!r}"
                )
    assert not problems, "migration/model drift:\n" + "\n".join(problems)


def test_drift_check_actually_inspects_the_schema():
    """Guard the guard: a parser that silently matches nothing would pass above."""
    models_schema = _model_schema()
    assert len(models_schema) >= 8
    assert sum(len(columns) for columns in models_schema.values()) >= 70
    assert "created_at" in models_schema["users"], "column parser dropped created_at"
