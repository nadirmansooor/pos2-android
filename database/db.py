# -*- coding: utf-8 -*-
# ============================================================================
#  ApnaSoft POS 2.0 - DATABASE ENGINE (SQLite | offline-first)
#  users | products | customers | suppliers | sales | held | purchases
#  expenses | stock_log | settings | license | devices | activity_log
# ============================================================================
import datetime
import hashlib
import json
import os
import shutil
import sqlite3
import threading

from core import utils
from core.config import (APP_TAG, COMPANY, EXPIRY_ALERT_DAYS, data_dir,
                         db_path)

_lock = threading.RLock()
_conn = None
_connp = None


def get_conn():
    global _conn, _connp
    if _conn is None or _connp != db_path():
        _conn = sqlite3.connect(db_path(), timeout=10)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys=ON")
        # SPEED PACK: the app opens + lists in a blink, even on slow PCs.
        # WAL = one file-lock reader/writer dance removed, NORMAL sync is
        # safe for a single-user desktop app, and the 8MB cache keeps hot
        # pages in RAM. Offline app -> nothing ever leaves the PC.
        # busy_timeout: if ANYTHING briefly holds the file (a close-time
        # backup, a zombie copy), we WAIT politely instead of erroring.
        for _p in ("PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL",
                   "PRAGMA temp_store=MEMORY", "PRAGMA cache_size=-8000",
                   "PRAGMA busy_timeout=10000"):
            try:
                _conn.execute(_p)
            except Exception:
                pass
        _connp = db_path()
    return _conn


def reset_conn():
    global _conn, _connp
    try:
        if _conn is not None:
            _conn.close()
    except Exception:
        pass
    _conn, _connp = None, None


def q(sql, p=(), one=False):
    with _lock:
        cur = get_conn().execute(sql, p)
        rows = [dict(r) for r in cur.fetchall()]
    return (rows[0] if rows else None) if one else rows


def run(sql, p=()):
    with _lock:
        cur = get_conn().execute(sql, p)
        get_conn().commit()
        return cur.lastrowid


def run_many(sql, seq):
    with _lock:
        get_conn().executemany(sql, seq)
        get_conn().commit()


# ----------------------------------------------------------------------------
#  SETTINGS
# ----------------------------------------------------------------------------
# (module pair 3/3 of the license seal - used by activation/licensemgr.py)
_CFG_CHUNK = ("r8Tz", "4Km9", "xQ2w", "7Vp3")


def _cfg_salt():
    return "".join(_CFG_CHUNK).encode()


def get_setting(key, default=""):
    r = q("SELECT value v FROM settings WHERE key=?", (key,), one=True)
    return r["v"] if r and r["v"] not in (None, "") else default


def set_setting(key, value):
    with _lock:
        get_conn().execute("INSERT INTO settings(key,value) VALUES(?,?) "
                           "ON CONFLICT(key) DO UPDATE SET value=?",
                           (key, str(value), str(value)))
        get_conn().commit()


def business():
    return {
        "name": get_setting("biz_name", "My Shop"),
        "address": get_setting("biz_address", ""),
        "phone": get_setting("biz_phone", ""),
        "currency": get_setting("currency", "Rs"),
        "tax_percent": float(get_setting("tax_percent", "0") or 0),
        "app_title": get_setting("app_title", ""),
        "receipt_paper": get_setting("receipt_paper", "80mm"),
        "receipt_header": get_setting("receipt_header", ""),
        "receipt_footer": get_setting(
            "receipt_footer", "خریداری کا شکریہ! دوبارہ تشریف لائیں۔"),
        "low_limit": int(get_setting("low_limit", "5") or 5),
        "expiry_days": int(get_setting("expiry_days",
                                       str(EXPIRY_ALERT_DAYS)) or
                           EXPIRY_ALERT_DAYS),
    }


def shop_logo_path():
    dd = data_dir()
    for ext in (".png", ".jpg", ".jpeg"):
        cand = os.path.join(dd, "shop_logo" + ext)
        if os.path.exists(cand):
            return cand
    return ""


def money(x):
    try:
        return round(float(x or 0), 2)
    except Exception:
        return 0.0


def is_demo():
    return get_setting("mode", "demo") == "demo"


def require_save():
    """The 1-MONTH TRIAL and licensed PCs save EVERYTHING freely. Only an
    ENDED trial (or a dead/blocked key) stops writing - and even then no
    data is ever touched, the software simply waits for the key."""
    if is_demo():
        try:
            from activation import licensemgr
            if licensemgr.license_state()[0] == "demo":
                return                      # trial month: fully open
        except Exception:
            return                          # never block by accident
        raise ValueError(
            "آپ کی ایک ماہ مفت آزمائش اس کمپیوٹر پر ختم ہو گئی ہے۔\n"
            "کام جاری رکھنے کے لیے اپنی لائسنس کلید لکھیں - آپ کا ہر پروڈکٹ، سیل "
            "اور ترتیب بالکل وہیں رہتی ہے، کچھ بھی "
            "ڈیلیٹ نہیں ہوتا۔")


def log_activity(action, detail="", user=""):
    run("INSERT INTO activity_log(ts,action,detail,username) VALUES(?,?,?,?)",
        (utils.now(), action, str(detail)[:400], user))


