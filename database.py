import sqlite3
import json
import os
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from contextlib import contextmanager
from config import CONFIG
DB_FOLDER = CONFIG["database_folder"]
SHARED_DB_PATH = os.path.join(DB_FOLDER, "shared.db")
os.makedirs(DB_FOLDER, exist_ok=True)
@dataclass
class User:
    id: int
    username: str
    password_hash: str
    created_at: str
    is_admin: bool = False
    profile_picture: Optional[str] = None
    profile_name: Optional[str] = None
    dashboard_instance_id: Optional[int] = None
@dataclass
class Category:
    id: int
    user_id: int
    instance_id: Optional[int]
    name: str
    color: str
    is_income: bool
    created_at: str
@dataclass
class Source:
    id: int
    user_id: int
    instance_id: Optional[int]
    name: str
    type: str
    is_default: bool
    created_at: str
@dataclass
class Card:
    id: int
    user_id: int
    instance_id: Optional[int]
    name: str
    card_number: str
    cvv: str
    expiry_date: str
    card_holder: str
    bank_name: str
    color: str
    created_at: str
@dataclass
class Transaction:
    id: int
    user_id: int
    amount: float
    description: str
    category_id: Optional[int]
    source_id: Optional[int]
    to_source_id: Optional[int]
    tags: str
    transaction_type: str
    is_company: bool
    date: str
    created_at: str
@dataclass
class RecurringTransaction:
    id: int
    user_id: int
    instance_id: Optional[int]
    amount: float
    description: str
    category_id: Optional[int]
    source_id: Optional[int]
    tags: str
    is_income: bool
    is_company: bool
    frequency: str
    start_date: str
    end_date: Optional[str]
    last_generated: Optional[str]
    created_at: str
@dataclass
class LinkedUser:
    id: int
    owner_user_id: int
    linked_user_id: int
    link_type: str
    created_at: str
@dataclass
class Loan:
    id: int
    user_id: int
    instance_id: Optional[int]
    name: str
    description: str
    total_amount: float
    tenure_months: int
    monthly_due: float
    start_date: str
    created_at: str
@dataclass
class LoanPayment:
    id: int
    loan_id: int
    month_number: int
    due_date: str
    amount: float
    status: str
    description: str
    paid_date: Optional[str]
    created_at: str
