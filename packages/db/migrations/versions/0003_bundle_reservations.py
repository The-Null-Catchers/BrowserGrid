"""Reserve source uploads before object writes; existing bundles remain usable."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bundles", sa.Column("ready", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.add_column("bundles", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_bundles_expires_at", "bundles", ["expires_at"])


def downgrade():
    with op.batch_alter_table("bundles") as batch:
        batch.drop_index("ix_bundles_expires_at")
        batch.drop_column("expires_at")
        batch.drop_column("ready")