# ----------------------------------------------------------------------------
#  SCHEMA
# ----------------------------------------------------------------------------
def init_db():
    with _lock:
        c = get_conn()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS devices(
            fingerprint TEXT PRIMARY KEY, machine TEXT, ts TEXT);
        CREATE TABLE IF NOT EXISTS license(
            id INTEGER PRIMARY KEY CHECK(id=1),
            client TEXT, key TEXT, expiry TEXT, activated TEXT);
        CREATE TABLE IF NOT EXISTS activity_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, action TEXT, detail TEXT, username TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            passhash TEXT NOT NULL, salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'cashier',
            active INTEGER DEFAULT 1, created TEXT);
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            barcode TEXT DEFAULT '',
            category TEXT DEFAULT 'General',
            cost REAL DEFAULT 0, price REAL DEFAULT 0,
            stock REAL DEFAULT 0, low_limit INTEGER DEFAULT 5,
            expiry TEXT DEFAULT '',
            active INTEGER DEFAULT 1, created TEXT);
        CREATE TABLE IF NOT EXISTS customers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, phone TEXT DEFAULT '',
            address TEXT DEFAULT '', zone TEXT DEFAULT '',
            sector TEXT DEFAULT '', created TEXT);
        CREATE TABLE IF NOT EXISTS suppliers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, phone TEXT DEFAULT '',
            address TEXT DEFAULT '', created TEXT);
        CREATE TABLE IF NOT EXISTS sales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT NOT NULL UNIQUE,
            date TEXT, ts TEXT,
            customer_id INTEGER DEFAULT 0,
            customer_name TEXT DEFAULT '',
            subtotal REAL DEFAULT 0, discount REAL DEFAULT 0,
            tax REAL DEFAULT 0, total REAL DEFAULT 0,
            paid REAL DEFAULT 0, change REAL DEFAULT 0,
            payment TEXT DEFAULT 'Cash',
            due_date TEXT DEFAULT '',
            username TEXT DEFAULT '', status TEXT DEFAULT 'done');
        CREATE TABLE IF NOT EXISTS sale_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL, product_id INTEGER DEFAULT 0,
            name TEXT, qty REAL DEFAULT 0, price REAL DEFAULT 0,
            discount REAL DEFAULT 0, cost REAL DEFAULT 0,
            total REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS held_sales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT, payload TEXT, ts TEXT, username TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS purchases(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, supplier_id INTEGER DEFAULT 0,
            supplier_name TEXT DEFAULT '',
            total REAL DEFAULT 0, paid REAL DEFAULT 0,
            note TEXT DEFAULT '', created TEXT);
        CREATE TABLE IF NOT EXISTS purchase_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id INTEGER NOT NULL, product_id INTEGER DEFAULT 0,
            name TEXT, qty REAL DEFAULT 0, cost REAL DEFAULT 0,
            total REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, category TEXT DEFAULT 'Other',
            note TEXT DEFAULT '', amount REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS stock_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, product_id INTEGER, change REAL,
            reason TEXT DEFAULT '', ref TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, ts TEXT,
            customer_id INTEGER NOT NULL,
            customer_name TEXT DEFAULT '',
            amount REAL DEFAULT 0,
            method TEXT DEFAULT 'Cash',
            note TEXT DEFAULT '',
            username TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS sync_seen(
            guid TEXT PRIMARY KEY,
            ts TEXT);
        CREATE TABLE IF NOT EXISTS day_flow(
            date TEXT PRIMARY KEY,
            opening REAL DEFAULT 0,
            open_ts TEXT, open_user TEXT DEFAULT '',
            closing_expected REAL, closing_actual REAL,
            close_ts TEXT, close_user TEXT DEFAULT '',
            close_note TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS returns(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            return_no TEXT NOT NULL UNIQUE,
            date TEXT, ts TEXT,
            sale_id INTEGER DEFAULT 0,
            invoice_no TEXT DEFAULT '',
            customer_name TEXT DEFAULT '',
            total REAL DEFAULT 0,
            reason TEXT DEFAULT '',
            mode TEXT DEFAULT 'Cash back',
            username TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS return_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            return_id INTEGER NOT NULL,
            product_id INTEGER DEFAULT 0,
            name TEXT, qty REAL DEFAULT 0,
            price REAL DEFAULT 0, cost REAL DEFAULT 0, total REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS employees(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, phone TEXT DEFAULT '',
            role TEXT DEFAULT 'Staff',
            salary REAL DEFAULT 0,
            joined TEXT DEFAULT '', note TEXT DEFAULT '',
            active INTEGER DEFAULT 1, created TEXT);
        CREATE TABLE IF NOT EXISTS salary_payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            employee_name TEXT DEFAULT '',
            month TEXT DEFAULT '',
            amount REAL DEFAULT 0,
            date TEXT, ts TEXT,
            note TEXT DEFAULT '', username TEXT DEFAULT '');
        """)
        # helpful indexes (speed: searches + joins stay instant as data grows)
        c.executescript("""
        CREATE INDEX IF NOT EXISTS ix_products_barcode ON products(barcode);
        CREATE INDEX IF NOT EXISTS ix_products_name ON products(name);
        CREATE INDEX IF NOT EXISTS ix_sales_date ON sales(date);
        CREATE INDEX IF NOT EXISTS ix_sales_inv ON sales(invoice_no);
        CREATE INDEX IF NOT EXISTS ix_sale_items_sid ON sale_items(sale_id);
        CREATE INDEX IF NOT EXISTS ix_sale_items_pid ON sale_items(product_id);
        CREATE INDEX IF NOT EXISTS ix_stock_log_pid ON stock_log(product_id);
        CREATE INDEX IF NOT EXISTS ix_payments_date ON payments(date);
        CREATE INDEX IF NOT EXISTS ix_expenses_date ON expenses(date);
        CREATE INDEX IF NOT EXISTS ix_sales_cid ON sales(customer_id);
        CREATE INDEX IF NOT EXISTS ix_payments_cid ON payments(customer_id);
        CREATE INDEX IF NOT EXISTS ix_returns_date ON returns(date);
        CREATE INDEX IF NOT EXISTS ix_cust_name_nc ON customers(name COLLATE NOCASE);
        """)
        c.commit()
    _migrate_columns()
    seed_admin()


def _migrate_columns():
    """Safe upgrades for OLD databases (columns added after v1): silently
    ALTER older tables so an old client's data keeps working."""
    def _cols(table):
        try:
            return [r["name"] for r in q("PRAGMA table_info(" + table + ")")]
        except Exception:
            return []
    for col in ("zone", "sector"):
        if col not in _cols("customers"):
            try:
                run("ALTER TABLE customers ADD COLUMN " + col +
                    " TEXT DEFAULT ''")
            except Exception:
                pass
    if "due_date" not in _cols("sales"):
        try:
            run("ALTER TABLE sales ADD COLUMN due_date TEXT DEFAULT ''")
        except Exception:
            pass
    if "expiry" not in _cols("products"):
        try:
            run("ALTER TABLE products ADD COLUMN expiry TEXT DEFAULT ''")
        except Exception:
            pass
    if "unit" not in _cols("products"):
        try:
            run("ALTER TABLE products ADD COLUMN unit TEXT DEFAULT 'pcs'")
        except Exception:
            pass
    if "unit" not in _cols("sale_items"):
        try:
            run("ALTER TABLE sale_items ADD COLUMN unit TEXT DEFAULT 'pcs'")
        except Exception:
            pass
    # PACK SIZE: "1 pack = N units" (a 40-kg bora, a 24-pc shell ...).
    # Stock always stays in the BASE unit, so a 0.25 kg loose sale and a
    # full-pack sale both cut the SAME shelf count - honest maths, always.
    if "pack_size" not in _cols("products"):
        try:
            run("ALTER TABLE products ADD COLUMN pack_size REAL DEFAULT 0")
        except Exception:
            pass
    # PACK SYSTEM level 1 + level 2: a middle pack (bora / dozen / packet)
    # AND a big outer pack (carton / peti). Each level has its OWN name,
    # its OWN size (in base units) and its OWN sell rate - because a shop
    # charges one rate for a full bora and another for loose kg. A rate
    # of 0 always means "auto": the plain unit price x size is used.
    for col, ddl in (("pack_name", "pack_name TEXT DEFAULT ''"),
                     ("pack_price", "pack_price REAL DEFAULT 0"),
                     ("pack2_name", "pack2_name TEXT DEFAULT ''"),
                     ("pack2_size", "pack2_size REAL DEFAULT 0"),
                     ("pack2_price", "pack2_price REAL DEFAULT 0")):
        if col not in _cols("products"):
            try:
                run("ALTER TABLE products ADD COLUMN " + ddl)
            except Exception:
                pass
    # SUB-UNIT: the small measuring partner of the main unit, so the
    # counter can sell straight in grams / ml / pieces without mental
    # maths - "250 g of sugar" lands as 0.25 kg of the SAME stock, and a
    # custom sub rate (0 = auto proportional) covers things like an
    # expensive 100-g pouch of an otherwise cheap kg item.
    for col, ddl in (("sub_unit", "sub_unit TEXT DEFAULT ''"),
                     ("sub_size", "sub_size REAL DEFAULT 0"),
                     ("sub_price", "sub_price REAL DEFAULT 0")):
        if col not in _cols("products"):
            try:
                run("ALTER TABLE products ADD COLUMN " + ddl)
            except Exception:
                pass
    if "refunded" not in _cols("sales"):
        try:
            run("ALTER TABLE sales ADD COLUMN refunded REAL DEFAULT 0")
        except Exception:
            pass
    # SOLD-UNIT BILLING: every bill line remembers how much of the MAIN
    # unit really left the shelf (a 0.5 kg sale of a 40-kg bora carries
    # base_qty 0.0125). Old rows were ALL base-unit lines, so base = qty.
    if "base_qty" not in _cols("sale_items"):
        try:
            run("ALTER TABLE sale_items ADD COLUMN base_qty REAL DEFAULT 0")
            run("UPDATE sale_items SET base_qty=qty")
        except Exception:
            pass
    if "base_qty" not in _cols("return_items"):
        try:
            run("ALTER TABLE return_items ADD COLUMN base_qty REAL "
                "DEFAULT 0")
            run("UPDATE return_items SET base_qty=qty")
        except Exception:
            pass
    _convert_pack_products()


def pack_to_unit(p):
    """July 2026 final simple model - ONE ladder per item: the big pack
    IS the main unit (so the plain product button sells the whole bora
    at the bora rate), the old loose unit becomes its ONE sub-unit, and
    every price the shopkeeper set is KEPT. p is a product row (or a
    csv import dict). Returns the fields to change, or None."""
    p1 = money(p.get("pack_size") or 0)
    p2 = money(p.get("pack2_size") or 0)
    if p1 <= 0 and p2 <= 0:
        return None
    clear = {"pack_size": 0, "pack_name": "", "pack_price": 0,
             "pack2_size": 0, "pack2_name": "", "pack2_price": 0}
    if (p.get("sub_unit") or "").strip():
        # a small sub-unit already exists - keep it and simply fold the
        # pack level away (a needed bora lives happily as its OWN
        # product; one clean two-step ladder per item from now on)
        return clear
    big = p2 > 0
    size = p2 if big else p1
    name = ((p.get("pack2_name") if big else p.get("pack_name")) or
            "").strip()
    rate = money((p.get("pack2_price") if big else
                  p.get("pack_price")) or 0)
    price = money(p.get("price") or 0)
    out = dict(clear)
    out.update({"unit": name.lower() if name else "pack",
                "price": rate if rate > 0 else money(price * size),
                "cost": money(money(p.get("cost") or 0) * size),
                "sub_unit": (p.get("unit") or "pcs"),
                "sub_size": size,
                "sub_price": price,
                "stock": round(money(p.get("stock") or 0) / size, 4),
                "low_limit": max(1, round(float(p.get("low_limit") or 0)
                                          / size))})
    return out


def _convert_pack_products():
    """One-time rewrite of OLD pack-style rows into the simple
    unit + sub-unit ladder. Runs exactly once (flag pack_to_unit_v1) and
    logs every row it touches - nothing ever changes silently."""
    if get_setting("pack_to_unit_v1") == "1":
        return
    try:
        rows = q("SELECT * FROM products WHERE pack_size>0 OR "
                 "pack2_size>0")
        for p in rows:
            conv = pack_to_unit(p)
            if not conv:
                continue
            sets = ",".join("%s=?" % k for k in conv)
            run("UPDATE products SET " + sets + " WHERE id=?",
                tuple(conv.values()) + (p["id"],))
            log_activity("MIGRATE", "pack -> unit+sub ladder: %s (#%d)"
                         % (p["name"], p["id"]))
    except Exception:
        pass
    try:
        set_setting("pack_to_unit_v1", "1")
    except Exception:
        pass


# ----------------------------------------------------------------------------
#  AUTH / USERS
# ----------------------------------------------------------------------------
def hash_pw(pw, salt):
    """Legacy salted SHA-256 - kept ONLY so installs upgraded from an old
    build can still log in once (they are then silently re-hashed)."""
    return hashlib.sha256((salt + "|" + pw + "|POS2-786").encode()).hexdigest()


def hash_pw2(pw, salt):
    """PBKDF2-HMAC-SHA256, 60,000 rounds - the premium standard. The stored
    string carries its own 'pbkdf2$' marker so old and new hashes can live
    side by side while users migrate on their next login."""
    dk = hashlib.pbkdf2_hmac("sha256", (pw + "|POS2-786").encode(),
                             salt.encode(), 60000)
    return "pbkdf2$" + dk.hex()


def seed_admin():
    if q("SELECT COUNT(*) c FROM users", one=True)["c"]:
        return
    salt = utils.now() + COMPANY
    run("INSERT INTO users(username,passhash,salt,role,active,created) "
        "VALUES(?,?,?,?,1,?)",
        ("admin", hash_pw2("admin123", salt), salt, "admin", utils.now()))


def verify_user(username, password):
    u = q("SELECT * FROM users WHERE username=? AND active=1",
          ((username or "").strip(),), one=True)
    if not u:
        return None
    stored = u["passhash"] or ""
    pw = password or ""
    if stored.startswith("pbkdf2$"):
        return u if hash_pw2(pw, u["salt"]) == stored else None
    if hash_pw(pw, u["salt"]) != stored:
        return None
    try:          # silent security upgrade: re-hash to PBKDF2 on login
        run("UPDATE users SET passhash=? WHERE id=?",
            (hash_pw2(pw, u["salt"]), u["id"]))
    except Exception:
        pass
    return u


def list_users():
    return q("SELECT id,username,role,active,created FROM users "
             "ORDER BY username")


def save_user(data, uid=None):
    require_save()
    uname = (data.get("username") or "").strip().lower()
    if not uname:
        raise ValueError("صارف نام لازمی ہے")
    role = data.get("role", "cashier")
    if role not in ("admin", "cashier"):
        role = "cashier"
    dup = q("SELECT id FROM users WHERE username=? AND id<>?",
            (uname, uid or 0), one=True)
    if dup:
        raise ValueError("صارف نام پہلے سے موجود ہے")
    if uid:
        if (data.get("password") or "").strip():
            salt = utils.now() + uname
            run("UPDATE users SET role=?,active=?,salt=?,passhash=? "
                "WHERE id=?", (role, 1 if data.get("active", 1) else 0,
                               salt, hash_pw2(data["password"], salt), uid))
        else:
            run("UPDATE users SET role=?,active=? WHERE id=?",
                (role, 1 if data.get("active", 1) else 0, uid))
        return uid
    if not (data.get("password") or "").strip():
        raise ValueError("پاس ورڈ لازمی ہے")
    salt = utils.now() + uname
    return run("INSERT INTO users(username,passhash,salt,role,active,created)"
               " VALUES(?,?,?,?,1,?)",
               (uname, hash_pw2(data["password"], salt), salt, role,
                utils.now()))


def del_user(uid):
    require_save()
    u = q("SELECT username FROM users WHERE id=?", (uid,), one=True)
    if u and u["username"] == "admin":
        raise ValueError("مرکزی 'admin' صارف ڈیلیٹ نہیں ہو سکتا۔")
    run("DELETE FROM users WHERE id=?", (uid,))


# ----------------------------------------------------------------------------
#  PRODUCTS
# ----------------------------------------------------------------------------
def save_product(data, pid=None):
    require_save()
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("پروڈکٹ کا نام لازمی ہے")
    price = money(data.get("price"))
    if price < 0:
        raise ValueError("قیمت منفی نہیں ہو سکتی۔")
    if money(data.get("cost")) < 0:
        raise ValueError("لاگت منفی نہیں ہو سکتی۔")
    if money(data.get("stock")) < 0:
        raise ValueError("اسٹاک منفی نہیں ہو سکتا۔")
    bc = (data.get("barcode") or "").strip()
    if bc:
        dup = q("SELECT id,name FROM products WHERE barcode=? AND id<>?",
                (bc, pid or 0), one=True)
        if dup:
            raise ValueError("بارکوڈ پہلے سے استعمال میں: " + dup["name"])
    elif not pid:
        bc = next_product_code()      # AUTO product code (PRD-00001 ...)
    expiry = (data.get("expiry") or "").strip()
    if expiry:
        try:
            utils.days_between(expiry, expiry)   # validates YYYY-MM-DD
        except Exception as err:
            raise ValueError(
                "ایکسپائری YYYY-MM-DD جیسی ہو (یا خالی)۔") from err
    unit = (data.get("unit") or "pcs").strip() or "pcs"
    pack = money(data.get("pack_size") or 0)
    if pack < 0:
        raise ValueError(
            "پیک سائز منفی نہیں ہو سکتا (0 = سادہ آئٹم، بغیر پیک)۔")
    pack_name = (data.get("pack_name") or "").strip()
    pack_rate = money(data.get("pack_price") or 0)
    pack2 = money(data.get("pack2_size") or 0)
    pack2_name = (data.get("pack2_name") or "").strip()
    pack2_rate = money(data.get("pack2_price") or 0)
    if pack_rate < 0 or pack2 < 0 or pack2_rate < 0:
        raise ValueError("پیک ریٹ اور بڑے پیک کی قدریں منفی نہیں ہو سکتیں "
                         "(0 = کوئی نہیں / خودکار)۔")
    sub_name = (data.get("sub_unit") or "").strip()
    sub_size = money(data.get("sub_size") or 0)
    sub_rate_v = money(data.get("sub_price") or 0)
    if sub_name and sub_size <= 0:
        raise ValueError("چھوٹے یونٹ کا سائز بھی چاہیے: کتنے %s "
                         "= 1 %s بنتے ہیں (مثلاً kg -> g کے لیے 1000)۔" %
                         (sub_name, unit))
    if not sub_name and (sub_size or sub_rate_v):
        raise ValueError("چھوٹے یونٹ کا نام بھی چنیں (g / ml / pcs) - "
                         "بغیر نام کا سائز بے معنی ہے۔")
    if sub_rate_v < 0 or sub_size < 0:
        raise ValueError("چھوٹے یونٹ کی قدریں منفی نہیں ہو سکتیں "
                         "(0 = کوئی نہیں / خودکار)۔")
    vals = (name, bc, (data.get("category") or "General").strip(),
            money(data.get("cost")), price, money(data.get("stock")),
            int(money(data.get("low_limit") or business()["low_limit"])),
            expiry, unit, pack, pack_name, pack_rate,
            pack2, pack2_name, pack2_rate,
            sub_name, sub_size, sub_rate_v,
            1 if data.get("active", 1) else 0)
    if pid:
        run("UPDATE products SET name=?,barcode=?,category=?,cost=?,price=?,"
            "stock=?,low_limit=?,expiry=?,unit=?,pack_size=?,pack_name=?,"
            "pack_price=?,pack2_size=?,pack2_name=?,pack2_price=?,"
            "sub_unit=?,sub_size=?,sub_price=?,active=? WHERE id=?",
            vals + (pid,))
        _new = pid
    else:
        _new = run("INSERT INTO products(name,barcode,category,cost,price,"
                   "stock,low_limit,expiry,unit,pack_size,pack_name,"
                   "pack_price,pack2_size,pack2_name,pack2_price,"
                   "sub_unit,sub_size,sub_price,active,"
                   "created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                   "?)", vals + (utils.now(),))
    try:                                  # twin-store sync: share at once
        from sync import twinsync
        twinsync.out_product(_new)
    except Exception:
        pass
    return _new


def pack_text(prod):
    """Short pack tag for the table columns: '40 kg' for a plain pack,
    'Bora: 40 kg' when the pack has a name, and both levels joined for a
    carton item - with its INNER structure when the big pack is made of
    the small one: 'Dozen: 12 pcs + Carton: 12 x Dozen (144 pcs)'. ''
    for a plain piece/loose item (no pack at all)."""
    prod = prod or {}
    try:
        p1 = money(prod.get("pack_size") or 0)
        p2 = money(prod.get("pack2_size") or 0)
    except Exception:
        p1 = p2 = 0
    unit = prod.get("unit") or "pcs"
    out = []
    n1 = (prod.get("pack_name") or "").strip()
    if p1 > 0:
        out.append((n1 + ": " if n1 else "") + "%g %s" % (p1, unit))
    if p2 > 0:
        n2 = (prod.get("pack2_name") or "").strip()
        body = "%g %s" % (p2, unit)
        if p1 > 0:
            # a carton made of packets: say how many of the small pack
            # sit inside, the way a shopkeeper reads his own stock
            cnt = round(p2 / p1)
            if cnt > 1 and abs(p2 / p1 - cnt) < 0.0001:
                body = "%d x %s (%s)" % (cnt, n1 or "Pack", body)
        out.append((n2 + ": " if n2 else "") + body)
    return " + ".join(out)


def pack_rates(prod):
    """The sellable PACK levels of a product, cheapest level first:
    [{"name","size","rate","big","unit"} ...]. 'size' is how many BASE
    units the whole pack holds (stock always stays base units, so every
    kind of sale cuts the same shelf count) and 'rate' is the pack's OWN
    price - or (unit price x size) automatically when the custom pack
    price is left at 0. A bora of 40 kg and a carton of 144 pcs BOTH
    appear here for a two-level item."""
    prod = prod or {}
    price = money(prod.get("price") or 0)
    unit = prod.get("unit") or "pcs"
    out = []
    for name, size, rate, big in (
            (prod.get("pack_name"), prod.get("pack_size"),
             prod.get("pack_price"), False),
            (prod.get("pack2_name"), prod.get("pack2_size"),
             prod.get("pack2_price"), True)):
        size = money(size or 0)
        if size <= 0:
            continue
        rate = money(rate or 0)
        if rate <= 0:
            rate = money(price * size)      # 0 = auto: unit price x size
        out.append({"name": (name or "").strip() or
                    ("Carton" if big else "Pack"),
                    "size": size, "rate": rate, "big": big, "unit": unit})
    return out


def sub_rate(prod):
    """The SUB-UNIT of a product as a selling helper:
    {"name","size","rate","unit"} or None. 'size' = how many sub units
    make 1 base unit (1000 for kg -> g); 'rate' = price of ONE sub unit -
    the custom sub price, or the honest proportional price
    (unit price / size) when the custom one is left at 0."""
    prod = prod or {}
    name = (prod.get("sub_unit") or "").strip()
    size = money(prod.get("sub_size") or 0)
    if not name or size <= 0:
        return None
    price = money(prod.get("price") or 0)
    rate = money(prod.get("sub_price") or 0)
    if rate <= 0:
        rate = round(price / size, 6)       # 0 = auto: proportional
    return {"name": name, "size": size, "rate": rate,
            "unit": prod.get("unit") or "pcs"}


def sub_text(prod):
    """One-line conversion hint for the counter: '1 kg = 1000 g (Rs
    0.1520 / g)'. '' when the product has no sub-unit."""
    sub = sub_rate(prod)
    if not sub:
        return ""
    return "1 %s = %g %s (Rs %g / %s)" % (sub["unit"], sub["size"],
                                          sub["name"], sub["rate"],
                                          sub["name"])


def sub_short(prod):
    """The SHORT ladder for tight counters/lists: '1 bora = 40 kg'. ''
    when the product has no sub-unit (the full sentence with the rate,
    sub_text, lives on the wide Products / Inventory pages and on the
    sub-unit sell button itself)."""
    sub = sub_rate(prod)
    if not sub:
        return ""
    return "1 %s = %g %s" % (sub["unit"], sub["size"], sub["name"])


def next_product_code():
    """Auto product code: PRD-00001, PRD-00002 ... (always free)."""
    n = 0
    for r in q("SELECT barcode FROM products WHERE barcode LIKE 'PRD-%'"):
        try:
            n = max(n, int(str(r["barcode"])[4:]))
        except Exception:
            pass
    while True:
        n += 1
        code = "PRD-%05d" % n
        if not q("SELECT 1 x FROM products WHERE barcode=?", (code,),
                 one=True):
            return code


def get_product(pid):
    return q("SELECT * FROM products WHERE id=?", (pid,), one=True)


def find_barcode(code):
    return q("SELECT * FROM products WHERE barcode=? AND active=1",
             ((code or "").strip(),), one=True)


def list_products(search="", category="", low_only=False, limit=1000):
    sql, p = "SELECT * FROM products WHERE 1=1", []
    if search:
        like = "%" + search + "%"
        sql += " AND (name LIKE ? OR barcode LIKE ?)"
        p += [like, like]
    if category and category != "All":
        sql += " AND category=?"
        p.append(category)
    if low_only:
        sql += " AND stock<=low_limit"
    return q(sql + " ORDER BY name LIMIT ?", p + [limit])


def product_categories():
    rows = q("SELECT DISTINCT category c FROM products ORDER BY c")
    return [r["c"] for r in rows if r["c"]]


def del_product(pid):
    require_save()
    run("DELETE FROM products WHERE id=?", (pid,))


def import_csv(path):
    """Columns are read BY NAME when a header row is present (the modern
    set is name,barcode,category,cost,price,stock,low_limit,unit,
    sub_unit,sub_size,sub_price; an OLD pack_* header still works - its
    rows convert to the simple unit + sub-unit ladder through the same
    one honest function). Without a header the positional order is the
    modern one: name..low_limit,unit,sub_unit,sub_size,sub_price.
    Empty sub columns = a plain item; unit default pcs."""
    import csv
    NEW_POS = ("name", "barcode", "category", "cost", "price", "stock",
               "low_limit", "unit", "sub_unit", "sub_size", "sub_price")
    KNOWN = set(NEW_POS) | {"pack_size", "pack_name", "pack_price",
                            "pack2_name", "pack2_size", "pack2_price"}
    ok, errors = 0, []
    with open(path, newline="", encoding="utf-8-sig") as f:
        idx = None
        for i, row in enumerate(csv.reader(f), 1):
            if not row or not (row[0] or "").strip():
                continue
            if idx is None:
                lowered = [str(c).strip().lower() for c in row]
                if lowered[0] == "name":
                    idx = {k: n for n, k in enumerate(lowered)
                           if k in KNOWN}
                    continue
                idx = {k: n for n, k in enumerate(NEW_POS)}

            def _v(k, default=""):
                n = idx.get(k)
                return (row[n] if (n is not None and n < len(row))
                        else default)
            try:
                _payload = {
                    "name": _v("name"),
                    "barcode": _v("barcode"),
                    "category": _v("category"),
                    "cost": _v("cost", 0) or 0,
                    "price": _v("price", 0) or 0,
                    "stock": _v("stock", 0) or 0,
                    "low_limit": _v("low_limit", 5) or 5,
                    "unit": _v("unit") or "pcs",
                    "pack_size": _v("pack_size", 0) or 0,
                    "pack_name": _v("pack_name"),
                    "pack_price": _v("pack_price", 0) or 0,
                    "pack2_name": _v("pack2_name"),
                    "pack2_size": _v("pack2_size", 0) or 0,
                    "pack2_price": _v("pack2_price", 0) or 0,
                    "sub_unit": _v("sub_unit"),
                    "sub_size": _v("sub_size", 0) or 0,
                    "sub_price": _v("sub_price", 0) or 0}
                # an OLD pack-style row is rewritten to the simple
                # unit + sub-unit ladder by the same one honest function
                _conv = pack_to_unit(_payload)
                if _conv:
                    _payload.update(_conv)
                save_product(_payload)
                ok += 1
            except Exception as e:
                errors.append("Row %d: %s" % (i, e))
    return ok, errors


# ----------------------------------------------------------------------------
#  INVENTORY
# ----------------------------------------------------------------------------
def adjust_stock(pid, change, reason="", ref=""):
    require_save()
    prod = get_product(pid)
    if not prod:
        raise ValueError("پروڈکٹ نہیں ملا۔")
    new = money(prod["stock"]) + money(change)
    if new < 0:
        raise ValueError("اسٹاک منفی نہیں ہو سکتا (دستیاب: %g)۔"
                         % prod["stock"])
    run("UPDATE products SET stock=? WHERE id=?", (new, pid))
    run("INSERT INTO stock_log(ts,product_id,change,reason,ref) "
        "VALUES(?,?,?,?,?)", (utils.now(), pid, money(change), reason, ref))
    return new


def stock_history(pid, limit=200):
    return q("SELECT * FROM stock_log WHERE product_id=? ORDER BY id DESC "
             "LIMIT ?", (pid, limit))


def low_stock(limit=100):
    return q("SELECT * FROM products WHERE active=1 AND stock<=low_limit "
             "ORDER BY stock LIMIT ?", (limit,))


# ----------------------------------------------------------------------------
#  RAW INSERTS (for the demo loader - bypasses the demo guard, internal use)
# ----------------------------------------------------------------------------
def data_insert_product(name, barcode, category, cost, price, stock,
                        unit="pcs"):
    return run("INSERT INTO products(name,barcode,category,cost,price,stock,"
               "low_limit,unit,active,created) "
               "VALUES(?,?,?,?,?,?,5,?,?,'%s')" % utils.now(),
               (name, barcode, category, money(cost), money(price),
                money(stock), unit, 1))


def data_insert_customer(name, phone, addr):
    return run("INSERT INTO customers(name,phone,address,created) "
               "VALUES(?,?,?,?)", (name, phone, addr, utils.now()))


def data_insert_supplier(name, phone, addr):
    return run("INSERT INTO suppliers(name,phone,address,created) "
               "VALUES(?,?,?,?)", (name, phone, addr, utils.now()))


# ----------------------------------------------------------------------------
#  CUSTOMERS / SUPPLIERS
# ----------------------------------------------------------------------------
def save_customer(data, cid=None):
    require_save()
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("گاہک کا نام لازمی ہے")
    phone = "".join(ch for ch in (data.get("phone") or "") if ch.isdigit())
    zone = (data.get("zone") or "").strip()
    sector = (data.get("sector") or "").strip()
    if cid:
        run("UPDATE customers SET name=?,phone=?,address=?,zone=?,sector=? "
            "WHERE id=?",
            (name, phone, data.get("address", ""), zone, sector, cid))
        return cid
    return run("INSERT INTO customers(name,phone,address,zone,sector,"
               "created) VALUES(?,?,?,?,?,?)",
               (name, phone, data.get("address", ""), zone, sector,
                utils.now()))


def get_customer(cid):
    return q("SELECT * FROM customers WHERE id=?", (cid,), one=True)


def list_customers(search="", zone="", sector="", limit=500):
    """Customer list with optional ZONE / SECTOR filters + free search.
    Always A-to-Z by name so the on-screen order is clean and numbered."""
    sql = "SELECT * FROM customers WHERE 1=1"
    p = []
    if zone:
        sql += " AND zone=?"
        p.append(zone)
    if sector:
        sql += " AND sector=?"
        p.append(sector)
    if search:
        sql += " AND (name LIKE ? OR phone LIKE ?)"
        like = "%" + search + "%"
        p += [like, like]
    p.append(limit)
    return q(sql + " ORDER BY name COLLATE NOCASE, id LIMIT ?", tuple(p))


def zones():
    """All distinct customer zones (for filter combos)."""
    return [r["zone"] for r in
            q("SELECT DISTINCT zone FROM customers WHERE zone<>'' "
              "ORDER BY zone")]


def sectors():
    """All distinct customer sectors (for filter combos)."""
    return [r["sector"] for r in
            q("SELECT DISTINCT sector FROM customers WHERE sector<>'' "
              "ORDER BY sector")]


def del_customer(cid):
    require_save()
    run("DELETE FROM customers WHERE id=?", (cid,))


def customer_history(cid, limit=100):
    return q("SELECT * FROM sales WHERE customer_id=? ORDER BY id DESC "
             "LIMIT ?", (cid, limit))


# ----------------------------------------------------------------------------
#  CREDIT SYSTEM (UDHAR) - credit sales, pending balances, recovery, reminders
# ----------------------------------------------------------------------------
def customer_balance(cid):
    """Outstanding credit of one customer =
    SUM(credit left on sales) - SUM(recovery payments). Never negative."""
    sold = q("SELECT COALESCE(SUM(total-paid),0) s FROM sales "
             "WHERE customer_id=? AND status='done'", (cid,), one=True)["s"]
    got = q("SELECT COALESCE(SUM(amount),0) s FROM payments "
            "WHERE customer_id=?", (cid,), one=True)["s"]
    return money(max(0.0, sold - got))


def customer_ledger(cid):
    """The FULL KHATA of one customer, oldest first (like a paper ledger
    book): every udhar sale's UNPAID part enters as DEBIT, every recovery
    payment / return-adjust enters as CREDIT, and each line carries the
    running balance - the last balance is the live pending udhar."""
    rows = []
    for s in q("SELECT invoice_no,date,ts,total,paid,due_date,refunded "
               "FROM sales WHERE customer_id=? AND status='done' "
               "AND total-paid>0.005 ORDER BY ts", (cid,)):
        due = money(s["total"] - s["paid"])
        rows.append({"date": s["date"], "ts": s["ts"] or s["date"],
                     "ref": s["invoice_no"],
                     "detail": "ادھار سیل - بل %s%s%s" % (
                         s["invoice_no"],
                         (" (promised " + s["due_date"] + ")")
                         if s["due_date"] else "",
                         " (بعد میں مکمل واپس ہوئی)" if money(
                             s["refunded"] or 0) >= money(s["total"]) > 0
                         else ""),
                     "debit": due, "credit": 0.0})
    for p in q("SELECT id,date,ts,amount,method,note FROM payments "
               "WHERE customer_id=? ORDER BY ts", (cid,)):
        rows.append({"date": p["date"], "ts": p["ts"] or p["date"],
                     "ref": "RCP-%05d" % p["id"],
                     "detail": "Received (%s)%s" % (
                         p["method"] or "Cash",
                         (" - " + p["note"]) if p["note"] else ""),
                     "debit": 0.0, "credit": money(p["amount"])})
    rows.sort(key=lambda r: (r["ts"], r["ref"]))
    bal = 0.0
    for r in rows:
        bal = money(bal + r["debit"] - r["credit"])
        r["balance"] = bal
    return rows


def credit_list(search="", owing_only=True):
    """Customers with their outstanding credit (Udhar) balance."""
    rows = q(
        "SELECT c.*, "
        " COALESCE((SELECT SUM(total-paid) FROM sales s "
        "           WHERE s.customer_id=c.id AND s.status='done'),0) sold,"
        " COALESCE((SELECT SUM(amount) FROM payments p "
        "           WHERE p.customer_id=c.id),0) recovered,"
        " (SELECT MIN(due_date) FROM sales s2 WHERE s2.customer_id=c.id "
        "  AND s2.due_date<>'' AND s2.total>s2.paid) next_due "
        "FROM customers c ORDER BY c.name")
    out = []
    for r in rows:
        bal = money(max(0.0, r["sold"] - r["recovered"]))
        if owing_only and bal <= 0:
            continue
        if search and search.lower() not in (r["name"] + r["phone"]).lower():
            continue
        d = dict(r)
        d["balance"] = bal
        out.append(d)
    out.sort(key=lambda x: -x["balance"])
    return out


def credit_summary():
    """Dashboard numbers for the credit system."""
    rows = credit_list(owing_only=True)
    return {
        "outstanding": money(sum(r["balance"] for r in rows)),
        "customers": len(rows),
        "recovered_today": money(q(
            "SELECT COALESCE(SUM(amount),0) s FROM payments WHERE date=?",
            (utils.today(),), one=True)["s"]),
        "recovered_month": money(q(
            "SELECT COALESCE(SUM(amount),0) s FROM payments "
            "WHERE date>=?", (utils.today()[:8] + "01",), one=True)["s"]),
    }


def receive_payment(cid, amount, method="Cash", note="", username=""):
    """Record a RECOVERY payment against a customer's credit."""
    require_save()
    c = get_customer(cid)
    if not c:
        raise ValueError("گاہک نہیں ملا۔")
    amount = money(amount)
    if amount <= 0:
        raise ValueError("رقم 0 سے زیادہ ہونی چاہیے۔")
    bal = customer_balance(cid)
    if amount > bal + 0.005:
        raise ValueError("رقم بقایا بیلنس (%.2f) سے زیادہ ہے۔"
                         % bal)
    pid = run("INSERT INTO payments(date,ts,customer_id,customer_name,"
              "amount,method,note,username) VALUES(?,?,?,?,?,?,?,?)",
              (utils.today(), utils.now(), cid, c["name"], amount,
               method or "Cash", note or "", username or ""))
    log_activity("RECOVERY", "%s -> %.2f (%s)" % (c["name"], amount,
                                                  method or "Cash"),
                 username or "")
    try:                                  # twin-store sync: share at once
        from sync import twinsync
        twinsync.out_payment(pid)
    except Exception:
        pass
    return pid


def payments_of(cid, limit=200):
    return q("SELECT * FROM payments WHERE customer_id=? ORDER BY id DESC "
             "LIMIT ?", (cid, limit))


def today_recovery_by_user():
    """Today's RECOVERY money split by WHO received it - used by the
    Credit page strip: admin: Rs 1,200 (3) | cashier: Rs 800 (2)."""
    return q("SELECT COALESCE(NULLIF(username,''),'?') usr, COUNT(*) cnt, "
             "COALESCE(SUM(amount),0) total FROM payments WHERE date=? "
             "GROUP BY usr ORDER BY total DESC", (utils.today(),))


def list_payments(date_from="", date_to="", limit=1000):
    d1 = date_from or "0000-00-00"
    d2 = date_to or "9999"
    return q("SELECT * FROM payments WHERE date>=? AND date<=? "
             "ORDER BY id DESC LIMIT ?", (d1, d2, limit))


def due_reminders(days_ahead=0):
    """Credit sales whose PROMISED date has arrived (or is near) and the
    customer still owes money -> the automatic reminder list."""
    limit = utils.add_days(utils.today(), days_ahead)
    rows = q("SELECT s.*, c.name cname, c.phone cphone, c.zone czone,"
             " c.sector csector FROM sales s JOIN customers c"
             " ON c.id=s.customer_id WHERE s.due_date<>'' AND s.due_date<=?"
             " AND s.status='done' ORDER BY s.due_date", (limit,))
    out = []
    seen = set()
    for r in rows:
        if customer_balance(r["customer_id"]) <= 0:
            continue
        if r["customer_id"] in seen:
            continue
        seen.add(r["customer_id"])
        d = dict(r)
        d["balance"] = customer_balance(r["customer_id"])
        d["overdue_days"] = max(0, utils.days_between(r["due_date"],
                                                      utils.today()))
        out.append(d)
    return out


# ----------------------------------------------------------------------------
#  PRODUCT EXPIRY TRACKING
# ----------------------------------------------------------------------------
def expiring_products(days=None):
    """Products whose expiry date is within `days` (settings default) -
    including already-expired ones (they sort first)."""
    if days is None:
        days = business()["expiry_days"]
    limit = utils.add_days(utils.today(), days)
    rows = q("SELECT * FROM products WHERE active=1 AND expiry<>'' "
             "AND expiry<=? ORDER BY expiry", (limit,))
    out = []
    for r in rows:
        d = dict(r)
        d["days_left"] = utils.days_between(utils.today(), r["expiry"])
        out.append(d)
    return out


# ----------------------------------------------------------------------------
#  STAFF (EMPLOYEE) PERFORMANCE - sales + recovery per user
# ----------------------------------------------------------------------------
def sales_by_user(date_from="", date_to=""):
    d1 = date_from or "0000-00-00"
    d2 = date_to or "9999"
    # NET of refunds, ALWAYS - so the staff panel / staff CSV / staff PDF
    # match the SALES card exactly (no confusing double numbers ever)
    return q("SELECT username, COUNT(*) invoices, "
             "SUM(total - COALESCE(refunded,0)) sales "
             "FROM sales WHERE status='done' AND date>=? AND date<=? "
             "GROUP BY username ORDER BY sales DESC", (d1, d2))


def recovery_by_user(date_from="", date_to=""):
    d1 = date_from or "0000-00-00"
    d2 = date_to or "9999"
    return q("SELECT username, COUNT(*) receipts, SUM(amount) recovered "
             "FROM payments WHERE date>=? AND date<=? GROUP BY username "
             "ORDER BY recovered DESC", (d1, d2))


def save_supplier(data, sid=None):
    require_save()
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("سپلائر کا نام لازمی ہے")
    phone = "".join(ch for ch in (data.get("phone") or "") if ch.isdigit())
    if sid:
        run("UPDATE suppliers SET name=?,phone=?,address=? WHERE id=?",
            (name, phone, data.get("address", ""), sid))
        return sid
    return run("INSERT INTO suppliers(name,phone,address,created) "
               "VALUES(?,?,?,?)", (name, phone, data.get("address", ""),
                                   utils.now()))


def get_supplier(sid):
    return q("SELECT * FROM suppliers WHERE id=?", (sid,), one=True)


def list_suppliers(search="", limit=500):
    if search:
        like = "%" + search + "%"
        return q("SELECT * FROM suppliers WHERE name LIKE ? OR phone LIKE ? "
                 "ORDER BY name LIMIT ?", (like, like, limit))
    return q("SELECT * FROM suppliers ORDER BY name LIMIT ?", (limit,))


def del_supplier(sid):
    require_save()
    run("DELETE FROM suppliers WHERE id=?", (sid,))


def supplier_history(sid, limit=100):
    return q("SELECT * FROM purchases WHERE supplier_id=? ORDER BY id DESC "
             "LIMIT ?", (sid, limit))


# ----------------------------------------------------------------------------
#  SALES / POS
# ----------------------------------------------------------------------------
def next_no(prefix, table, col):
    """Next free invoice-style number for THIS prefix. Only rows starting
    with our own prefix are counted - a stray, imported or hand-fixed
    number (e.g. 'POS-DRILL2') can never confuse the counter. If the
    parse ever stumbles we WALK FORWARD to a free slot, so a number
    clash can NEVER again stop a shop from selling."""
    r = q("SELECT %s v FROM %s WHERE %s LIKE ? ORDER BY id DESC LIMIT 1"
          % (col, table, col), (prefix + "-%",), one=True)
    n = 1
    if r and r["v"]:
        try:
            n = int(str(r["v"]).split("-")[-1]) + 1
        except Exception:
            n = 1
    while q("SELECT %s FROM %s WHERE %s=?" % (col, table, col),
            ("%s-%05d" % (prefix, n),), one=True):
        n += 1                       # free slot guaranteed, always
    return "%s-%05d" % (prefix, n)


def sale_prefix():
    """Invoice prefix for THIS computer. Device 1 (the first PC) keeps the
    classic "POS-00001"; device 2 makes "POS2-00001" and so on - so two
    twin-store PCs on the SAME KEY can never create the same invoice
    number (clash-free sync)."""
    dv = (get_setting("device_no", "1") or "1").strip()
    return "POS" if dv in ("", "1") else "POS" + dv


# ----------------------------------------------------------------------------
#  TWIN-STORE SYNC markers (a guid of every row that arrived via sync)
# ----------------------------------------------------------------------------
def sync_is_seen(guid):
    return guid and q("SELECT 1 x FROM sync_seen WHERE guid=?",
                      (guid,), one=True) is not None


def sync_mark_seen(guid):
    if guid:
        run("INSERT OR IGNORE INTO sync_seen(guid,ts) VALUES(?,?)",
            (guid, utils.now()))


def save_sale(data):
    """data: {customer_id, items:[{product_id,name,qty,price,discount,cost }],
               discount, tax_percent, paid, payment, username}
    Returns (sale_id, invoice_no, total). Trial = FULL software for the
    whole month: NO sales cap - only the calendar clock limits it."""
    require_save()          # an ENDED trial waits for the key; nothing lost
    items = [dict(it) for it in (data.get("items") or [])]
    if not items:
        raise ValueError("ٹوکری خالی ہے - پہلے پروڈکٹس شامل کریں۔")
    inv = next_no(sale_prefix(), "sales", "invoice_no")
    subtotal = 0.0
    for it in items:
        # QTY also keeps up to 6 decimals: a rupee-typed sub-unit sale
        # (Rs 50 of ghee at 150/kg) is 0.333333 kg, and the line total
        # must still land on the EXACT rupees the customer handed over.
        it["qty"] = round(float(it.get("qty") or 0), 6)
        # PRICE keeps up to 6 decimals: a pack sold at its OWN rate carries
        # an exact per-unit price (a Rs 100 pack of 3 -> 33.333333) so the
        # line total always lands on the pack rate to the penny. Normal
        # prices are already clean 2-decimal values, untouched by this.
        it["price"] = round(float(it.get("price") or 0), 6)
        it["discount"] = money(it.get("discount"))
        if it["qty"] <= 0:
            raise ValueError("تعداد 0 سے زیادہ ہونی چاہیے: " +
                             str(it.get("name")))
        it["total"] = money(it["qty"] * it["price"] - it["discount"])
        if it["total"] < 0:
            raise ValueError("آئٹم کی کل رقم منفی نہیں ہو سکتی: " +
                             str(it.get("name")))
        it["cost"] = money(it.get("cost"))
        subtotal += it["total"]
        if it.get("product_id"):
            prod = get_product(it["product_id"])
            if not prod:
                raise ValueError("پروڈکٹ نہیں ملا: " + str(it.get("name")))
            # the caller may sell in the product's SUB-unit (0.5 kg of a
            # bora): the bill line stays in the unit the customer agreed
            # on, and the shelf is cut in MAIN units further below
            # (base_qty = qty / size) - one honest stock number, always.
            it["unit"] = (it.get("unit") or "").strip() or \
                         (prod.get("unit") or "pcs")
        else:
            it["unit"] = (it.get("unit") or "pcs").strip() or "pcs"
        it["sub_size"] = money(it.get("sub_size") or 0)
        if it["sub_size"] < 0:
            raise ValueError("چھوٹے یونٹ کا سائز منفی نہیں ہو سکتا: " +
                             str(it.get("name")))
        if it["sub_size"] > 0:
            it["base_qty"] = round(it["qty"] / it["sub_size"], 6)
            # the stored cost is per SOLD unit, so the profit maths
            # (price - cost) x qty stays honest on every kind of line
            it["cost"] = round(it["cost"] / it["sub_size"], 4)
        else:
            it["base_qty"] = it["qty"]
    # STOCK GUARD (total per product across the WHOLE bill): a product
    # repeated on several cart lines is counted together - the shelf can
    # never go below zero through ANY kind of bill, ever.
    need = {}
    for it in items:
        if it.get("product_id"):
            need[it["product_id"]] = round(need.get(it["product_id"], 0.0)
                                           + it["base_qty"], 6)
    for pid, qty in need.items():
        prod = get_product(pid)
        if prod and prod["stock"] + 0.0001 < qty:
            raise ValueError("اسٹاک ناکافی: %s - شیلف پر %g ہے مگر یہ "
                             "بل کل %g مانگتا ہے۔" % (prod["name"],
                                                          prod["stock"], qty))
    subtotal = money(subtotal)
    disc = money(data.get("discount"))
    if disc < 0 or disc > subtotal:
        raise ValueError("رعایت درست نہیں۔")
    taxp = float(data.get("tax_percent") or 0)
    tax = money((subtotal - disc) * taxp / 100.0)
    total = money(subtotal - disc + tax)
    paid = money(data.get("paid", total))
    change = money(max(0.0, paid - total))
    if paid < total and (data.get("payment") or "Cash") != "Credit":
        paid = total  # POS speed: partial amount is also accepted (change 0)
    cid = int(data.get("customer_id") or 0)
    if paid < total and not cid:
        raise ValueError("ادھار سیل کے لیے پہلے گاہک منتخب کریں۔")
    cname = ""
    if cid:
        c = get_customer(cid)
        if not c:
            raise ValueError("گاہک نہیں ملا۔")
        cname = c["name"]
    due = (data.get("due_date") or "").strip()
    if due:
        try:
            utils.days_between(due, due)           # validates YYYY-MM-DD
        except Exception as err:
            raise ValueError("وعدہ تاریخ YYYY-MM-DD جیسی ہو۔"
                             ) from err
    if paid < total and not due:
        due = utils.add_days(utils.today(), 7)     # default credit reminder
    sid = run("INSERT INTO sales(invoice_no,date,ts,customer_id,customer_name,"
              "subtotal,discount,tax,total,paid,change,payment,due_date,"
              "username,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (inv, utils.today(), utils.now(), cid, cname, subtotal, disc,
               tax, total, paid, change, data.get("payment", "Cash"), due,
               data.get("username", ""), "done"))
    run_many("INSERT INTO sale_items(sale_id,product_id,name,qty,price,"
             "discount,cost,total,unit,base_qty) "
             "VALUES(?,?,?,?,?,?,?,?,?,?)",
             [(sid, it.get("product_id") or 0, it.get("name", ""),
               it["qty"], it["price"], it["discount"], it["cost"],
               it["total"], it["unit"], it["base_qty"]) for it in items],)
    for it in items:
        if it.get("product_id"):
            run("UPDATE products SET stock=stock-? WHERE id=?",
                (it["base_qty"], it["product_id"]))
            run("INSERT INTO stock_log(ts,product_id,change,reason,ref) "
                "VALUES(?,?,?,?,?)",
                (utils.now(), it["product_id"], -it["base_qty"], "sale",
                 inv))
    log_activity("SALE", inv + " total=" + str(total),
                 data.get("username", ""))
    try:                                  # twin-store sync: share at once
        from sync import twinsync
        twinsync.out_sale(sid)
    except Exception:
        pass
    return sid, inv, total


