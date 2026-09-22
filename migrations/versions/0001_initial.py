"""initial schema including empty tools tables

Revision ID: 0001
Revises:
Create Date: 2026-09-22
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tables are created via SQLAlchemy metadata in init_db for bootstrap;
    # this revision stamps the schema version. Full create_all is idempotent.
    bind = op.get_bind()
    from ocrroute.db.base import Base
    from ocrroute.db import models  # noqa: F401

    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    from ocrroute.db.base import Base
    from ocrroute.db import models  # noqa: F401

    Base.metadata.drop_all(bind=bind)
