<%!
    import re
%>\
<% slug = re.sub(r"\W+", "_", message or "").strip("_").lower()[:40] %>\
# src/weatherbot/services/persistence/migrations/versions/${up_revision}_${slug}.py
"""${message}.

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Apply the revision: expand first, so code that reads it can follow."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Undo the revision."""
    ${downgrades if downgrades else "pass"}