def get_sale(sid):
    s = q("SELECT * FROM sales WHERE id=?", (sid,), one=True)
    if s:
        s["items"] = q("SELECT * FROM sale_items WHERE sale_id=? "
                       "ORDER BY id", (sid,))
    return s


def get_sale_by_inv(inv):
    s = q("SELECT * FROM sales WHERE invoice_no=?", (inv,), one=True)
    if s:
        s["items"] = q("SELECT * FROM sale_items WHERE sale_id=? "
                       "ORDER BY id", (s["id"],))
    return s


def list_sales(search="", date_from="", date_to="", payment="", limit=400):
    sql, p = "SELECT * FROM sales WHERE 1=1", []
    if search:
        like = "%" + search + "%"
        sql += " AND (invoice_no LIKE ? OR customer_name LIKE ?)"
        p += [like, like]
    if date_from:
        sql += " AND date>=?"
        p.append(date_from)
    if date_to:
        sql += " AND date<=?"
        p.append(date_to)
    if payment and payment != "All":
        sql += " AND payment=?"
        p.append(payment)
    return q(sql + " ORDER BY id DESC LIMIT ?", p + [limit])


def hold_sale(label, payload, username=""):
    require_save()
    return run("INSERT INTO held_sales(label,payload,ts,username) "
               "VALUES(?,?,?,?)",
               (label or "Hold", json.dumps(payload), utils.now(), username))


