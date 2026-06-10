import aiosqlite
import json
from typing import Optional, List, Dict

DB_PATH = "shop.db"

async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                price REAL NOT NULL,
                photos TEXT, 
                is_reserved INTEGER DEFAULT 0,
                reserved_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def add_product(name: str, description: str, price: float, photos: List[str]) -> int:
    photos_json = json.dumps(photos)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO products (name, description, price, photos) VALUES (?, ?, ?, ?)",
            (name, description, price, photos_json)
        )
        await db.commit()
        return cursor.lastrowid

async def delete_product(product_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await db.commit()
        return cursor.rowcount > 0

async def get_all_products() -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products ORDER BY id DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def get_product(product_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def reserve_product(product_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE products SET is_reserved = 1, reserved_by = ? WHERE id = ? AND is_reserved = 0",
            (user_id, product_id)
        )
        await db.commit()
        return cursor.rowcount > 0

async def cancel_reservation(product_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE products SET is_reserved = 0, reserved_by = NULL WHERE id = ? AND reserved_by = ?",
            (product_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0

async def remove_photo_from_product(product_id: int, photo_index: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT photos FROM products WHERE id = ?", (product_id,))
        row = await cursor.fetchone()
        if not row or not row["photos"]:
            return False
        
        photos_list = json.loads(row["photos"])
        if 0 <= photo_index < len(photos_list):
            photos_list.pop(photo_index)
            new_photos_json = json.dumps(photos_list)
            await db.execute("UPDATE products SET photos = ? WHERE id = ?", (new_photos_json, product_id))
            await db.commit()
            return True
        return False
