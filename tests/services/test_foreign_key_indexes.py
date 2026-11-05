# tests/services/test_foreign_key_indexes.py
"""Every foreign key's child column leads an index or unique key, except ``ai_outputs``."""

from sqlalchemy import UniqueConstraint

from weatherbot.services.persistence.tables import Base

UNINDEXED_AI_OUTPUT_FKS = frozenset(
    {
        ("ai_outputs", "assessment_id"),
        ("ai_outputs", "call_id"),
    }
)


def _leading_indexed_columns(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    leading: set[str] = set()
    pk_cols = list(table.primary_key.columns)
    if pk_cols:
        leading.add(pk_cols[0].name)
    for index in table.indexes:
        cols = list(index.columns)
        if cols:
            leading.add(cols[0].name)
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint):
            cols = list(constraint.columns)
            if cols:
                leading.add(cols[0].name)
    for col in table.columns:
        if col.unique or col.index:
            leading.add(col.name)
    return leading


def test_every_foreign_key_child_column_leads_an_index_or_unique_key() -> None:
    missing: set[tuple[str, str]] = set()
    for table_name, table in Base.metadata.tables.items():
        leading = _leading_indexed_columns(table_name)
        for fk in table.foreign_key_constraints:
            cols = list(fk.columns)
            assert len(cols) == 1
            child_col = cols[0].name
            if child_col not in leading:
                missing.add((table_name, child_col))

    assert missing == UNINDEXED_AI_OUTPUT_FKS