def list_held():
    return q("SELECT * FROM held_sales ORDER BY id DESC")


def get_held(hid):
    r = q("SELECT * FROM held_sales WHERE id=?", (hid,), one=True)
    if r:
        r["cart"] = json.loads(r["payload"])
    return r


def del_held(hid):
    run("DELETE FROM held_sales WHERE id=?", (hid,))


# ----------------------------------------------------------------------------
#  PURCHASES
# ----------------------------------------------------------------------------
def save_purchase(data, items):
    require_save()
    its = [dict(it) for it in (items or [])]
    if not its:
        raise ValueError("خریداری میں کم از کم ایک آئٹم شامل کریں۔")
    supid = int(data.get("supplier_id") or 0)
    supname = ""
    if supid:
        s = get_supplier(supid)
        if not s:
            raise ValueError("سپلائر نہیں ملا۔")
        supname = s["name"]
    total = 0.0
    for it in its:
        if not it.get("product_id"):
            raise ValueError("ہر آئٹم قطار میں پروڈکٹ منتخب کریں۔")
        prod = get_product(it["product_id"])
        if not prod:
            raise ValueError("پروڈکٹ نہیں ملا (id %s)۔" % it["product_id"])
        it["qty"] = money(it.get("qty"))
        it["cost"] = money(it.get("cost"))
        if it["qty"] <= 0:
            raise ValueError("تعداد 0 سے زیادہ ہونی چاہیے۔")
        it["name"] = prod["name"]
        it["total"] = money(it["qty"] * it["cost"])
        total += it["total"]
    pv = data.get("paid")
    paid_v = money(total) if pv in (None, "") else money(pv)
    pid = run("INSERT INTO purchases(date,supplier_id,supplier_name,total,"
              "paid,note,created) VALUES(?,?,?,?,?,?,?)",
              (data.get("date") or utils.today(), supid, supname,
               money(total), paid_v,
               data.get("note", ""), utils.now()))
    run_many("INSERT INTO purchase_items(purchase_id,product_id,name,qty,"
             "cost,total) VALUES(?,?,?,?,?,?)",
             [(pid, it["product_id"], it["name"], it["qty"], it["cost"],
               it["total"]) for it in its])
    for it in its:
        run("UPDATE products SET stock=stock+? WHERE id=?",
            (it["qty"], it["product_id"]))
        run("INSERT INTO stock_log(ts,product_id,change,reason,ref) "
            "VALUES(?,?,?,?,?)",
            (utils.now(), it["product_id"], it["qty"], "purchase",
             "PUR-%05d" % pid))
    log_activity("PURCHASE", "PUR-%05d total=%g" % (pid, total))
    try:                                  # twin-store sync: share at once
        from sync import twinsync
        twinsync.out_purchase(pid)
    except Exception:
        pass
    return pid