def _get_instance_name(instance_id: int) -> Optional[str]:
    conn = sqlite3.connect(SHARED_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute("SELECT name FROM instances WHERE id = ?", (instance_id,))
        row = cursor.fetchone()
        return row["name"] if row else None
    finally:
        conn.close()
def _get_all_instance_ids() -> List[int]:
    conn = sqlite3.connect(SHARED_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute("SELECT id FROM instances")
        return [row["id"] for row in cursor.fetchall()]
    finally:
        conn.close()
def _get_user_instance_ids(user_id: int) -> List[int]:
    conn = sqlite3.connect(SHARED_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute("SELECT instance_id FROM instance_members WHERE user_id = ?", (user_id,))
        return [row["instance_id"] for row in cursor.fetchall()]
    finally:
        conn.close()
def _resolve_instance_id(user_id: int, instance_id: Optional[int]) -> int:
    if instance_id is not None:
        return instance_id
    ids = _get_user_instance_ids(user_id)
    if not ids:
        raise ValueError("User has no instances")
    return ids[0]
def _instance_db_path(instance_id: int) -> str:
    name = _get_instance_name(instance_id)
    return os.path.join(DB_FOLDER, f"{name}.db") if name else ""
def _instance_log_path(instance_id: int) -> str:
    name = _get_instance_name(instance_id)
    return os.path.join(DB_FOLDER, f"{name}.log") if name else ""
def audit_log(instance_id: int, action: str, table: str, user_id: int, record_id: int, details: str = ""):
    log_path = _instance_log_path(instance_id)
    if not log_path:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a") as f:
        f.write(f"{timestamp} | {action} | {table} | user:{user_id} | id:{record_id} | {details}\n")
def _find_instance_for_record(table: str, record_id: int, user_id: int) -> Optional[int]:
    for iid in _get_user_instance_ids(user_id):
        path = _instance_db_path(iid)
        if not os.path.exists(path):
            continue
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(f"SELECT 1 FROM {table} WHERE id = ? AND user_id = ?", (record_id, user_id))
            if cursor.fetchone():
                return iid
        finally:
            conn.close()
    return None
@contextmanager
def get_db(instance_id: Optional[int] = None):
    if instance_id:
        path = _instance_db_path(instance_id)
        if not path:
            raise ValueError(f"Instance {instance_id} not found")
    else:
        path = SHARED_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
def init_db():
    os.makedirs(DB_FOLDER, exist_ok=True)
    with get_db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, profile_name TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS instances (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, currency TEXT DEFAULT '$', created_by INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS instance_members (id INTEGER PRIMARY KEY AUTOINCREMENT, instance_id INTEGER NOT NULL, user_id INTEGER NOT NULL, role TEXT NOT NULL DEFAULT 'member', joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, UNIQUE(instance_id, user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS instance_invites (id INTEGER PRIMARY KEY AUTOINCREMENT, instance_id INTEGER NOT NULL, token TEXT NOT NULL UNIQUE, created_by INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP, used_by INTEGER, used_at TIMESTAMP, FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE, FOREIGN KEY (created_by) REFERENCES users(id), FOREIGN KEY (used_by) REFERENCES users(id))")
        conn.execute("CREATE TABLE IF NOT EXISTS linked_users (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_user_id INTEGER NOT NULL, linked_user_id INTEGER NOT NULL, link_type TEXT DEFAULT 'full', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (owner_user_id) REFERENCES users(id), FOREIGN KEY (linked_user_id) REFERENCES users(id), UNIQUE(owner_user_id, linked_user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS settings (user_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY (user_id, key), FOREIGN KEY (user_id) REFERENCES users(id))")
        conn.commit()
        cursor = conn.execute("SELECT COUNT(*) as count FROM users")
        if cursor.fetchone()["count"] == 0:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            hash = pwd_context.hash("admin")
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("admin", hash))
            conn.commit()
    run_migrations()
def run_migrations():
    with get_db() as conn:
        try:
            conn.execute("SELECT is_admin FROM users LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0")
            conn.execute("UPDATE users SET is_admin = 1 WHERE username = 'admin'")
        try:
            conn.execute("SELECT profile_picture FROM users LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE users ADD COLUMN profile_picture TEXT")
        try:
            conn.execute("SELECT profile_name FROM users LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE users ADD COLUMN profile_name TEXT")
        try:
            conn.execute("SELECT currency FROM instances LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE instances ADD COLUMN currency TEXT DEFAULT '$'")
        try:
            conn.execute("SELECT dashboard_instance_id FROM users LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE users ADD COLUMN dashboard_instance_id INTEGER")
        try:
            conn.execute("SELECT view_config FROM instances LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE instances ADD COLUMN view_config TEXT DEFAULT '{}'")
        try:
            conn.execute("SELECT is_default FROM instances LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE instances ADD COLUMN is_default BOOLEAN DEFAULT 0")
        conn.commit()
    for iid in _get_all_instance_ids():
        _init_instance_db(iid)
        _run_instance_migrations(iid)
def _init_instance_db(instance_id: int):
    path = _instance_db_path(instance_id)
    if not path:
        return
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, instance_id INTEGER, name TEXT NOT NULL, color TEXT DEFAULT '#6366f1', is_income BOOLEAN DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS sources (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, instance_id INTEGER, name TEXT NOT NULL, type TEXT DEFAULT 'custom', is_default BOOLEAN DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS cards (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, instance_id INTEGER, name TEXT NOT NULL, card_number TEXT NOT NULL, cvv TEXT NOT NULL, expiry_date TEXT NOT NULL, card_holder TEXT, bank_name TEXT, color TEXT DEFAULT '#6366f1', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, instance_id INTEGER, amount REAL NOT NULL, description TEXT NOT NULL, category_id INTEGER, source_id INTEGER, to_source_id INTEGER, tags TEXT DEFAULT '[]', transaction_type TEXT DEFAULT 'expense', is_company BOOLEAN DEFAULT 0, date DATE NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS recurring_transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, instance_id INTEGER, amount REAL NOT NULL, description TEXT NOT NULL, category_id INTEGER, source_id INTEGER, tags TEXT DEFAULT '[]', is_income BOOLEAN DEFAULT 0, is_company BOOLEAN DEFAULT 0, frequency TEXT NOT NULL, start_date DATE NOT NULL, end_date DATE, last_generated DATE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS loans (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, instance_id INTEGER, name TEXT NOT NULL, description TEXT, total_amount REAL NOT NULL, tenure_months INTEGER NOT NULL, monthly_due REAL NOT NULL, start_date DATE NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS loan_payments (id INTEGER PRIMARY KEY AUTOINCREMENT, loan_id INTEGER NOT NULL, month_number INTEGER NOT NULL, due_date DATE NOT NULL, amount REAL NOT NULL, status TEXT DEFAULT 'pending', description TEXT, paid_date DATE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(loan_id, month_number))")
        conn.commit()
    finally:
        conn.close()
def _run_instance_migrations(instance_id: int):
    path = _instance_db_path(instance_id)
    if not path or not os.path.exists(path):
        return
    conn = sqlite3.connect(path)
    try:
        for tbl in ['categories', 'sources', 'cards', 'recurring_transactions', 'loans', 'transactions']:
            try:
                conn.execute(f"SELECT instance_id FROM {tbl} LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN instance_id INTEGER")
        conn.commit()
    finally:
        conn.close()
def create_user(username: str, password_hash: str) -> int:
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
        conn.commit()
        return cursor.lastrowid
def get_user_by_username(username: str) -> Optional[User]:
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        return User(**dict(row)) if row else None
def get_user_by_id(user_id: int) -> Optional[User]:
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return User(**dict(row)) if row else None
def get_all_users() -> List[User]:
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM users ORDER BY username")
        return [User(**dict(row)) for row in cursor.fetchall()]
def get_categories(user_id: int, is_income: Optional[bool] = None, instance_id: Optional[int] = None) -> List[Category]:
    if instance_id is not None:
        with get_db(instance_id) as conn:
            query = "SELECT * FROM categories WHERE user_id = ?"
            params = [user_id]
            if is_income is not None:
                query += " AND is_income = ?"
                params.append(is_income)
            query += " ORDER BY is_income, name"
            cursor = conn.execute(query, params)
            return [Category(**dict(row)) for row in cursor.fetchall()]
    instance_ids = _get_user_instance_ids(user_id)
    all_cats = []
    for iid in instance_ids:
        with get_db(iid) as conn:
            query = "SELECT * FROM categories WHERE user_id = ?"
            params = [user_id]
            if is_income is not None:
                query += " AND is_income = ?"
                params.append(is_income)
            query += " ORDER BY is_income, name"
            cursor = conn.execute(query, params)
            for row in cursor.fetchall():
                all_cats.append(Category(**dict(row)))
    return all_cats
def create_category(user_id: int, name: str, color: str, is_income: bool, instance_id: Optional[int] = None) -> int:
    instance_id = _resolve_instance_id(user_id, instance_id)
    with get_db(instance_id) as conn:
        cursor = conn.execute("INSERT INTO categories (user_id, instance_id, name, color, is_income) VALUES (?, ?, ?, ?, ?)", (user_id, instance_id, name, color, is_income))
        conn.commit()
        audit_log(instance_id, "INSERT", "categories", user_id, cursor.lastrowid, name)
        return cursor.lastrowid
def delete_category(category_id: int, user_id: int) -> bool:
    iid = _find_instance_for_record("categories", category_id, user_id)
    if not iid:
        return False
    with get_db(iid) as conn:
        cursor = conn.execute("SELECT COUNT(*) as count FROM transactions WHERE category_id = ?", (category_id,))
        if cursor.fetchone()["count"] > 0:
            return False
        cursor = conn.execute("DELETE FROM categories WHERE id = ? AND user_id = ?", (category_id, user_id))
        conn.commit()
        if cursor.rowcount > 0:
            audit_log(iid, "DELETE", "categories", user_id, category_id)
        return cursor.rowcount > 0
def get_sources(user_id: int, instance_id: Optional[int] = None) -> List[Source]:
    if instance_id is not None:
        with get_db(instance_id) as conn:
            query = "SELECT * FROM sources WHERE user_id = ? ORDER BY is_default DESC, name"
            cursor = conn.execute(query, (user_id,))
            return [Source(**dict(row)) for row in cursor.fetchall()]
    instance_ids = _get_user_instance_ids(user_id)
    all_srcs = []
    for iid in instance_ids:
        with get_db(iid) as conn:
            cursor = conn.execute("SELECT * FROM sources WHERE user_id = ? ORDER BY is_default DESC, name", (user_id,))
            for row in cursor.fetchall():
                all_srcs.append(Source(**dict(row)))
    return all_srcs
def get_source(source_id: int, user_id: int) -> Optional[Source]:
    for iid in _get_user_instance_ids(user_id):
        with get_db(iid) as conn:
            cursor = conn.execute("SELECT * FROM sources WHERE id = ? AND user_id = ?", (source_id, user_id))
            row = cursor.fetchone()
            if row:
                return Source(**dict(row))
    return None
def create_source(user_id: int, name: str, source_type: str, instance_id: Optional[int] = None) -> int:
    instance_id = _resolve_instance_id(user_id, instance_id)
    with get_db(instance_id) as conn:
        cursor = conn.execute("INSERT INTO sources (user_id, instance_id, name, type, is_default) VALUES (?, ?, ?, ?, ?)", (user_id, instance_id, name, source_type, False))
        conn.commit()
        audit_log(instance_id, "INSERT", "sources", user_id, cursor.lastrowid, name)
        return cursor.lastrowid
def delete_source(source_id: int, user_id: int) -> bool:
    iid = _find_instance_for_record("sources", source_id, user_id)
    if not iid:
        return False
    with get_db(iid) as conn:
        cursor = conn.execute("SELECT COUNT(*) as count FROM transactions WHERE source_id = ? OR to_source_id = ?", (source_id, source_id))
        if cursor.fetchone()["count"] > 0:
            return False
        cursor = conn.execute("DELETE FROM sources WHERE id = ? AND user_id = ?", (source_id, user_id))
        conn.commit()
        if cursor.rowcount > 0:
            audit_log(iid, "DELETE", "sources", user_id, source_id)
        return cursor.rowcount > 0
def get_source_balance(user_id: int, source_id: int) -> float:
    for iid in _get_user_instance_ids(user_id):
        with get_db(iid) as conn:
            cursor = conn.execute("SELECT 1 FROM sources WHERE id = ? AND user_id = ?", (source_id, user_id))
            if cursor.fetchone():
                cursor = conn.execute("SELECT COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount WHEN transaction_type = 'expense' THEN -amount WHEN transaction_type = 'transfer' AND source_id = ? THEN -amount WHEN transaction_type = 'transfer' AND to_source_id = ? THEN amount ELSE 0 END), 0) as balance FROM transactions WHERE user_id = ? AND (source_id = ? OR to_source_id = ?)", (source_id, source_id, user_id, source_id, source_id))
                return cursor.fetchone()["balance"]
    return 0.0
def get_cards(user_id: int, instance_id: Optional[int] = None) -> List[Card]:
    if instance_id is not None:
        with get_db(instance_id) as conn:
            cursor = conn.execute("SELECT * FROM cards WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
            return [Card(**dict(row)) for row in cursor.fetchall()]
    instance_ids = _get_user_instance_ids(user_id)
    all_cards = []
    for iid in instance_ids:
        with get_db(iid) as conn:
            cursor = conn.execute("SELECT * FROM cards WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
            for row in cursor.fetchall():
                all_cards.append(Card(**dict(row)))
    return all_cards
def create_card(user_id: int, name: str, card_number: str, cvv: str, expiry_date: str, card_holder: str, bank_name: str, color: str, instance_id: Optional[int] = None) -> int:
    instance_id = _resolve_instance_id(user_id, instance_id)
    with get_db(instance_id) as conn:
        cursor = conn.execute("INSERT INTO cards (user_id, instance_id, name, card_number, cvv, expiry_date, card_holder, bank_name, color) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (user_id, instance_id, name, card_number, cvv, expiry_date, card_holder, bank_name, color))
        conn.commit()
        audit_log(instance_id, "INSERT", "cards", user_id, cursor.lastrowid, name)
        return cursor.lastrowid
def delete_card(card_id: int, user_id: int) -> bool:
    iid = _find_instance_for_record("cards", card_id, user_id)
    if not iid:
        return False
    with get_db(iid) as conn:
        cursor = conn.execute("DELETE FROM cards WHERE id = ? AND user_id = ?", (card_id, user_id))
        conn.commit()
        if cursor.rowcount > 0:
            audit_log(iid, "DELETE", "cards", user_id, card_id)
        return cursor.rowcount > 0
def create_transaction(user_id: int, amount: float, description: str, category_id: Optional[int], source_id: Optional[int], to_source_id: Optional[int], tags: List[str], transaction_type: str, is_company: bool, date: str, instance_id: int) -> int:
    instance_id = _resolve_instance_id(user_id, instance_id)
    with get_db(instance_id) as conn:
        cursor = conn.execute("INSERT INTO transactions (user_id, instance_id, amount, description, category_id, source_id, to_source_id, tags, transaction_type, is_company, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (user_id, instance_id, amount, description, category_id, source_id, to_source_id, json.dumps(tags), transaction_type, is_company, date))
        conn.commit()
        audit_log(instance_id, "INSERT", "transactions", user_id, cursor.lastrowid, f"{transaction_type} {amount}")
        return cursor.lastrowid
def get_transactions(user_id: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, is_company: Optional[bool] = None, category_id: Optional[int] = None, source_id: Optional[int] = None, transaction_type: Optional[str] = None, instance_id: Optional[int] = None) -> List[Dict]:
    if instance_id is not None:
        with get_db(instance_id) as conn:
            query = "SELECT t.*, c.name as category_name, c.color as category_color, s.name as source_name, s.type as source_type, ts.name as to_source_name FROM transactions t LEFT JOIN categories c ON t.category_id = c.id LEFT JOIN sources s ON t.source_id = s.id LEFT JOIN sources ts ON t.to_source_id = ts.id WHERE 1=1"
            params = []
            if user_id is not None:
                query += " AND t.user_id = ?"
                params.append(user_id)
            if start_date:
                query += " AND t.date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND t.date <= ?"
                params.append(end_date)
            if is_company is not None:
                query += " AND t.is_company = ?"
                params.append(is_company)
            if category_id:
                query += " AND t.category_id = ?"
                params.append(category_id)
            if source_id:
                query += " AND (t.source_id = ? OR t.to_source_id = ?)"
                params.extend([source_id, source_id])
            if transaction_type:
                query += " AND t.transaction_type = ?"
                params.append(transaction_type)
            query += " ORDER BY t.date DESC, t.created_at DESC"
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            transactions = []
            for row in rows:
                d = dict(row)
                d["tags"] = json.loads(d.get("tags", "[]"))
                d["instance_id"] = instance_id
                d["instance_name"] = _get_instance_name(instance_id)
                transactions.append(d)
            return transactions
    instance_ids = _get_user_instance_ids(user_id) if user_id else _get_all_instance_ids()
    all_transactions = []
    for iid in instance_ids:
        with get_db(iid) as conn:
            query = "SELECT t.*, c.name as category_name, c.color as category_color, s.name as source_name, s.type as source_type, ts.name as to_source_name FROM transactions t LEFT JOIN categories c ON t.category_id = c.id LEFT JOIN sources s ON t.source_id = s.id LEFT JOIN sources ts ON t.to_source_id = ts.id WHERE 1=1"
            params = []
            if user_id is not None:
                query += " AND t.user_id = ?"
                params.append(user_id)
            if start_date:
                query += " AND t.date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND t.date <= ?"
                params.append(end_date)
            if is_company is not None:
                query += " AND t.is_company = ?"
                params.append(is_company)
            if category_id:
                query += " AND t.category_id = ?"
                params.append(category_id)
            if source_id:
                query += " AND (t.source_id = ? OR t.to_source_id = ?)"
                params.extend([source_id, source_id])
            if transaction_type:
                query += " AND t.transaction_type = ?"
                params.append(transaction_type)
            query += " ORDER BY t.date DESC, t.created_at DESC"
            cursor = conn.execute(query, params)
            for row in cursor.fetchall():
                d = dict(row)
                d["tags"] = json.loads(d.get("tags", "[]"))
                d["instance_id"] = iid
                d["instance_name"] = _get_instance_name(iid)
                all_transactions.append(d)
    all_transactions.sort(key=lambda x: (x.get("date", ""), x.get("created_at", "")), reverse=True)
    return all_transactions
def get_transaction(transaction_id: int, user_id: int) -> Optional[Dict]:
    for iid in _get_user_instance_ids(user_id):
        with get_db(iid) as conn:
            cursor = conn.execute("SELECT t.*, c.name as category_name, c.color as category_color, s.name as source_name, s.type as source_type, ts.name as to_source_name FROM transactions t LEFT JOIN categories c ON t.category_id = c.id LEFT JOIN sources s ON t.source_id = s.id LEFT JOIN sources ts ON t.to_source_id = ts.id WHERE t.id = ? AND t.user_id = ?", (transaction_id, user_id))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d["tags"] = json.loads(d.get("tags", "[]"))
                d["instance_id"] = iid
                d["instance_name"] = _get_instance_name(iid)
                return d
    return None
def update_transaction(transaction_id: int, user_id: int, **kwargs) -> bool:
    iid = _find_instance_for_record("transactions", transaction_id, user_id)
    if not iid:
        return False
    allowed = ["amount", "description", "category_id", "source_id", "to_source_id", "tags", "transaction_type", "is_company", "date", "instance_id"]
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    if "tags" in updates:
        updates["tags"] = json.dumps(updates["tags"])
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [transaction_id, user_id]
    with get_db(iid) as conn:
        cursor = conn.execute(f"UPDATE transactions SET {set_clause} WHERE id = ? AND user_id = ?", values)
        conn.commit()
        if cursor.rowcount > 0:
            audit_log(iid, "UPDATE", "transactions", user_id, transaction_id)
        return cursor.rowcount > 0
def delete_transaction(transaction_id: int, user_id: int) -> bool:
    iid = _find_instance_for_record("transactions", transaction_id, user_id)
    if not iid:
        return False
    with get_db(iid) as conn:
        cursor = conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (transaction_id, user_id))
        conn.commit()
        if cursor.rowcount > 0:
            audit_log(iid, "DELETE", "transactions", user_id, transaction_id)
        return cursor.rowcount > 0
def get_monthly_summary(user_id: Optional[int] = None, year: Optional[int] = None, month: Optional[int] = None, instance_id: Optional[int] = None):
    if instance_id is not None:
        with get_db(instance_id) as conn:
            if year and month:
                date_filter = f"{year:04d}-{month:02d}"
                date_condition = "strftime('%Y-%m', date) = ?"
                params = [date_filter]
            elif year:
                date_condition = "strftime('%Y', date) = ?"
                params = [str(year)]
            else:
                date_condition = "1=1"
                params = []
            user_condition = "t.user_id = ?" if user_id else "1=1"
            if user_id:
                params.append(user_id)
            cursor = conn.execute(f"SELECT COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) as total_income, COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END), 0) as total_expense, COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE -amount END), 0) as net, COALESCE(SUM(CASE WHEN is_company = 1 AND transaction_type = 'expense' THEN amount ELSE 0 END), 0) as company_expense, COALESCE(SUM(CASE WHEN is_company = 1 AND transaction_type = 'income' THEN amount ELSE 0 END), 0) as company_income FROM transactions t WHERE {date_condition} AND {user_condition}", params)
            summary = dict(cursor.fetchone())
            cursor = conn.execute(f"SELECT c.name, c.color, t.transaction_type, SUM(t.amount) as total, COUNT(*) as count FROM transactions t LEFT JOIN categories c ON t.category_id = c.id WHERE {date_condition} AND {user_condition} GROUP BY c.name, c.color, t.transaction_type ORDER BY total DESC", params)
            categories = [dict(row) for row in cursor.fetchall()]
            cursor = conn.execute(f"SELECT date, COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) as income, COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END), 0) as expense FROM transactions t WHERE {date_condition} AND {user_condition} GROUP BY date ORDER BY date", params)
            daily = [dict(row) for row in cursor.fetchall()]
            return {"summary": summary, "categories": categories, "daily": daily}
    instance_ids = _get_user_instance_ids(user_id) if user_id else _get_all_instance_ids()
    total_summary = {"total_income": 0.0, "total_expense": 0.0, "net": 0.0, "company_expense": 0.0, "company_income": 0.0}
    all_categories = []
    all_daily = []
    for iid in instance_ids:
        result = get_monthly_summary(user_id=user_id, year=year, month=month, instance_id=iid)
        s = result["summary"]
        total_summary["total_income"] += s["total_income"]
        total_summary["total_expense"] += s["total_expense"]
        total_summary["net"] += s["net"]
        total_summary["company_expense"] += s["company_expense"]
        total_summary["company_income"] += s["company_income"]
        all_categories.extend(result["categories"])
        all_daily.extend(result["daily"])
    cat_agg = {}
    for c in all_categories:
        key = (c.get("name"), c.get("color"), c.get("transaction_type"))
        if key not in cat_agg:
            cat_agg[key] = {"name": c.get("name"), "color": c.get("color"), "transaction_type": c.get("transaction_type"), "total": 0.0, "count": 0}
        cat_agg[key]["total"] += c.get("total", 0)
        cat_agg[key]["count"] += c.get("count", 0)
    categories = sorted(cat_agg.values(), key=lambda x: x["total"], reverse=True)
    daily_agg = {}
    for d in all_daily:
        date_key = d.get("date")
        if date_key not in daily_agg:
            daily_agg[date_key] = {"date": date_key, "income": 0.0, "expense": 0.0}
        daily_agg[date_key]["income"] += d.get("income", 0)
        daily_agg[date_key]["expense"] += d.get("expense", 0)
    daily = sorted(daily_agg.values(), key=lambda x: x.get("date", ""))
    return {"summary": total_summary, "categories": categories, "daily": daily}
def get_yearly_summary(user_id: Optional[int] = None, year: Optional[int] = None, instance_id: Optional[int] = None):
    if instance_id is not None:
        with get_db(instance_id) as conn:
            year_condition = "strftime('%Y', date) = ?" if year else "1=1"
            params = [str(year)] if year else []
            user_condition = "t.user_id = ?" if user_id else "1=1"
            if user_id:
                params.append(user_id)
            cursor = conn.execute(f"SELECT strftime('%m', date) as month, COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) as income, COALESCE(SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END), 0) as expense, COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE -amount END), 0) as net FROM transactions t WHERE {year_condition} AND {user_condition} GROUP BY strftime('%m', date) ORDER BY month", params)
            return [dict(row) for row in cursor.fetchall()]
    instance_ids = _get_user_instance_ids(user_id) if user_id else _get_all_instance_ids()
    monthly_agg = {}
    for iid in instance_ids:
        result = get_yearly_summary(user_id=user_id, year=year, instance_id=iid)
        for r in result:
            month = r.get("month")
            if month not in monthly_agg:
                monthly_agg[month] = {"month": month, "income": 0.0, "expense": 0.0, "net": 0.0}
            monthly_agg[month]["income"] += r.get("income", 0)
            monthly_agg[month]["expense"] += r.get("expense", 0)
            monthly_agg[month]["net"] += r.get("net", 0)
    return sorted(monthly_agg.values(), key=lambda x: x.get("month", ""))
def create_recurring_transaction(user_id: int, amount: float, description: str, category_id: Optional[int], source_id: Optional[int], tags: List[str], is_income: bool, is_company: bool, frequency: str, start_date: str, end_date: Optional[str], instance_id: Optional[int] = None) -> int:
    instance_id = _resolve_instance_id(user_id, instance_id)
    with get_db(instance_id) as conn:
        cursor = conn.execute("INSERT INTO recurring_transactions (user_id, instance_id, amount, description, category_id, source_id, tags, is_income, is_company, frequency, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (user_id, instance_id, amount, description, category_id, source_id, json.dumps(tags), is_income, is_company, frequency, start_date, end_date))
        conn.commit()
        audit_log(instance_id, "INSERT", "recurring_transactions", user_id, cursor.lastrowid, description)
        return cursor.lastrowid
def get_recurring_transactions(user_id: int, instance_id: Optional[int] = None) -> List[Dict]:
    if instance_id is not None:
        with get_db(instance_id) as conn:
            query = "SELECT r.*, c.name as category_name, c.color as category_color, s.name as source_name FROM recurring_transactions r LEFT JOIN categories c ON r.category_id = c.id LEFT JOIN sources s ON r.source_id = s.id WHERE r.user_id = ? ORDER BY r.created_at DESC"
            cursor = conn.execute(query, (user_id,))
            rows = cursor.fetchall()
            recurring = []
            for row in rows:
                d = dict(row)
                d["tags"] = json.loads(d.get("tags", "[]"))
                recurring.append(d)
            return recurring
    instance_ids = _get_user_instance_ids(user_id)
    all_recurring = []
    for iid in instance_ids:
        with get_db(iid) as conn:
            cursor = conn.execute("SELECT r.*, c.name as category_name, c.color as category_color, s.name as source_name FROM recurring_transactions r LEFT JOIN categories c ON r.category_id = c.id LEFT JOIN sources s ON r.source_id = s.id WHERE r.user_id = ? ORDER BY r.created_at DESC", (user_id,))
            for row in cursor.fetchall():
                d = dict(row)
                d["tags"] = json.loads(d.get("tags", "[]"))
                all_recurring.append(d)
    all_recurring.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return all_recurring
def delete_recurring_transaction(recurring_id: int, user_id: int) -> bool:
    iid = _find_instance_for_record("recurring_transactions", recurring_id, user_id)
    if not iid:
        return False
    with get_db(iid) as conn:
        cursor = conn.execute("DELETE FROM recurring_transactions WHERE id = ? AND user_id = ?", (recurring_id, user_id))
        conn.commit()
        if cursor.rowcount > 0:
            audit_log(iid, "DELETE", "recurring_transactions", user_id, recurring_id)
        return cursor.rowcount > 0
def generate_recurring_transactions():
    for iid in _get_all_instance_ids():
        path = _instance_db_path(iid)
        if not os.path.exists(path):
            continue
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("SELECT * FROM recurring_transactions WHERE (end_date IS NULL OR end_date >= date('now'))")
            recurring = [dict(row) for row in cursor.fetchall()]
            today = date.today()
            for r in recurring:
                last_gen = r.get("last_generated")
                start = datetime.strptime(r["start_date"], "%Y-%m-%d").date()
                current = datetime.strptime(last_gen, "%Y-%m-%d").date() + timedelta(days=1) if last_gen else start
                generated = []
                while current <= today:
                    should_generate = False
                    if r["frequency"] == "daily":
                        should_generate = True
                    elif r["frequency"] == "weekly":
                        should_generate = current.weekday() == start.weekday()
                    elif r["frequency"] == "monthly":
                        should_generate = current.day == start.day
                    elif r["frequency"] == "yearly":
                        should_generate = current.month == start.month and current.day == start.day
                    if should_generate:
                        if r.get("end_date") and current > datetime.strptime(r["end_date"], "%Y-%m-%d").date():
                            break
                        generated.append(current)
                    current += timedelta(days=1)
                if generated:
                    last_date = generated[-1]
                    for gen_date in generated:
                        ttype = "income" if r["is_income"] else "expense"
                        conn.execute("INSERT INTO transactions (user_id, instance_id, amount, description, category_id, source_id, tags, transaction_type, is_company, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (r["user_id"], r.get("instance_id"), r["amount"], r["description"], r["category_id"], r.get("source_id"), r["tags"], ttype, r["is_company"], gen_date.strftime("%Y-%m-%d")))
                    conn.execute("UPDATE recurring_transactions SET last_generated = ? WHERE id = ?", (last_date.strftime("%Y-%m-%d"), r["id"]))
            conn.commit()
        finally:
            conn.close()
def link_users(owner_user_id: int, linked_user_id: int, link_type: str = "full") -> bool:
    with get_db() as conn:
        try:
            conn.execute("INSERT INTO linked_users (owner_user_id, linked_user_id, link_type) VALUES (?, ?, ?)", (owner_user_id, linked_user_id, link_type))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
def unlink_users(owner_user_id: int, linked_user_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM linked_users WHERE owner_user_id = ? AND linked_user_id = ?", (owner_user_id, linked_user_id))
        conn.commit()
        return cursor.rowcount > 0
def get_linked_users(user_id: int) -> List[Dict]:
    with get_db() as conn:
        cursor = conn.execute("SELECT l.*, u.username FROM linked_users l JOIN users u ON l.linked_user_id = u.id WHERE l.owner_user_id = ?", (user_id,))
        return [dict(row) for row in cursor.fetchall()]
def get_linked_to_users(user_id: int) -> List[Dict]:
    with get_db() as conn:
        cursor = conn.execute("SELECT l.*, u.username FROM linked_users l JOIN users u ON l.owner_user_id = u.id WHERE l.linked_user_id = ?", (user_id,))
        return [dict(row) for row in cursor.fetchall()]
def get_visible_user_ids(user_id: int) -> List[int]:
    ids = [user_id]
    linked_to = get_linked_to_users(user_id)
    for link in linked_to:
        if link["link_type"] in ("full", "shared_income", "shared_expense"):
            ids.append(link["owner_user_id"])
    return list(set(ids))
def create_loan(user_id: int, name: str, description: str, total_amount: float, tenure_months: int, monthly_due: float, start_date: str, instance_id: Optional[int] = None) -> int:
    instance_id = _resolve_instance_id(user_id, instance_id)
    with get_db(instance_id) as conn:
        cursor = conn.execute("INSERT INTO loans (user_id, instance_id, name, description, total_amount, tenure_months, monthly_due, start_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (user_id, instance_id, name, description, total_amount, tenure_months, monthly_due, start_date))
        loan_id = cursor.lastrowid
        audit_log(instance_id, "INSERT", "loans", user_id, loan_id, name)
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        for i in range(1, tenure_months + 1):
            due_date = add_months(start, i - 1)
            cursor2 = conn.execute("INSERT INTO loan_payments (loan_id, month_number, due_date, amount, status) VALUES (?, ?, ?, ?, 'pending')", (loan_id, i, due_date.strftime("%Y-%m-%d"), monthly_due))
            audit_log(instance_id, "INSERT", "loan_payments", user_id, cursor2.lastrowid, f"loan:{loan_id} month:{i}")
        conn.commit()
        return loan_id
def add_months(date_obj, months):
    month = date_obj.month - 1 + months
    year = date_obj.year + month // 12
    month = month % 12 + 1
    day = min(date_obj.day, [31, 29 if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)
def get_loans(user_id: int, instance_id: Optional[int] = None) -> List[Dict]:
    if instance_id is not None:
        with get_db(instance_id) as conn:
            query = "SELECT l.*, (SELECT COUNT(*) FROM loan_payments WHERE loan_id = l.id AND status = 'paid') as paid_count, (SELECT COUNT(*) FROM loan_payments WHERE loan_id = l.id AND status = 'reserved') as reserved_count, (SELECT COUNT(*) FROM loan_payments WHERE loan_id = l.id AND status = 'pending') as pending_count FROM loans l WHERE l.user_id = ? ORDER BY l.created_at DESC"
            cursor = conn.execute(query, (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    instance_ids = _get_user_instance_ids(user_id)
    all_loans = []
    for iid in instance_ids:
        with get_db(iid) as conn:
            cursor = conn.execute("SELECT l.*, (SELECT COUNT(*) FROM loan_payments WHERE loan_id = l.id AND status = 'paid') as paid_count, (SELECT COUNT(*) FROM loan_payments WHERE loan_id = l.id AND status = 'reserved') as reserved_count, (SELECT COUNT(*) FROM loan_payments WHERE loan_id = l.id AND status = 'pending') as pending_count FROM loans l WHERE l.user_id = ? ORDER BY l.created_at DESC", (user_id,))
            for row in cursor.fetchall():
                all_loans.append(dict(row))
    return all_loans
def get_loan(loan_id: int, user_id: int) -> Optional[Dict]:
    for iid in _get_user_instance_ids(user_id):
        with get_db(iid) as conn:
            cursor = conn.execute("SELECT * FROM loans WHERE id = ? AND user_id = ?", (loan_id, user_id))
            row = cursor.fetchone()
            if row:
                return dict(row)
    return None
def delete_loan(loan_id: int, user_id: int) -> bool:
    iid = _find_instance_for_record("loans", loan_id, user_id)
    if not iid:
        return False
    with get_db(iid) as conn:
        conn.execute("DELETE FROM loan_payments WHERE loan_id = ?", (loan_id,))
        cursor = conn.execute("DELETE FROM loans WHERE id = ? AND user_id = ?", (loan_id, user_id))
        conn.commit()
        if cursor.rowcount > 0:
            audit_log(iid, "DELETE", "loans", user_id, loan_id)
        return cursor.rowcount > 0
def get_loan_payments(loan_id: int) -> List[Dict]:
    for iid in _get_all_instance_ids():
        with get_db(iid) as conn:
            cursor = conn.execute("SELECT * FROM loan_payments WHERE loan_id = ? ORDER BY month_number", (loan_id,))
            rows = cursor.fetchall()
            if rows:
                return [dict(row) for row in rows]
    return []
def update_loan_payment(payment_id: int, status: str, description: str = "", user_id: int = 0) -> bool:
    for iid in _get_all_instance_ids():
        with get_db(iid) as conn:
            cursor = conn.execute("SELECT 1 FROM loan_payments WHERE id = ?", (payment_id,))
            if cursor.fetchone():
                paid_date = datetime.now().strftime("%Y-%m-%d") if status in ("paid", "reserved") else None
                cursor = conn.execute("UPDATE loan_payments SET status = ?, description = ?, paid_date = ? WHERE id = ?", (status, description, paid_date, payment_id))
                conn.commit()
                if cursor.rowcount > 0:
                    audit_log(iid, "UPDATE", "loan_payments", user_id, payment_id, f"status:{status}")
                return cursor.rowcount > 0
    return False
def get_loan_summary(user_id: int, instance_id: Optional[int] = None) -> Dict:
    if instance_id is not None:
        with get_db(instance_id) as conn:
            cursor = conn.execute("SELECT COUNT(*) as total_loans, COALESCE(SUM(total_amount), 0) as total_borrowed, (SELECT COUNT(*) FROM loan_payments lp JOIN loans l ON lp.loan_id = l.id WHERE l.user_id = ? AND lp.status = 'pending' AND strftime('%Y-%m', lp.due_date) = strftime('%Y-%m', 'now')) as due_this_month FROM loans WHERE user_id = ?", (user_id, user_id))
            return dict(cursor.fetchone())
    instance_ids = _get_user_instance_ids(user_id)
    total = {"total_loans": 0, "total_borrowed": 0.0, "due_this_month": 0}
    for iid in instance_ids:
        result = get_loan_summary(user_id, instance_id=iid)
        total["total_loans"] += result["total_loans"]
        total["total_borrowed"] += result["total_borrowed"]
        total["due_this_month"] += result["due_this_month"]
    return total
def get_setting(user_id: int, key: str, default=None):
    with get_db() as conn:
        cursor = conn.execute("SELECT value FROM settings WHERE user_id = ? AND key = ?", (user_id, key))
        row = cursor.fetchone()
        return row["value"] if row else default
def set_setting(user_id: int, key: str, value: str):
    with get_db() as conn:
        conn.execute("INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?) ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value", (user_id, key, value))
        conn.commit()
def get_all_settings(user_id: int) -> Dict[str, str]:
    with get_db() as conn:
        cursor = conn.execute("SELECT key, value FROM settings WHERE user_id = ?", (user_id,))
        return {row["key"]: row["value"] for row in cursor.fetchall()}
def update_user_profile(user_id: int, username: Optional[str] = None, profile_picture: Optional[str] = None, profile_name: Optional[str] = None) -> bool:
    updates = []
    params = []
    if username is not None:
        updates.append("username = ?")
        params.append(username)
    if profile_picture is not None:
        updates.append("profile_picture = ?")
        params.append(profile_picture)
    if profile_name is not None:
        updates.append("profile_name = ?")
        params.append(profile_name)
    if not updates:
        return False
    params.append(user_id)
    with get_db() as conn:
        try:
            cursor = conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            return False
def update_user_password(user_id: int, new_password_hash: str) -> bool:
    with get_db() as conn:
        cursor = conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_password_hash, user_id))
        conn.commit()
        return cursor.rowcount > 0
def create_instance(user_id: int, name: str, currency: str = "$") -> int:
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO instances (name, currency, created_by) VALUES (?, ?, ?)", (name, currency, user_id))
        instance_id = cursor.lastrowid
        conn.execute("INSERT INTO instance_members (instance_id, user_id, role) VALUES (?, ?, ?)", (instance_id, user_id, "owner"))
        conn.commit()
    _init_instance_db(instance_id)
    return instance_id
def get_user_instances(user_id: int) -> List[Dict]:
    with get_db() as conn:
        cursor = conn.execute("SELECT i.*, m.role, (SELECT COUNT(*) FROM instance_members WHERE instance_id = i.id) as member_count FROM instances i JOIN instance_members m ON i.id = m.instance_id WHERE m.user_id = ? ORDER BY i.created_at DESC", (user_id,))
        return [dict(row) for row in cursor.fetchall()]
def get_instance(instance_id: int, user_id: int) -> Optional[Dict]:
    with get_db() as conn:
        cursor = conn.execute("SELECT i.*, m.role, (SELECT COUNT(*) FROM instance_members WHERE instance_id = i.id) as member_count FROM instances i JOIN instance_members m ON i.id = m.instance_id WHERE i.id = ? AND m.user_id = ?", (instance_id, user_id))
        row = cursor.fetchone()
        return dict(row) if row else None
def get_instance_members(instance_id: int) -> List[Dict]:
    with get_db() as conn:
        cursor = conn.execute("SELECT m.*, u.username FROM instance_members m JOIN users u ON m.user_id = u.id WHERE m.instance_id = ? ORDER BY m.joined_at", (instance_id,))
        return [dict(row) for row in cursor.fetchall()]
def get_instance_transactions(instance_id: int) -> List[Dict]:
    with get_db(instance_id) as conn:
        cursor = conn.execute("SELECT t.*, c.name as category_name, c.color as category_color, s.name as source_name, s.type as source_type, ts.name as to_source_name FROM transactions t LEFT JOIN categories c ON t.category_id = c.id LEFT JOIN sources s ON t.source_id = s.id LEFT JOIN sources ts ON t.to_source_id = ts.id WHERE t.instance_id = ? ORDER BY t.date DESC, t.created_at DESC", (instance_id,))
        rows = cursor.fetchall()
        transactions = []
        for row in rows:
            d = dict(row)
            d["tags"] = json.loads(d.get("tags", "[]"))
            transactions.append(d)
        return transactions
def create_instance_transaction(user_id: int, instance_id: int, amount: float, description: str, category_id: Optional[int], source_id: Optional[int], to_source_id: Optional[int], tags: List[str], transaction_type: str, is_company: bool, date: str) -> int:
    return create_transaction(user_id, amount, description, category_id, source_id, to_source_id, tags, transaction_type, is_company, date, instance_id)
def generate_instance_invite(instance_id: int, user_id: int) -> str:
    import secrets
    token = secrets.token_urlsafe(16)
    with get_db() as conn:
        conn.execute("INSERT INTO instance_invites (instance_id, token, created_by, expires_at) VALUES (?, ?, ?, datetime('now', '+7 days'))", (instance_id, token, user_id))
        conn.commit()
        return token
def join_instance_by_token(token: str, user_id: int) -> Optional[Dict]:
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM instance_invites WHERE token = ? AND (expires_at IS NULL OR expires_at > datetime('now')) AND used_by IS NULL", (token,))
        invite = cursor.fetchone()
        if not invite:
            return None
        instance_id = invite["instance_id"]
        try:
            conn.execute("INSERT INTO instance_members (instance_id, user_id, role) VALUES (?, ?, ?)", (instance_id, user_id, "member"))
            conn.execute("UPDATE instance_invites SET used_by = ?, used_at = datetime('now') WHERE id = ?", (user_id, invite["id"]))
            conn.commit()
            return {"instance_id": instance_id, "name": conn.execute("SELECT name FROM instances WHERE id = ?", (instance_id,)).fetchone()["name"]}
        except sqlite3.IntegrityError:
            return None
def leave_instance(instance_id: int, user_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM instance_members WHERE instance_id = ? AND user_id = ? AND role != 'owner'", (instance_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
def delete_instance(instance_id: int, user_id: int) -> bool:
    name = _get_instance_name(instance_id)
    with get_db() as conn:
        cursor = conn.execute("SELECT role FROM instance_members WHERE instance_id = ? AND user_id = ?", (instance_id, user_id))
        row = cursor.fetchone()
        if not row or row["role"] != "owner":
            return False
        conn.execute("DELETE FROM instance_invites WHERE instance_id = ?", (instance_id,))
        conn.execute("DELETE FROM instance_members WHERE instance_id = ?", (instance_id,))
        conn.execute("DELETE FROM instances WHERE id = ?", (instance_id,))
        conn.commit()
    if name:
        db_path = os.path.join(DB_FOLDER, f"{name}.db")
        log_path = os.path.join(DB_FOLDER, f"{name}.log")
        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists(log_path):
            os.remove(log_path)
    return True
def admin_remove_instance_member(instance_id: int, member_user_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM instance_members WHERE instance_id = ? AND user_id = ? AND role != 'owner'", (instance_id, member_user_id))
        conn.commit()
        return cursor.rowcount > 0
def get_instance_invites(instance_id: int) -> List[Dict]:
    with get_db() as conn:
        cursor = conn.execute("SELECT i.*, u.username as used_by_name FROM instance_invites i LEFT JOIN users u ON i.used_by = u.id WHERE i.instance_id = ? ORDER BY i.created_at DESC", (instance_id,))
        return [dict(row) for row in cursor.fetchall()]
def is_instance_member(instance_id: int, user_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute("SELECT 1 FROM instance_members WHERE instance_id = ? AND user_id = ?", (instance_id, user_id))
        return cursor.fetchone() is not None
def get_all_instances() -> List[Dict]:
    with get_db() as conn:
        cursor = conn.execute("SELECT i.*, u.username as owner_name, (SELECT COUNT(*) FROM instance_members WHERE instance_id = i.id) as member_count FROM instances i JOIN users u ON i.created_by = u.id ORDER BY i.created_at DESC")
        return [dict(row) for row in cursor.fetchall()]
def admin_create_user(username: str, password_hash: str) -> int:
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
        conn.commit()
        return cursor.lastrowid
def admin_delete_user(user_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row or row["username"] == "admin":
            return False
        cursor = conn.execute("SELECT id, name FROM instances")
        instances = [dict(row) for row in cursor.fetchall()]
        conn.execute("DELETE FROM settings WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM instance_members WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM instance_invites WHERE created_by = ? OR used_by = ?", (user_id, user_id))
        conn.execute("DELETE FROM linked_users WHERE owner_user_id = ? OR linked_user_id = ?", (user_id, user_id))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    for inst in instances:
        db_path = os.path.join(DB_FOLDER, f"{inst['name']}.db")
        if os.path.exists(db_path):
            iconn = sqlite3.connect(db_path)
            try:
                iconn.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
                iconn.execute("DELETE FROM categories WHERE user_id = ?", (user_id,))
                iconn.execute("DELETE FROM sources WHERE user_id = ?", (user_id,))
                iconn.execute("DELETE FROM cards WHERE user_id = ?", (user_id,))
                iconn.execute("DELETE FROM recurring_transactions WHERE user_id = ?", (user_id,))
                iconn.execute("DELETE FROM loans WHERE user_id = ?", (user_id,))
                iconn.commit()
            finally:
                iconn.close()
    return True
def admin_reset_password(user_id: int, new_password_hash: str) -> bool:
    with get_db() as conn:
        cursor = conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_password_hash, user_id))
        conn.commit()
        return cursor.rowcount > 0
def update_user_dashboard_instance(user_id: int, instance_id: Optional[int]) -> bool:
    with get_db() as conn:
        cursor = conn.execute("UPDATE users SET dashboard_instance_id = ? WHERE id = ?", (instance_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
def get_user_dashboard_instance(user_id: int) -> Optional[int]:
    with get_db() as conn:
        cursor = conn.execute("SELECT dashboard_instance_id FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return row["dashboard_instance_id"] if row and row["dashboard_instance_id"] else None
def get_instance_view_config(instance_id: int) -> Dict:
    with get_db() as conn:
        cursor = conn.execute("SELECT view_config FROM instances WHERE id = ?", (instance_id,))
        row = cursor.fetchone()
        if row and row["view_config"]:
            try:
                return json.loads(row["view_config"])
            except:
                return {}
        return {}
def update_instance_view_config(instance_id: int, config: Dict) -> bool:
    with get_db() as conn:
        cursor = conn.execute("UPDATE instances SET view_config = ? WHERE id = ?", (json.dumps(config), instance_id))
        conn.commit()
        return cursor.rowcount > 0
def create_instance_wizard(user_id: int, name: str, currency: str, member_ids: List[int], source_names: List[str], category_defs: List[Dict], loan_defs: List[Dict]) -> int:
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO instances (name, currency, created_by) VALUES (?, ?, ?)", (name, currency, user_id))
        instance_id = cursor.lastrowid
        conn.execute("INSERT INTO instance_members (instance_id, user_id, role) VALUES (?, ?, ?)", (instance_id, user_id, "owner"))
        for mid in member_ids:
            if mid != user_id:
                try:
                    conn.execute("INSERT INTO instance_members (instance_id, user_id, role) VALUES (?, ?, ?)", (instance_id, mid, "member"))
                except sqlite3.IntegrityError:
                    pass
        conn.commit()
    _init_instance_db(instance_id)
    with get_db(instance_id) as conn:
        for sname in source_names:
            if sname.strip():
                cursor = conn.execute("INSERT INTO sources (user_id, instance_id, name, type, is_default) VALUES (?, ?, ?, ?, ?)", (user_id, instance_id, sname.strip(), "custom", False))
                audit_log(instance_id, "INSERT", "sources", user_id, cursor.lastrowid, sname.strip())
        for cat in category_defs:
            cursor = conn.execute("INSERT INTO categories (user_id, instance_id, name, color, is_income) VALUES (?, ?, ?, ?, ?)", (user_id, instance_id, cat["name"], cat.get("color", "#6366f1"), cat.get("is_income", False)))
            audit_log(instance_id, "INSERT", "categories", user_id, cursor.lastrowid, cat["name"])
        for loan in loan_defs:
            cursor2 = conn.execute("INSERT INTO loans (user_id, instance_id, name, description, total_amount, tenure_months, monthly_due, start_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (user_id, instance_id, loan["name"], loan.get("description", ""), loan["total_amount"], loan["tenure_months"], loan["monthly_due"], loan["start_date"]))
            loan_id = cursor2.lastrowid
            audit_log(instance_id, "INSERT", "loans", user_id, loan_id, loan["name"])
            start = datetime.strptime(loan["start_date"], "%Y-%m-%d").date()
            for i in range(1, loan["tenure_months"] + 1):
                due_date = add_months(start, i - 1)
                cursor3 = conn.execute("INSERT INTO loan_payments (loan_id, month_number, due_date, amount, status) VALUES (?, ?, ?, ?, 'pending')", (loan_id, i, due_date.strftime("%Y-%m-%d"), loan["monthly_due"]))
                audit_log(instance_id, "INSERT", "loan_payments", user_id, cursor3.lastrowid, f"loan:{loan_id} month:{i}")
        conn.commit()
    return instance_id
def update_instance_name(instance_id: int, name: str) -> bool:
    with get_db() as conn:
        cursor = conn.execute("UPDATE instances SET name = ? WHERE id = ?", (name, instance_id))
        conn.commit()
        return cursor.rowcount > 0
def get_instance_by_id(instance_id: int) -> Optional[Dict]:
    with get_db() as conn:
        cursor = conn.execute("SELECT i.*, u.username as owner_name, (SELECT COUNT(*) FROM instance_members WHERE instance_id = i.id) as member_count FROM instances i JOIN users u ON i.created_by = u.id WHERE i.id = ?", (instance_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
def update_instance_currency(instance_id: int, user_id: int, currency: str, conversion_rate: float = 1.0) -> bool:
    with get_db() as conn:
        cursor = conn.execute("SELECT role FROM instance_members WHERE instance_id = ? AND user_id = ?", (instance_id, user_id))
        row = cursor.fetchone()
        if not row or row["role"] != "owner":
            return False
        conn.execute("UPDATE instances SET currency = ? WHERE id = ?", (currency, instance_id))
        if conversion_rate != 1.0:
            with get_db(instance_id) as iconn:
                iconn.execute("UPDATE transactions SET amount = amount * ? WHERE instance_id = ?", (conversion_rate, instance_id))
                iconn.execute("UPDATE loans SET total_amount = total_amount * ?, monthly_due = monthly_due * ? WHERE instance_id = ?", (conversion_rate, conversion_rate, instance_id))
                iconn.execute("UPDATE recurring_transactions SET amount = amount * ? WHERE instance_id = ?", (conversion_rate, instance_id))
                iconn.commit()
        conn.commit()
        return True