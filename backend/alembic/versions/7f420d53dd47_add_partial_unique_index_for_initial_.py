"""add_partial_unique_index_for_initial_drafts

Revision ID: 7f420d53dd47
Revises: 4a386b6fd0d9
Create Date: 2026-11-27 17:03:53.124580

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f420d53dd47'
down_revision: Union[str, None] = '4a386b6fd0d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create SQLite partial unique index protecting initial draft version uniqueness."""
    op.create_index(
        "uq_drafts_initial_version",
        "drafts",
        ["outreach_thread_id", "draft_type", "version"],
        unique=True,
        sqlite_where=sa.text("draft_type = 'initial' AND followup_number IS NULL"),
    )


def downgrade() -> None:
    """Drop partial unique index for initial draft versions."""
    op.drop_index("uq_drafts_initial_version", table_name="drafts")
