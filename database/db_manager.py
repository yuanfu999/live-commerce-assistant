"""SQLite 数据库管理"""
import sqlite3
import os
import threading
from typing import List, Optional
from models.product import Product
from models.script import Script


class DBManager:
    """数据库管理器（线程安全）"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._local = threading.local()
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self.conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price TEXT DEFAULT '',
                feature TEXT DEFAULT '',
                target_audience TEXT DEFAULT '',
                benefit TEXT DEFAULT '',
                commission TEXT DEFAULT '',
                extra_notes TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1,
                priority INTEGER DEFAULT 0,
                scripts_per_round INTEGER DEFAULT 5,
                max_rounds INTEGER DEFAULT 0,
                created_at REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS scripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER DEFAULT 0,
                script_type TEXT DEFAULT 'main',
                content TEXT NOT NULL,
                style TEXT DEFAULT '热情促销型',
                is_favorite INTEGER DEFAULT 0,
                play_count INTEGER DEFAULT 0,
                created_at REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS broadcast_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                product_name TEXT DEFAULT '',
                script_content TEXT,
                duration REAL DEFAULT 0,
                broadcast_at REAL DEFAULT 0
            );
        """)
        conn.commit()
        self._migrate(conn)

    def _migrate(self, conn):
        """数据库结构迁移：为旧版本已存在的表补齐缺失的列（CREATE TABLE IF NOT EXISTS 不会更新旧表）"""
        # 检查 broadcast_history 表的实际列
        cols = {row[1] for row in conn.execute("PRAGMA table_info(broadcast_history)").fetchall()}
        if "product_name" not in cols:
            conn.execute("ALTER TABLE broadcast_history ADD COLUMN product_name TEXT DEFAULT ''")
        if "duration" not in cols:
            conn.execute("ALTER TABLE broadcast_history ADD COLUMN duration REAL DEFAULT 0")
        conn.commit()

    # ========== 商品操作 ==========
    def add_product(self, product: Product) -> int:
        conn = self.conn
        cur = conn.execute(
            """INSERT INTO products 
               (name, price, feature, target_audience, benefit, commission,
                extra_notes, enabled, priority, scripts_per_round, max_rounds, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (product.name, product.price, product.feature, product.target_audience,
             product.benefit, product.commission, product.extra_notes,
             int(product.enabled), product.priority, product.scripts_per_round,
             product.max_rounds, product.created_at)
        )
        conn.commit()
        return cur.lastrowid

    def update_product(self, product: Product):
        conn = self.conn
        conn.execute(
            """UPDATE products SET name=?, price=?, feature=?, target_audience=?,
               benefit=?, commission=?, extra_notes=?, enabled=?, priority=?,
               scripts_per_round=?, max_rounds=? WHERE id=?""",
            (product.name, product.price, product.feature, product.target_audience,
             product.benefit, product.commission, product.extra_notes,
             int(product.enabled), product.priority, product.scripts_per_round,
             product.max_rounds, product.id)
        )
        conn.commit()

    def delete_product(self, product_id: int):
        conn = self.conn
        conn.execute("DELETE FROM products WHERE id=?", (product_id,))
        conn.execute("DELETE FROM scripts WHERE product_id=?", (product_id,))
        conn.commit()

    def get_all_products(self) -> List[Product]:
        rows = self.conn.execute(
            "SELECT * FROM products ORDER BY priority ASC, id ASC"
        ).fetchall()
        return [Product(**dict(row)) for row in rows]

    def get_enabled_products(self) -> List[Product]:
        rows = self.conn.execute(
            "SELECT * FROM products WHERE enabled=1 ORDER BY priority ASC, id ASC"
        ).fetchall()
        return [Product(**dict(row)) for row in rows]

    # ========== 话术操作 ==========
    def add_script(self, script: Script) -> int:
        conn = self.conn
        cur = conn.execute(
            """INSERT INTO scripts (product_id, script_type, content, style, 
               is_favorite, play_count, created_at) VALUES (?,?,?,?,?,?,?)""",
            (script.product_id, script.script_type, script.content, script.style,
             int(script.is_favorite), script.play_count, script.created_at)
        )
        conn.commit()
        return cur.lastrowid

    def add_scripts_batch(self, scripts: List[Script]):
        conn = self.conn
        conn.executemany(
            """INSERT INTO scripts (product_id, script_type, content, style,
               is_favorite, play_count, created_at) VALUES (?,?,?,?,?,?,?)""",
            [(s.product_id, s.script_type, s.content, s.style,
              int(s.is_favorite), s.play_count, s.created_at) for s in scripts]
        )
        conn.commit()

    def get_scripts_by_product(self, product_id: int, script_type: str = None) -> List[Script]:
        if script_type:
            rows = self.conn.execute(
                "SELECT * FROM scripts WHERE product_id=? AND script_type=? ORDER BY id",
                (product_id, script_type)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM scripts WHERE product_id=? ORDER BY id",
                (product_id,)
            ).fetchall()
        return [Script(**dict(row)) for row in rows]

    def get_all_scripts(self) -> List[Script]:
        rows = self.conn.execute("SELECT * FROM scripts ORDER BY id DESC").fetchall()
        return [Script(**dict(row)) for row in rows]

    def delete_script(self, script_id: int):
        self.conn.execute("DELETE FROM scripts WHERE id=?", (script_id,))
        self.conn.commit()

    def update_script_content(self, script_id: int, content: str):
        self.conn.execute("UPDATE scripts SET content=? WHERE id=?", (content, script_id))
        self.conn.commit()

    def increment_play_count(self, script_id: int):
        self.conn.execute("UPDATE scripts SET play_count=play_count+1 WHERE id=?", (script_id,))
        self.conn.commit()

    # ========== 播报历史 ==========
    def add_history(self, product_id: int, script_content: str, product_name: str = "", duration: float = 0):
        import time
        self.conn.execute(
            "INSERT INTO broadcast_history (product_id, product_name, script_content, duration, broadcast_at) VALUES (?,?,?,?,?)",
            (product_id, product_name, script_content, duration, time.time())
        )
        self.conn.commit()

    def get_broadcast_history(self, limit: int = 100) -> list:
        rows = self.conn.execute(
            "SELECT * FROM broadcast_history ORDER BY broadcast_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def clear_broadcast_history(self):
        self.conn.execute("DELETE FROM broadcast_history")
        self.conn.commit()

    def close(self):
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