def list_purchases(search="", limit=300):
    if search:
        like = "%" + search + "%"
        return q("SELECT * FROM purchases WHERE supplier_name LIKE ? "
                 "ORDER BY id DESC LIMIT ?", (like, limit))
    return q("SELECT * FROM purchases ORDER BY id DESC LIMIT ?", (limit,))


def get_purchase(pid):
    r = q("SELECT * FROM purchases WHERE id=?", (pid,), one=True)
    if r:
        r["items"] = q("SELECT * FROM purchase_items WHERE purchase_id=?",
                       (pid,))
    return r


# ----------------------------------------------------------------------------
#  EXPENSES
# ----------------------------------------------------------------------------
def save_expense(data, eid=None):
    require_save()
    amt = money(data.get("amount"))
    if amt <= 0:
        raise ValueError("رقم 0 سے زیادہ ہونی چاہیے۔")
    vals = (data.get("date") or utils.today(),
            (data.get("category") or "Other").strip(),
            (data.get("note") or "").strip(), amt)
    if eid:
        run("UPDATE expenses SET date=?,category=?,note=?,amount=? "
            "WHERE id=?", vals + (eid,))
        return eid
    return run("INSERT INTO expenses(date,category,note,amount) "
               "VALUES(?,?,?,?)", vals)


