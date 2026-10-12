"""Backend-only, versioned food catalog queries."""
from app.db.proposals import connection


class FoodRepository:
    def __init__(self, connect=connection):
        self.connect = connect

    async def search(self, query: str, limit: int) -> list[dict]:
        # Escape LIKE operators; user text is always a bound parameter.
        pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        async with self.connect() as conn:
            cursor = await conn.execute(
                "select f.payload || jsonb_build_object('catalog_version', f.version) as payload "
                "from food_catalog_items f join food_catalog_versions v on v.version=f.version "
                "where v.active and f.normalized_name like %s "
                "order by (f.normalized_name=%s) desc, f.food_id limit %s", (pattern, query, limit))
            return [row['payload'] for row in await cursor.fetchall()]

    async def get(self, food_id: str) -> dict | None:
        async with self.connect() as conn:
            cursor = await conn.execute(
                "select f.payload || jsonb_build_object('catalog_version', f.version) as payload "
                "from food_catalog_items f join food_catalog_versions v on v.version=f.version "
                "where v.active and f.food_id=%s", (food_id,))
            row = await cursor.fetchone()
            return row['payload'] if row else None
