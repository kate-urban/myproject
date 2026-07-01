import asyncio
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()


async def test_sqlalchemy():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set in .env")
        sys.exit(1)

    engine = create_async_engine(database_url, echo=False)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version()"))
            print(f"OK: {result.scalar()}")
    except Exception as e:
        print(f"ERROR: {type(e).__name__} - {e}")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_sqlalchemy())