def get_expense(eid):
    return q("SELECT * FROM expenses WHERE id=?", (eid,), one=True)


def list_expenses(search="", category="", date_from="", date_to="",
                  limit=400):
    sql, p = "SELECT * FROM expenses WHERE 1=1", []
    if search:
        sql += " AND note LIKE ?"
        p.append("%" + search + "%")
    if category and category != "All":
        sql += " AND category=?"
        p.append(category)
    if date_from:
        sql += " AND date>=?"
        p.append(date_from)
    if date_to:
        sql += " AND date<=?"
        p.append(date_to)
    return q(sql + " ORDER BY id DESC LIMIT ?", p + [limit])


def del_expense(eid):
    require_save()
    run("DELETE FROM expenses WHERE id=?", (eid,))


# ----------------------------------------------------------------------------
#  REPORTS / DASHBOARD
# ----------------------------------------------------------------------------
def sales_summary(date_from="", date_to=""):
    sql = "SELECT COUNT(*) c, COALESCE(SUM(total),0) t FROM sales"
    p = []
    where = ""
    if date_from:
        where += (" WHERE" if not where else " AND") + " date>=?"
        p.append(date_from)
    if date_to:
        where += (" WHERE" if not where else " AND") + " date<=?"
        p.append(date_to)
    r = q(sql + where, p, one=True)
    # NET money, the way a shopkeeper counts: a refund handed back inside
    # this same date range comes OUT of the range total (dashboard, daily
    # chart and the reports all use this one honest function).
    _ret_r = q("SELECT COALESCE(SUM(total),0) t FROM returns" + where,
               p, one=True)
    return r["c"], money(r["t"] - _ret_r["t"])


def profit_loss(date_from="", date_to=""):
    where, p = "", []
    if date_from:
        where += " AND s.date>=?"
        p.append(date_from)
    if date_to:
        where += " AND s.date<=?"
        p.append(date_to)
    sales_r = q("SELECT COALESCE(SUM(s.total),0) t, COALESCE(SUM(s.tax),0) x "
                "FROM sales s WHERE 1=1" + where, p, one=True)
    cost_r = q("SELECT COALESCE(SUM(i.qty*i.cost),0) c FROM sale_items i "
               "JOIN sales s ON s.id=i.sale_id WHERE 1=1" + where,
               p, one=True)
    exp_r = q("SELECT COALESCE(SUM(amount),0) e FROM expenses WHERE 1=1" +
              where.replace("s.date", "date"), p, one=True)
    # REFUNDS never enter profit: both the returned money and the returned
    # cost are peeled off inside the very same period (by return date)
    rw, rp = "", []
    if date_from:
        rw += " AND r.date>=?"
        rp.append(date_from)
    if date_to:
        rw += " AND r.date<=?"
        rp.append(date_to)
    back_r = q("SELECT COALESCE(SUM(r.total),0) t FROM returns r "
               "WHERE 1=1" + rw, rp, one=True)
    rcost_r = q("SELECT COALESCE(SUM(i.qty*i.cost),0) c FROM return_items i "
                "JOIN returns r ON r.id=i.return_id WHERE 1=1" + rw,
                rp, one=True)
    refunds = money(back_r["t"])
    gross = money(sales_r["t"] - back_r["t"])
    cost = money(cost_r["c"] - rcost_r["c"])
    exp = money(exp_r["e"])
    profit = money(gross - cost - exp)
    return {"gross": gross, "cost": cost, "expenses": exp,
            "profit": profit, "tax": money(sales_r["x"]),
            "refunds": refunds}


def sales_by_day(days=30):
    out = []
    for i in range(days - 1, -1, -1):
        d = (datetime.date.today() -
             datetime.timedelta(days=i)).isoformat()
        _c, t = sales_summary(d, d)
        out.append((d, t))
    return out


def inventory_value():
    r = q("SELECT COALESCE(SUM(stock*cost),0) c, COALESCE(SUM(stock*price),0)"
          " p FROM products WHERE active=1", one=True)
    return money(r["c"]), money(r["p"])


def dashboard_stats():
    tc, tt = sales_summary(utils.today())
    month_start = utils.today()[:8] + "01"
    _mc, mt = sales_summary(month_start, utils.today())
    cs = credit_summary()
    return {
        "today_count": tc, "today_total": tt,
        "month_total": mt,
        "products": q("SELECT COUNT(*) c FROM products WHERE active=1",
                      one=True)["c"],
        "low_stock": q("SELECT COUNT(*) c FROM products WHERE active=1 AND "
                       "stock<=low_limit", one=True)["c"],
        "customers": q("SELECT COUNT(*) c FROM customers", one=True)["c"],
        "suppliers": q("SELECT COUNT(*) c FROM suppliers", one=True)["c"],
        "held": q("SELECT COUNT(*) c FROM held_sales", one=True)["c"],
        "pl_month": profit_loss(month_start, utils.today())["profit"],
        "inv_value": inventory_value()[0],
        "credit_out": cs["outstanding"],
        "credit_customers": cs["customers"],
        "recov_today": cs["recovered_today"],
        "expiring": len(expiring_products()),
        "credit_due": len(due_reminders()),
    }


def global_search(text):
    """Dashboard search: products + sales + customers + suppliers ek sath."""
    like = "%" + (text or "") + "%"
    return {
        "products": q("SELECT * FROM products WHERE name LIKE ? OR barcode "
                      "LIKE ? ORDER BY name LIMIT 8", (like, like)),
        "sales": q("SELECT * FROM sales WHERE invoice_no LIKE ? OR "
                   "customer_name LIKE ? ORDER BY id DESC LIMIT 8",
                   (like, like)),
        "customers": q("SELECT * FROM customers WHERE name LIKE ? OR phone "
                       "LIKE ? ORDER BY name LIMIT 8", (like, like)),
        "suppliers": q("SELECT * FROM suppliers WHERE name LIKE ? OR phone "
                       "LIKE ? ORDER BY name LIMIT 8", (like, like)),
        "expenses": q("SELECT * FROM expenses WHERE note LIKE ? OR category "
                      "LIKE ? ORDER BY id DESC LIMIT 8", (like, like)),
    }


# ----------------------------------------------------------------------------
#  OPTIONAL ONLINE SYNC (best-effort, safe)
# ----------------------------------------------------------------------------
def export_sync_json(folder):
    """JSON snapshot of sales + summary - into a cloud folder (Drive/Dropbox)."""
    os.makedirs(folder, exist_ok=True)
    payload = {
        "app": "ApnaSoft POS 2.0", "ts": utils.now(),
        "company": COMPANY,
        "stats": dashboard_stats(),
        "sales": list_sales(limit=1000),
        "expenses": list_expenses(limit=1000),
    }
    fname = os.path.join(folder, "pos2-sync-" +
                         utils.now().replace(":", "").replace(" ", "-") +
                         ".json")
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, default=str)
    log_activity("SYNC-EXPORT", fname)
    return fname


def sql_dump_backup(folder=""):
    """SQL BACKUP: a .sql text dump of EVERYTHING (structure + data)."""
    folder = folder or backup_dirs()[0]
    os.makedirs(folder, exist_ok=True)
    fname = os.path.join(folder, "%s-backup-%s.sql" % (
        APP_TAG, utils.now().replace(":", "").replace(" ", "-")))
    with _lock:
        get_conn().commit()
        lines = list(get_conn().iterdump())
    with open(fname, "w", encoding="utf-8") as f:
        f.write("-- ApnaSoft POS 2.0 SQL backup | " + COMPANY + " | " +
                utils.now() + "\n")
        f.write("\n".join(lines))
    log_activity("BACKUP-SQL", fname)
    return fname


def json_backup(folder=""):
    """JSON BACKUP: every table exported to one readable .json file."""
    folder = folder or backup_dirs()[0]
    os.makedirs(folder, exist_ok=True)
    tables = ["products", "customers", "suppliers", "sales", "sale_items",
              "purchases", "purchase_items", "expenses", "payments",
              "users", "settings"]
    payload = {"app": "ApnaSoft POS 2.0", "company": COMPANY,
               "ts": utils.now(), "tables": {}}
    for t in tables:
        try:
            payload["tables"][t] = [dict(r) for r in
                                    q("SELECT * FROM " + t)]
        except Exception:
            payload["tables"][t] = []
    for u in payload["tables"].get("users", []):
        u.pop("passhash", None)
        u.pop("salt", None)
    fname = os.path.join(folder, "%s-backup-%s.json" % (
        APP_TAG, utils.now().replace(":", "").replace(" ", "-")))
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, default=str)
    log_activity("BACKUP-JSON", fname)
    return fname


def webhook_sync(url):
    """POST stats to the user's own webhook URL (urllib, safe, optional)."""
    import urllib.request
    payload = json.dumps({"app": "ApnaSoft POS 2.0", "ts": utils.now(),
                          "stats": dashboard_stats()}).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            body = r.read().decode("utf-8", "replace")[:200]
        log_activity("SYNC-WEBHOOK", "ok " + str(body[:80]))
        return True, "Webhook OK: " + body[:80]
    except Exception as e:
        log_activity("SYNC-WEBHOOK", "fail " + str(e)[:120])
        return False, "Webhook fail: " + str(e)[:120]


# ----------------------------------------------------------------------------
#  STRONG BACKUP / RESTORE (auto on close + restore-only in settings)
# ----------------------------------------------------------------------------
def backup_dirs():
    """Every safe place that gets an automatic backup copy on CLOSE.
    We copy to the app folder, the Documents folder, EVERY other drive
    found on the PC (D:, E:, a plugged-in USB...) - so even if WINDOWS is
    reinstalled, the backups on the other drive / USB stay fully safe -
    PLUS any folder the USER adds from Settings (their own USB / drive
    folder joins this list forever, until they remove it)."""
    dirs = [os.path.join(data_dir(), "backups")]
    for extra in (get_setting("backup_xdirs", "") or "").split("|"):
        extra = extra.strip()
        if extra:
            dirs.append(extra)
    try:
        home = os.path.expanduser("~")
        docs = os.path.join(home, "Documents") if os.path.isdir(
            os.path.join(home, "Documents")) else home
        dirs.append(os.path.join(docs, "ApnaSoftBackups", APP_TAG))
    except Exception:
        pass
    try:
        if os.name == "nt":
            # scan EVERY drive letter except the system drive C:
            for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
                try:
                    root = letter + ":" + chr(92)
                    if os.path.isdir(root):
                        dirs.append(os.path.join(root + "ApnaSoftBackups",
                                                 APP_TAG))
                except Exception:
                    pass
        else:
            # Linux: every mounted drive / USB under the media folders
            for base in ("/media", "/mnt", "/run/media"):
                try:
                    stack = [base]
                    while stack:
                        cur = stack.pop()
                        for sub in sorted(os.listdir(cur)):
                            p = os.path.join(cur, sub)
                            if os.path.isdir(p):
                                if os.access(p, os.W_OK):
                                    dirs.append(os.path.join(
                                        p, "ApnaSoftBackups", APP_TAG))
                                if cur != base:
                                    stack.append(p)
                                elif len(stack) < 12:
                                    stack.append(p)
                except Exception:
                    pass
    except Exception:
        pass
    dedup = []
    for d in dirs:
        if d and d not in dedup:
            dedup.append(d)
    return dedup


def prune_backups(folder, keep=30):
    try:
        files = [os.path.join(folder, f) for f in os.listdir(folder)
                 if f.endswith(".db")]
        files.sort(key=os.path.getmtime, reverse=True)
        for old in files[keep:]:
            try:
                os.remove(old)
            except Exception:
                pass
    except Exception:
        pass


