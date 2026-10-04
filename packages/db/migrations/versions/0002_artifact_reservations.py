"""Track upload reservations; historical artifacts are already ready."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "artifacts", sa.Column("ready", sa.Boolean(), nullable=False, server_default=sa.true())
    )


def downgrade():
    with op.batch_alter_table("artifacts") as batch:
        batch.drop_column("ready")
