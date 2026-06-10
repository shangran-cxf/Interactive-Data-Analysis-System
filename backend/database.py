import sqlite3
import hashlib
import os
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database')
DB_PATH = os.path.join(DB_DIR, 'app.db')


def get_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            brand TEXT NOT NULL,
            model TEXT NOT NULL,
            sales_volume INTEGER NOT NULL DEFAULT 0,
            sales_price REAL NOT NULL DEFAULT 0.0,
            energy_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            filename TEXT NOT NULL,
            record_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        -- 每次上传的清洗后明细数据的历史归档（按 upload_id 区分批次）
        CREATE TABLE IF NOT EXISTS upload_vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
            brand TEXT NOT NULL,
            model TEXT NOT NULL,
            sales_volume INTEGER NOT NULL DEFAULT 0,
            sales_price REAL NOT NULL DEFAULT 0.0,
            energy_type TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_vehicles_user ON vehicles(user_id);
        CREATE INDEX IF NOT EXISTS idx_uploads_user ON uploads(user_id);
        CREATE INDEX IF NOT EXISTS idx_upload_vehicles_upload ON upload_vehicles(upload_id);
    ''')
    # ── 轻量迁移：为既有数据库补充 users.active_upload_id 列（指向当前正在分析的上传批次）──
    user_cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)")]
    if "active_upload_id" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN active_upload_id INTEGER")
    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def create_user(username: str, password: str) -> tuple[bool, str, int]:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hash_password(password))
        )
        conn.commit()
        return True, "注册成功", cur.lastrowid
    except sqlite3.IntegrityError:
        return False, "账号已存在", 0
    finally:
        conn.close()


def verify_user(username: str, password: str) -> tuple:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    if row is None:
        return False, "账号不存在", None
    if row["password"] != hash_password(password):
        return False, "密码错误", None
    return True, "登录成功", dict(row)


def get_user_by_id(user_id: int) -> dict:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Per-user vehicle operations ──

def clear_user_vehicles(user_id: int):
    conn = get_db()
    conn.execute("DELETE FROM vehicles WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def insert_user_vehicles(user_id: int, records: list[dict]):
    conn = get_db()
    conn.executemany(
        "INSERT INTO vehicles (user_id, brand, model, sales_volume, sales_price, energy_type) VALUES (?, ?, ?, ?, ?, ?)",
        [(user_id, r['brand'], r['model'], r['sales_volume'], r['sales_price'], r['energy_type']) for r in records]
    )
    conn.commit()
    conn.close()


def record_upload(user_id: int, filename: str, record_count: int) -> int:
    """记录一次上传，返回新生成的 upload_id（供历史归档关联使用）。"""
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO uploads (user_id, filename, record_count) VALUES (?, ?, ?)",
        (user_id, filename, record_count)
    )
    conn.commit()
    upload_id = cur.lastrowid
    conn.close()
    return upload_id


# ── Upload history (归档 / 切换 / 删除) ──

def archive_upload_vehicles(upload_id: int, records: list[dict]):
    """把某次上传清洗后的明细数据归档到 upload_vehicles，作为可回溯的历史记录。"""
    conn = get_db()
    conn.executemany(
        "INSERT INTO upload_vehicles (upload_id, brand, model, sales_volume, sales_price, energy_type) VALUES (?, ?, ?, ?, ?, ?)",
        [(upload_id, r['brand'], r['model'], r['sales_volume'], r['sales_price'], r['energy_type']) for r in records]
    )
    conn.commit()
    conn.close()


def get_upload_vehicles(upload_id: int) -> list[dict]:
    """读取某次上传归档的明细数据。"""
    conn = get_db()
    rows = conn.execute(
        "SELECT brand, model, sales_volume, sales_price, energy_type "
        "FROM upload_vehicles WHERE upload_id = ? ORDER BY brand, model",
        (upload_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_upload(user_id: int, upload_id: int) -> dict:
    """按 (user_id, upload_id) 取单条上传记录，兼作归属校验。"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM uploads WHERE id = ? AND user_id = ?", (upload_id, user_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def set_active_upload(user_id: int, upload_id):
    """设置该用户当前正在分析的上传批次。"""
    conn = get_db()
    conn.execute("UPDATE users SET active_upload_id = ? WHERE id = ?", (upload_id, user_id))
    conn.commit()
    conn.close()


def get_active_upload_id(user_id: int):
    """取该用户当前正在分析的上传批次 id（无则返回 None）。"""
    conn = get_db()
    row = conn.execute("SELECT active_upload_id FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row["active_upload_id"] if row else None


def activate_upload(user_id: int, upload_id: int) -> tuple[bool, str, list]:
    """
    把某条历史上传切换为「当前分析数据」：
    校验归属 → 从归档恢复明细到 vehicles → 记为 active。
    返回 (是否成功, 提示, 恢复的记录列表)。
    """
    up = get_upload(user_id, upload_id)
    if not up:
        return False, "历史记录不存在或无权访问", []
    records = get_upload_vehicles(upload_id)
    if not records:
        return False, "该历史记录没有可恢复的明细数据（可能上传于历史功能上线之前）", []
    clear_user_vehicles(user_id)
    insert_user_vehicles(user_id, records)
    set_active_upload(user_id, upload_id)
    return True, "已切换到所选历史数据", records


def delete_upload(user_id: int, upload_id: int) -> tuple[bool, str]:
    """删除一条上传历史及其归档明细；若删的是当前 active 批次，则一并清空 vehicles。"""
    up = get_upload(user_id, upload_id)
    if not up:
        return False, "历史记录不存在或无权访问"
    conn = get_db()
    was_active = conn.execute(
        "SELECT active_upload_id FROM users WHERE id = ?", (user_id,)
    ).fetchone()["active_upload_id"] == upload_id
    conn.execute("DELETE FROM upload_vehicles WHERE upload_id = ?", (upload_id,))
    conn.execute("DELETE FROM uploads WHERE id = ? AND user_id = ?", (upload_id, user_id))
    if was_active:
        conn.execute("UPDATE users SET active_upload_id = NULL WHERE id = ?", (user_id,))
        conn.execute("DELETE FROM vehicles WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True, "已删除该历史记录"


def get_user_vehicles(user_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM vehicles WHERE user_id = ? ORDER BY brand, model", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_stats(user_id: int) -> dict:
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as cnt FROM vehicles WHERE user_id = ?", (user_id,)).fetchone()["cnt"]
    if total == 0:
        conn.close()
        return {
            "totalVehicles": 0, "topSalesCar": "-", "topSalesAmount": "-",
            "topSalesModel": "-", "topBrandByModels": "-", "avgPrice": "-",
            "brandCount": 0, "oilRatio": 0, "electricRatio": 0, "hybridRatio": 0
        }
    top_car = conn.execute(
        "SELECT brand, model, sales_volume FROM vehicles WHERE user_id = ? ORDER BY sales_volume DESC LIMIT 1",
        (user_id,)
    ).fetchone()
    top_amount = conn.execute(
        "SELECT brand, model, (sales_volume * sales_price) as revenue FROM vehicles WHERE user_id = ? ORDER BY revenue DESC LIMIT 1",
        (user_id,)
    ).fetchone()
    top_model_type = conn.execute(
        "SELECT model, COUNT(*) as cnt FROM vehicles WHERE user_id = ? GROUP BY model ORDER BY cnt DESC LIMIT 1",
        (user_id,)
    ).fetchone()
    top_brand_models = conn.execute(
        "SELECT brand, COUNT(*) as cnt FROM vehicles WHERE user_id = ? GROUP BY brand ORDER BY cnt DESC LIMIT 1",
        (user_id,)
    ).fetchone()
    avg_price = conn.execute("SELECT AVG(sales_price) as avg_p FROM vehicles WHERE user_id = ?", (user_id,)).fetchone()["avg_p"]
    brand_cnt = conn.execute("SELECT COUNT(DISTINCT brand) as cnt FROM vehicles WHERE user_id = ?", (user_id,)).fetchone()["cnt"]
    total_vol = conn.execute("SELECT SUM(sales_volume) as sv FROM vehicles WHERE user_id = ?", (user_id,)).fetchone()["sv"] or 1
    oil_vol = conn.execute(
        "SELECT SUM(sales_volume) as sv FROM vehicles WHERE user_id = ? AND energy_type IN ('油车','燃油车','汽油车')",
        (user_id,)
    ).fetchone()["sv"] or 0
    electric_vol = conn.execute(
        "SELECT SUM(sales_volume) as sv FROM vehicles WHERE user_id = ? AND energy_type IN ('电车','电动','纯电动','新能源')",
        (user_id,)
    ).fetchone()["sv"] or 0
    hybrid_vol = conn.execute(
        "SELECT SUM(sales_volume) as sv FROM vehicles WHERE user_id = ? AND energy_type IN ('混动','油电混合','插电混动')",
        (user_id,)
    ).fetchone()["sv"] or 0
    conn.close()
    return {
        "totalVehicles": total,
        "topSalesCar": f"{top_car['brand']} {top_car['model']}" if top_car else "-",
        "topSalesCarVolume": top_car["sales_volume"] if top_car else 0,
        "topSalesAmount": f"{top_amount['brand']} {top_amount['model']}" if top_amount else "-",
        "topSalesAmountValue": round(top_amount["revenue"], 2) if top_amount else 0,
        "topSalesModel": top_model_type["model"] if top_model_type else "-",
        "topBrandByModels": top_brand_models["brand"] if top_brand_models else "-",
        "avgPrice": round(avg_price, 2) if avg_price else 0,
        "brandCount": brand_cnt,
        "oilRatio": round(oil_vol / total_vol * 100, 1),
        "electricRatio": round(electric_vol / total_vol * 100, 1),
        "hybridRatio": round(hybrid_vol / total_vol * 100, 1),
    }


def get_user_brand_sales(user_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT brand, SUM(sales_volume) as total_sales FROM vehicles WHERE user_id = ? GROUP BY brand ORDER BY total_sales DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [{"brand": r["brand"], "sales": r["total_sales"]} for r in rows]


def get_user_price_distribution(user_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT sales_price FROM vehicles WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    prices = [r["sales_price"] for r in rows]
    bins = [
        ("10万以下", 0, 10), ("10-20万", 10, 20), ("20-30万", 20, 30),
        ("30-50万", 30, 50), ("50万以上", 50, float("inf"))
    ]
    result = []
    for label, lo, hi in bins:
        count = sum(1 for p in prices if lo <= p < hi)
        result.append({"range": label, "count": count, "lo": lo, "hi": hi if hi != float("inf") else "以上"})
    return result


def get_user_energy_ratio(user_id: int) -> dict:
    conn = get_db()
    total = conn.execute("SELECT SUM(sales_volume) as sv FROM vehicles WHERE user_id = ?", (user_id,)).fetchone()["sv"] or 1
    oil = conn.execute(
        "SELECT SUM(sales_volume) as sv FROM vehicles WHERE user_id = ? AND energy_type IN ('油车','燃油车','汽油车')",
        (user_id,)
    ).fetchone()["sv"] or 0
    electric = conn.execute(
        "SELECT SUM(sales_volume) as sv FROM vehicles WHERE user_id = ? AND energy_type IN ('电车','电动','纯电动','新能源')",
        (user_id,)
    ).fetchone()["sv"] or 0
    hybrid = conn.execute(
        "SELECT SUM(sales_volume) as sv FROM vehicles WHERE user_id = ? AND energy_type IN ('混动','油电混合','插电混动')",
        (user_id,)
    ).fetchone()["sv"] or 0
    conn.close()
    return {
        "oil": round(oil / total * 100, 1),
        "electric": round(electric / total * 100, 1),
        "hybrid": round(hybrid / total * 100, 1),
    }


def get_user_sales_chart(user_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT brand, model, sales_volume, sales_price FROM vehicles WHERE user_id = ? ORDER BY sales_volume DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [{"name": f"{r['brand']} {r['model']}", "volume": r["sales_volume"], "price": r["sales_price"]} for r in rows]


# ── Admin queries ──

def get_all_users() -> list[dict]:
    conn = get_db()
    rows = conn.execute("""
        SELECT u.id, u.username, u.created_at,
               COUNT(DISTINCT v.id) as vehicle_count,
               COUNT(DISTINCT up.id) as upload_count
        FROM users u
        LEFT JOIN vehicles v ON v.user_id = u.id
        LEFT JOIN uploads up ON up.user_id = u.id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_uploads(user_id: int) -> list[dict]:
    """
    返回该用户的上传历史（倒序），并附带：
      · is_active     — 是否为当前正在分析的批次
      · archived_count — 该批次归档的可恢复明细条数（0 表示无法回溯）
    供前端历史记录列表选择使用。
    """
    conn = get_db()
    active_row = conn.execute(
        "SELECT active_upload_id FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    active_id = active_row["active_upload_id"] if active_row else None
    rows = conn.execute(
        """
        SELECT up.id, up.user_id, up.filename, up.record_count, up.created_at,
               (SELECT COUNT(*) FROM upload_vehicles uv WHERE uv.upload_id = up.id) AS archived_count
        FROM uploads up
        WHERE up.user_id = ?
        ORDER BY up.created_at DESC, up.id DESC
        """,
        (user_id,)
    ).fetchall()
    conn.close()
    return [{**dict(r), "is_active": r["id"] == active_id} for r in rows]


def get_all_uploads() -> list[dict]:
    conn = get_db()
    rows = conn.execute("""
        SELECT up.*, u.username
        FROM uploads up JOIN users u ON u.id = up.user_id
        ORDER BY up.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]