def strong_backup():
    """A safe copy of the live DB in ALL available safe places."""
    saved = []
    src = db_path()
    if not os.path.exists(src):
        return saved
    with _lock:
        get_conn().commit()
        fresh = shutil.copy2 if os.path.exists(src) else None
    stamp = utils.now().replace(":", "").replace(" ", "-")
    for folder in backup_dirs():
        try:
            os.makedirs(folder, exist_ok=True)
            fname = os.path.join(folder, "%s-backup-%s.db" % (APP_TAG, stamp))
            n = 0
            while os.path.exists(fname):
                n += 1
                fname = os.path.join(folder, "%s-backup-%s-%d.db" %
                                     (APP_TAG, stamp, n))
            dest = sqlite3.connect(fname)
            with _lock:
                get_conn().backup(dest)
            dest.close()
            saved.append(fname)
            prune_backups(folder)
        except Exception:
            try:
                if fresh:
                    fresh(src, fname)
                    saved.append(fname)
            except Exception:
                pass
    if saved:
        log_activity("BACKUP", " | ".join(saved)[:380])
    return saved


def backup_to_folder(folder):
    """Save a FRESH, complete backup copy into the folder the USER chooses
    (e.g. a USB drive or any other folder they pick)."""
    folder = (folder or "").strip()
    if not folder:
        raise ValueError("کوئی فولڈر منتخب نہیں ہوا۔")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as err:
            raise ValueError("یہ فولڈر استعمال نہیں ہو سکتا۔ کوئی اور "
                             "منتخب کریں۔") from err
    stamp = utils.now().replace(":", "").replace(" ", "-")
    fname = os.path.join(folder, "%s-backup-%s.db" % (APP_TAG, stamp))
    n = 0
    while os.path.exists(fname):
        n += 1
        fname = os.path.join(folder, "%s-backup-%s-%d.db" %
                             (APP_TAG, stamp, n))
    try:
        dest = sqlite3.connect(fname)
        with _lock:
            get_conn().backup(dest)
        dest.close()
    except Exception:
        shutil.copy2(db_path(), fname)
    log_activity("BACKUP", "user-chosen folder: " + fname[:360])
    return fname


def live_backup(keep=3):
    """LIVE AUTO-BACKUP (the every-few-minutes safety net): a small rolling
    copy of the WHOLE database lands in EVERY safe place while the app is
    OPEN. Each copy is written to a .tmp file first and then atomically
    renamed - so even a power cut in the exact middle of writing can never
    leave a half-written, unreadable backup file."""
    saved = []
    src = db_path()
    if not os.path.exists(src):
        return saved
    with _lock:
        get_conn().commit()
    try:
        slot = int(get_setting("live_backup_slot", "0") or 0)
    except Exception:
        slot = 0
    slot = slot % max(1, keep)
    name = "%s-live-%d" % (APP_TAG, slot + 1)
    for folder in backup_dirs():
        try:
            os.makedirs(folder, exist_ok=True)
            final = os.path.join(folder, name + ".db")
            tmp = os.path.join(folder, name + ".tmp")
            dest = sqlite3.connect(tmp)
            with _lock:
                get_conn().backup(dest)
            dest.close()
            os.replace(tmp, final)        # atomic swap - never a half file
            saved.append(final)
            prune_backups(folder)
        except Exception:
            continue
    set_setting("live_backup_slot", str((slot + 1) % max(1, keep)))
    if saved:
        set_setting("live_backup_last", utils.now())
    return saved


