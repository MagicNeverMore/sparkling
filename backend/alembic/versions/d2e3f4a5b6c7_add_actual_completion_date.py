"""Add editable task completion date without guessing historical timezones."""
from alembic import op
import sqlalchemy as sa

revision = "d2e3f4a5b6c7"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("user_task")}
    if "actual_completion_date" not in columns:
        op.add_column("user_task", sa.Column("actual_completion_date", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_task") as batch:
        batch.drop_column("actual_completion_date")
