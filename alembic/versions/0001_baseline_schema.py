"""Baseline schema — all tables at schema version 4.

This migration captures the full schema as it exists after the four
custom migrations in ``core/migrations_legacy.py`` (the original
sqlite3-based system).  It is the starting point for the Alembic-managed
migration history.

Existing databases
------------------
Databases that were already fully migrated by the legacy system (i.e. they
have all tables present and ``meta.schema_version = 4``) are *stamped* at
this revision by ``core.migrations.runner`` without running this migration.
This preserves all existing data without any DDL changes.

New databases
-------------
A fresh database (no existing tables) runs this migration in full, creating
all eight tables in a single transaction.

Table inventory
---------------
``devices``         Network device inventory (id / JSON blob / updated_at)
``bandwidth_caps``  Interface bandwidth caps (id / JSON blob / updated_at)
``subnets``         Subnet definitions (id / JSON blob / updated_at)
``tag_defs``        Dynamic tag definitions (id / JSON blob / updated_at)
``audit_log``       Immutable audit trail (id / ts / actor / action / details)
``yaml_history``    YAML generation history (id / ts / actor / summary / files)
``lists``           Managed dropdown lists (list_name / items JSON array)
``meta``            Key-value metadata store (key / value)

Revision ID: c1f4e7a8b2d0
Revises:
Create Date: 2025-01-15 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1f4e7a8b2d0"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all ConfigFoundry tables."""

    # ------------------------------------------------------------------
    # JSON-blob entity tables
    # Pattern: (id TEXT PK, data TEXT NOT NULL, updated_at FLOAT NOT NULL)
    # ------------------------------------------------------------------

    op.create_table(
        "devices",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "bandwidth_caps",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "subnets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tag_defs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("ts", sa.Float(), nullable=False),
        sa.Column("actor", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # YAML generation history
    # ------------------------------------------------------------------

    op.create_table(
        "yaml_history",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("ts", sa.Float(), nullable=False),
        sa.Column("actor", sa.String(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("files", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # Managed dropdown lists  (list_name is the PK / name of the list)
    # ------------------------------------------------------------------

    op.create_table(
        "lists",
        sa.Column("list_name", sa.String(), nullable=False),
        sa.Column("items", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("list_name"),
    )

    # ------------------------------------------------------------------
    # Key-value metadata store
    # ------------------------------------------------------------------

    op.create_table(
        "meta",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    """Drop all ConfigFoundry tables (full rollback to empty database)."""

    # Drop in reverse creation order to respect any potential FK constraints
    # (there are none in the current schema, but this is good practice).
    op.drop_table("meta")
    op.drop_table("lists")
    op.drop_table("yaml_history")
    op.drop_table("audit_log")
    op.drop_table("tag_defs")
    op.drop_table("subnets")
    op.drop_table("bandwidth_caps")
    op.drop_table("devices")