def excel_zip_export(path):
    """FULL EXCEL EXPORT: every table as its own .csv file (Excel opens a
    .csv directly - no installs, fully offline) packed inside one .zip."""
    import csv
    import io
    import zipfile
    tables = [r["name"] for r in q(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for t in tables:
            rows = q("SELECT * FROM \"%s\"" % t)
            buf = io.StringIO()
            wr = csv.writer(buf)
            cols = rows[0].keys() if rows else []
            if cols:
                wr.writerow(list(cols))
                for r in rows:
                    wr.writerow([r[c] for c in cols])
            z.writestr(t + ".csv", buf.getvalue())
        z.writestr(
            "README-EXCEL.txt",
            "ApnaSoft POS 2.0 - مکمل ایکسل ایکسپورٹ\n"
            "اس zip کی ہر .csv فائل سیدھا Excel میں کھلتی ہے "
            "(ڈبل کلک کریں)۔\nہر ٹیبل کی اپنی فائل: پروڈکٹس، گاہک، "
            "فروختیں، آئٹمز، اخراجات، ادائیگیاں وغیرہ۔\n"
            "ApnaSoft Software Solutions | blazinginfo.com\n")
    return path


def list_backups():
    out = []
    for folder in backup_dirs():
        if os.path.isdir(folder):
            for f in sorted(os.listdir(folder), reverse=True):
                if f.endswith(".db"):
                    full = os.path.join(folder, f)
                    try:
                        out.append({"path": full, "name": f,
                                    "size": os.path.getsize(full),
                                    "ts": utils.now()})
                    except Exception:
                        pass
    return out


def is_valid_backup(path):
    try:
        if not path or not os.path.exists(path):
            return False
        con = sqlite3.connect(path)
        cur = con.execute("SELECT name FROM sqlite_master WHERE "
                          "type='table'")
        names = {r[0] for r in cur.fetchall()}
        con.close()
        return "settings" in names and "sales" in names
    except Exception:
        return False


def restore_backup(src_path):
    if not is_valid_backup(src_path):
        return False, "یہ فائل ApnaSoft POS 2.0 کا درست بیک اپ نہیں ہے۔"
    try:
        dst = db_path()
        with _lock:
            get_conn().commit()
        safety = dst + ".pre-restore-" + \
            utils.now().replace(":", "").replace(" ", "-")
        if os.path.exists(dst):
            shutil.copy2(dst, safety)
        # WAL-speed side care: the OLD connection must close BEFORE the
        # file is swapped - closing a WAL connection checkpoints its frames
        # (like that big delete you are restoring away) straight into the
        # fresh file and the undo would be lost again.
        reset_conn()
        shutil.copy2(src_path, dst)
        # any STALE -wal/-shm side-files of the old database must also go
        for ext in ("-wal", "-shm"):
            try:
                os.remove(dst + ext)
            except OSError:
                pass
        log_activity("RESTORE", src_path)
        return True, "بحالی مکمل! اب سافٹ ویئر دوبارہ کھولیں۔"
    except Exception as e:
        return False, "بحالی ناکام: %s" % e
# (appended to database/db.py by the mega-batch build)


# ============================================================================
#  DAY FLOW - daily OPENING / CLOSING cash with FULL reconciliation
#  Rule: closing EXPECTED = opening + today's CASH-IN (cash sales + cash
#  recoveries) - today's CASH-OUT (expenses + cash refunds) - card/digital
#  sales are NOT drawer cash, so they are tracked but excluded.
# ============================================================================
def day_row(date=None):
    date = date or utils.today()
    return q("SELECT * FROM day_flow WHERE date=?", (date,), one=True)


def day_expected_cash(date=None):
    """Live expected drawer cash for a date (opening + cash in - cash out).
    Returns a full breakdown dict so the close screen can show EVERY rupee
    (missing / equal / extra is then counted against it)."""
    date = date or utils.today()
    row = day_row(date) or {}
    opening = money(row.get("opening") or 0)
    cash_sales = q("SELECT COALESCE(SUM(paid),0) s FROM sales WHERE date=? "
                   "AND payment='Cash' AND status='done'", (date,),
                   one=True)["s"]
    cash_recovery = q("SELECT COALESCE(SUM(amount),0) s FROM payments "
                      "WHERE date=? AND method='Cash'", (date,),
                      one=True)["s"]
    cash_refund = q("SELECT COALESCE(SUM(total),0) s FROM returns "
                    "WHERE date=? AND mode='Cash back'", (date,),
                    one=True)["s"]
    expenses = q("SELECT COALESCE(SUM(amount),0) s FROM expenses "
                 "WHERE date=?", (date,), one=True)["s"]
    card_sales = q("SELECT COALESCE(SUM(paid),0) s FROM sales WHERE date=? "
                   "AND payment IN ('Card','Digital') AND status='done'",
                   (date,), one=True)["s"]
    udhar_given = q("SELECT COALESCE(SUM(total-paid),0) s FROM sales "
                    "WHERE date=? AND status='done'", (date,),
                    one=True)["s"]
    expected = money(opening + money(cash_sales) + money(cash_recovery)
                     - money(expenses) - money(cash_refund))
    return {"date": date, "opening": opening,
            "cash_sales": money(cash_sales),
            "cash_recovery": money(cash_recovery),
            "cash_refund": money(cash_refund),
            "expenses": money(expenses), "card_sales": money(card_sales),
            "udhar_given": money(udhar_given), "expected": expected,
            "is_open": bool(row and row.get("open_ts")),
            "is_closed": bool(row and row.get("close_ts")),
            "closing_actual": row.get("closing_actual"),
            "closing_expected": row.get("closing_expected"),
            "close_note": (row or {}).get("close_note", "")}


def open_day(opening, username=""):
    """Start today with the cash in the drawer. Yesterday's actual closing
    is offered by the screen as the default."""
    require_save()
    date = utils.today()
    if day_row(date) and day_row(date).get("open_ts"):
        raise ValueError("آج کا دن پہلے ہی کھلا ہے۔ اسے بند کریں تو "
                         "کل نیا دن شروع ہو گا۔")
    run("INSERT OR REPLACE INTO day_flow(date,opening,open_ts,open_user,"
        "closing_expected,closing_actual,close_ts,close_user,close_note) "
        "VALUES(?,?,?,?,COALESCE((SELECT closing_expected FROM day_flow "
        "WHERE date=?),NULL),COALESCE((SELECT closing_actual FROM day_flow "
        "WHERE date=?),NULL),(SELECT close_ts FROM day_flow WHERE date=?),"
        "(SELECT close_user FROM day_flow WHERE date=?),"
        "(SELECT close_note FROM day_flow WHERE date=?))",
        (date, money(opening), utils.now(), username, date, date, date,
         date, date))
    log_activity("DAY-OPEN", date + " opening=" + str(money(opening)),
                 username)
    return date


def _day_verdict(diff):
    return ("برابر - بالکل صحیح حساب!" if abs(diff) < 0.005 else
            ("کمی Rs %.2f" % -diff if diff < 0 else
             "زیادتی Rs %.2f" % diff))


def close_day(actual_cash, username="", note=""):
    """Close today: compare the counted cash with the expected cash and
    record the verdict (SHORT / EQUAL / EXTRA) inside the note field."""
    require_save()
    date = utils.today()
    b = day_expected_cash(date)
    if not b["is_open"]:
        raise ValueError("پہلے دن کھولیں (دن کھولیں بٹن)۔")
    if b["is_closed"]:
        raise ValueError("آج کا دن پہلے ہی بند ہو چکا ہے۔")
    actual = money(actual_cash)
    diff = money(actual - b["expected"])
    verdict = _day_verdict(diff)
    full_note = ((note + "  |  ") if note else "") + verdict
    run("UPDATE day_flow SET closing_expected=?, closing_actual=?,"
        "close_ts=?, close_user=?, close_note=? WHERE date=?",
        (b["expected"], actual, utils.now(), username, full_note, date))
    log_activity("DAY-CLOSE", date + " expected=%s actual=%s %s" %
                 (b["expected"], actual, verdict), username)
    return {"expected": b["expected"], "actual": actual, "diff": diff,
            "verdict": verdict}


def _refresh_closed_day(date):
    """After an edit, a CLOSED day's expected cash and its verdict are
    figured out again from the live numbers (edits never leave a stale
    hisaab behind)."""
    row = day_row(date)
    if not row or not row.get("close_ts"):
        return
    exp = day_expected_cash(date)["expected"]
    actual = money(row.get("closing_actual") or 0)
    diff = money(actual - exp)
    run("UPDATE day_flow SET closing_expected=?, close_note=? "
        "WHERE date=?", (exp, _day_verdict(diff) + "  (edited)", date))


def update_day_opening(date, opening, username=""):
    """Fix a typed-wrong OPENING for any date (mistakes happen). If that
    day was already closed, its expected cash + verdict are recounted."""
    require_save()
    row = day_row(date)
    if not row or not row.get("open_ts"):
        raise ValueError("اس تاریخ کا کوئی کھلا اندراج نہیں جسے ٹھیک کیا جا سکے۔")
    run("UPDATE day_flow SET opening=?, open_user=? WHERE date=?",
        (money(opening), username, date))
    log_activity("DAY-EDIT-OPEN", date + " opening=" +
                 str(money(opening)), username)
    _refresh_closed_day(date)


def update_day_closing(date, actual_cash, username=""):
    """Fix a typed-wrong counted CLOSING for an already CLOSED date; the
    verdict (EQUAL / MISSING / EXTRA) is recounted at once."""
    require_save()
    row = day_row(date)
    if not row or not row.get("close_ts"):
        raise ValueError("صرف بند دن کی گنی گئی نقدی ٹھیک کی جا سکتی ہے۔")
    run("UPDATE day_flow SET closing_actual=?, close_user=? WHERE date=?",
        (money(actual_cash), username, date))
    log_activity("DAY-EDIT-CLOSE", date + " actual=" +
                 str(money(actual_cash)), username)
    _refresh_closed_day(date)


def delete_day(date, username=""):
    """Remove a day entry completely (only the day-book line goes away;
    sales, expenses and payments of that date are never touched)."""
    require_save()
    row = day_row(date)
    if not row:
        raise ValueError("دن کا ایسا کوئی اندراج نہیں۔")
    run("DELETE FROM day_flow WHERE date=?", (date,))
    log_activity("DAY-DELETE", date + " (opening=%s, closed=%s)" %
                 (row.get("opening"), bool(row.get("close_ts"))), username)


def day_history(limit=31):
    return q("SELECT * FROM day_flow ORDER BY date DESC LIMIT ?",
             (limit,))


# ============================================================================
#  SALE RETURN / REFUND - stock goes BACK to the shelf, money is recorded,
#  and partial returns are allowed (never more than what was sold).
# ============================================================================
def returned_qty_map(sale_id):
    """product_id -> total qty already returned for this sale."""
    m = {}
    for r in q("SELECT ri.product_id pid, COALESCE(SUM(ri.qty),0) q "
               "FROM return_items ri JOIN returns r ON r.id=ri.return_id "
               "WHERE r.sale_id=? GROUP BY ri.product_id", (sale_id,)):
        if r["pid"]:
            m[r["pid"]] = round(r["q"], 6)
    return m


def save_return(data):
    """data: {sale_id, items:[{product_id,name,qty,price,cost}], reason,
              mode ('Cash back'|'Reduce udhar'), username}
    Restores stock, writes the return, and (for udhar mode) nothing else is
    needed: the customer balance formula counts this return automatically
    because payments/balance read the RETURN total separately below."""
    require_save()
    sale = get_sale(int(data.get("sale_id") or 0))
    if not sale:
        raise ValueError("اصل سیل نہیں ملی۔")
    items = [dict(it) for it in (data.get("items") or []) if
             money(it.get("qty")) > 0]
    if not items:
        raise ValueError("واپسی کے لیے کچھ منتخب نہیں - کم از کم "
                         "ایک آئٹم کی تعداد 0 سے زیادہ کریں۔")
    already = returned_qty_map(sale["id"])
    sold = {}
    for it in sale["items"]:
        pid = it.get("product_id") or 0
        sold[pid] = round(sold.get(pid, 0.0) + float(it["qty"] or 0), 6)
    # a SUB-UNIT line returns in the unit it was sold in, so the shelf
    # is refilled in MAIN units through the exact ratio of the original
    # bill line (matched by product AND line name - a loose line and a
    # sub-unit line of one product keep their own honest ratios)
    ratio = {}
    for it in sale["items"]:
        pid = it.get("product_id") or 0
        sq = float(it.get("qty") or 0)
        if pid and sq > 0:
            ratio[(pid, it.get("name") or "")] = \
                float(it.get("base_qty") or sq) / sq
    total = 0.0
    for it in items:
        it["qty"] = round(float(it.get("qty") or 0), 6)
        it["price"] = money(it.get("price"))
        it["cost"] = money(it.get("cost"))
        it["base_qty"] = round(it["qty"] * ratio.get(
            (it.get("product_id") or 0, it.get("name") or ""), 1.0), 6)
        if it["qty"] <= 0:
            raise ValueError("واپسی تعداد 0 سے زیادہ ہونی چاہیے: " +
                             str(it.get("name")))
        pid = it.get("product_id") or 0
        left = round(sold.get(pid, 0.0) - already.get(pid, 0.0), 6)
        if pid and it["qty"] > left + 0.0001:
            raise ValueError("%g x %s واپس نہیں ہو سکتا - بل میں %g بکے اور "
                             "%g پہلے ہی واپس آ چکے (زیادہ سے زیادہ باقی: %g)۔"
                             % (it["qty"], it.get("name"), sold.get(pid, 0),
                                already.get(pid, 0), left))
        it["total"] = money(it["qty"] * it["price"])
        total += it["total"]
    total = money(total)
    rno = next_no("POSR", "returns", "return_no")
    rid = run("INSERT INTO returns(return_no,date,ts,sale_id,invoice_no,"
              "customer_name,total,reason,mode,username) "
              "VALUES(?,?,?,?,?,?,?,?,?,?)",
              (rno, utils.today(), utils.now(), sale["id"],
               sale["invoice_no"], sale["customer_name"], total,
               (data.get("reason") or "").strip(),
               (data.get("mode") or "Cash back"),
               data.get("username", "")))
    run_many("INSERT INTO return_items(return_id,product_id,name,qty,price,"
             "cost,total,base_qty) VALUES(?,?,?,?,?,?,?,?)",
             [(rid, it.get("product_id") or 0, it.get("name", ""),
               it["qty"], it["price"], it["cost"], it["total"],
               it["base_qty"]) for it in items])
    for it in items:
        pid = it.get("product_id") or 0
        if pid:
            run("UPDATE products SET stock=stock+? WHERE id=?",
                (it["base_qty"], pid))
            run("INSERT INTO stock_log(ts,product_id,change,reason,ref) "
                "VALUES(?,?,?,?,?)",
                (utils.now(), pid, it["base_qty"], "return", rno))
    # "Reduce udhar" mode: the returned value is booked as if the customer
    # paid it back -> their balance falls automatically (payment with a
    # crystal-clear method name, so the recovery report stays readable).
    if (data.get("mode") or "") == "Reduce udhar" and sale["customer_id"]:
        run("INSERT INTO payments(date,ts,customer_id,customer_name,amount,"
            "method,note,username) VALUES(?,?,?,?,?,?,?,?)",
            (utils.today(), utils.now(), sale["customer_id"],
             sale["customer_name"], total, "Return adjust",
             "Return " + rno + " vs " + sale["invoice_no"],
             data.get("username", "")))
    # STAMP the original invoice: it now carries the refunded amount, so the
    # Sales list shows a REFUND / PART mark on it and net-money functions
    # (sales_summary, profit_loss) cut exactly this value. The sale row
    # itself is never deleted - the full honest trail always stays.
    run("UPDATE sales SET refunded=COALESCE(refunded,0)+? WHERE id=?",
        (total, sale["id"]))
    log_activity("RETURN", rno + " vs " + sale["invoice_no"] + " total=" +
                 str(total) + " mode=" + str(data.get("mode")),
                 data.get("username", ""))
    return rid, rno, total


def get_return(rid):
    r = q("SELECT * FROM returns WHERE id=?", (rid,), one=True)
    if r:
        r["items"] = q("SELECT * FROM return_items WHERE return_id=? "
                       "ORDER BY id", (rid,))
    return r


def list_returns(date_from="", date_to="", limit=200):
    where, p = "", []
    if date_from:
        where += " AND date>=?"
        p.append(date_from)
    if date_to:
        where += " AND date<=?"
        p.append(date_to)
    return q("SELECT * FROM returns WHERE 1=1" + where +
             " ORDER BY id DESC LIMIT ?", p + [limit])


def returns_of_sale(sale_id):
    return q("SELECT * FROM returns WHERE sale_id=? ORDER BY id DESC",
             (sale_id,))


def qty_for_amount(amount, price):
    """THE SHOPKEEPER'S FAVOURITE: customer says 'Rs 37 of sugar' -
    type the MONEY and the quantity is computed by itself (price per unit).
    Rounded to 2 decimals, minimum 0.01 so a bill never carries 0 qty."""
    price = money(price)
    if price <= 0:
        raise ValueError("پہلے آئٹم کی قیمت لکھیں، پھر روپے -> تعداد استعمال کریں۔")
    amt = money(amount)
    if amt <= 0:
        raise ValueError("پہلے روپے لکھیں (0 سے زیادہ)۔")
    q_ = round(amt / price, 2)
    return max(q_, 0.01)


# ============================================================================
#  EMPLOYEES + SALARY - staff list, monthly salary record; every salary
#  payment ALSO writes an expense (category Salary) so the money books stay
#  complete automatically - nothing is ever missing from the hisaab.
# ============================================================================
def save_employee(data, eid=None):
    require_save()
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("ملازم کا نام لازمی ہے۔")
    sal = money(data.get("salary"))
    if sal < 0:
        raise ValueError("تنخواہ منفی نہیں ہو سکتی۔")
    vals = (name, (data.get("phone") or "").strip(),
            (data.get("role") or "Staff").strip(), sal,
            (data.get("joined") or utils.today()).strip(),
            (data.get("note") or "").strip(),
            1 if data.get("active", 1) else 0)
    if eid:
        run("UPDATE employees SET name=?,phone=?,role=?,salary=?,joined=?,"
            "note=?,active=? WHERE id=?", vals + (eid,))
        return eid
    return run("INSERT INTO employees(name,phone,role,salary,joined,note,"
               "active,created) VALUES(?,?,?,?,?,?,?,?)",
               vals + (utils.now(),))


def get_employee(eid):
    return q("SELECT * FROM employees WHERE id=?", (eid,), one=True)


def list_employees(show_all=True):
    if show_all:
        return q("SELECT * FROM employees ORDER BY active DESC, name")
    return q("SELECT * FROM employees WHERE active=1 ORDER BY name")


def del_employee(eid):
    require_save()
    run("DELETE FROM employees WHERE id=?", (eid,))


def pay_salary(eid, amount, month="", note="", username=""):
    """Pay a salary: one salary_payments row + one matching EXPENSE row
    (category Salary) so the cash book and profit/loss both count it."""
    require_save()
    emp = get_employee(int(eid))
    if not emp:
        raise ValueError("ملازم نہیں ملا۔")
    amt = money(amount)
    if amt <= 0:
        raise ValueError("رقم 0 سے زیادہ ہونی چاہیے۔")
    month = (month or utils.this_month()).strip()
    dup = q("SELECT id FROM salary_payments WHERE employee_id=? AND month=?",
            (emp["id"], month), one=True)
    if dup:
        raise ValueError("%s %s کے لیے پہلے ہی ادا شدہ ہے۔ غلطی ہو تو "
                         "پہلے وہ ادائیگی ڈیلیٹ کریں۔" % (emp["name"], month))
    sid = run("INSERT INTO salary_payments(employee_id,employee_name,month,"
              "amount,date,ts,note,username) VALUES(?,?,?,?,?,?,?,?)",
              (emp["id"], emp["name"], month, amt, utils.today(),
               utils.now(), (note or "").strip(), username))
    # the same money also exists as an expense -> cash book stays true
    run("INSERT INTO expenses(date,category,note,amount) VALUES(?,?,?,?)",
        (utils.today(), "Salary",
         "Salary %s - %s" % (month, emp["name"]), amt))
    log_activity("SALARY", "%s %s = %s" % (emp["name"], month, amt),
                 username)
    return sid


def salary_history(eid=None, limit=200):
    if eid:
        return q("SELECT * FROM salary_payments WHERE employee_id=? "
                 "ORDER BY id DESC LIMIT ?", (eid, limit))
    return q("SELECT * FROM salary_payments ORDER BY id DESC LIMIT ?",
             (limit,))
