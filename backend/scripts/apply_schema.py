"""Apply supabase/schema.sql to the configured database.

Safe to re-run: every statement in schema.sql is idempotent
(CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS / CREATE OR REPLACE).

Usage (from the backend/ directory so .env is picked up):
    python -m scripts.apply_schema
"""
import asyncio
import logging
from pathlib import Path

from sqlalchemy import text

from app.database import engine

logger = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).resolve().parents[1] / "supabase" / "schema.sql"


def split_statements(sql: str) -> list[str]:
    """Split SQL on top-level semicolons, skipping `$$ ... $$` PL/pgSQL
    blocks and line comments (so `;` inside function bodies is preserved)."""
    statements: list[str] = []
    current: list[str] = []
    in_dollar = False
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if not in_dollar:
            if ch == "-" and nxt == "-":
                j = sql.find("\n", i)
                i = n if j == -1 else j + 1
                continue
            if ch == "$" and nxt == "$":
                in_dollar = True
                current.append("$$")
                i += 2
                continue
            if ch == ";":
                statements.append("".join(current).strip())
                current = []
                i += 1
                continue
        else:
            if ch == "$" and nxt == "$":
                in_dollar = False
                current.append("$$")
                i += 2
                continue

        current.append(ch)
        i += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return [s for s in statements if s]


async def apply_schema() -> int:
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    statements = split_statements(sql)
    logger.info("Applying %d statements from %s", len(statements), SCHEMA_FILE.name)

    applied = 0
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))
            applied += 1
    return applied


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    count = await apply_schema()
    logger.info("Schema applied successfully (%d statements).", count)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
