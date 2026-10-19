"""Schema upgrades for admin panel (PostgreSQL)."""
from sqlalchemy import text

ADMIN_SCHEMA_STATEMENTS = [
    "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS full_name VARCHAR(200)",
    "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS phone VARCHAR(32)",
    "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS school_class VARCHAR(20)",
    "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
    "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP",
    "ALTER TABLE course ADD COLUMN IF NOT EXISTS subject VARCHAR(80)",
    "ALTER TABLE course ADD COLUMN IF NOT EXISTS school_class VARCHAR(20)",
    "ALTER TABLE course_material ADD COLUMN IF NOT EXISTS category VARCHAR(32) DEFAULT 'theory'",
    "ALTER TABLE course_material ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1",
    "ALTER TABLE course_material ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
    """CREATE TABLE IF NOT EXISTS announcement (
        id SERIAL PRIMARY KEY,
        title VARCHAR(200) NOT NULL,
        body TEXT NOT NULL,
        author_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc') NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS ix_announcement_created_at ON announcement (created_at DESC)",
    "ALTER TABLE homework_submission ADD COLUMN IF NOT EXISTS is_rejected BOOLEAN DEFAULT FALSE",
    "ALTER TABLE homework_submission ADD COLUMN IF NOT EXISTS rejection_reason TEXT",
]

def upgrade_admin_schema(db):
    for stmt in ADMIN_SCHEMA_STATEMENTS:
        db.session.execute(text(stmt))
    db.session.commit()
