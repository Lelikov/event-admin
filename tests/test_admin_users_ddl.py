"""scripts/admin_users.sql must exist and stay in sync with the AdminUser model."""

from pathlib import Path

from event_admin.db.models import AdminUser


DDL_PATH = Path(__file__).parent.parent / "scripts" / "admin_users.sql"


def test_ddl_script_is_tracked() -> None:
    assert DDL_PATH.is_file(), "admin_users DDL must live in scripts/admin_users.sql"


def test_ddl_script_is_idempotent() -> None:
    ddl = DDL_PATH.read_text()
    assert "CREATE TABLE IF NOT EXISTS admin_users" in ddl
    assert "CREATE INDEX IF NOT EXISTS ix_admin_users_email" in ddl


def test_ddl_script_covers_all_model_columns() -> None:
    ddl = DDL_PATH.read_text()
    for column in AdminUser.__table__.columns:
        assert column.name in ddl, f"column {column.name!r} missing from scripts/admin_users.sql"


def test_model_docstring_carries_no_ddl() -> None:
    assert "CREATE TABLE admin_users" not in (AdminUser.__doc__ or "")
