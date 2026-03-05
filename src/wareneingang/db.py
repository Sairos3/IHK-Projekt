import sqlite3
from pathlib import Path
from typing import Iterable, Dict, Any

DB_PATH = Path("data/wareneingang.db")


def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with connect() as con:
        con.executescript("""
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS files (
            file_id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE,
            doc_type TEXT NOT NULL,
            match_key TEXT,
            created_at TEXT NOT NULL
        );

        -- store customer_no on the lines (simple + minimal changes)
        CREATE TABLE IF NOT EXISTS invoice_lines (
            line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            customer_no TEXT,
            description TEXT NOT NULL,
            qty REAL NOT NULL,
            FOREIGN KEY (file_id) REFERENCES files(file_id)
        );

        CREATE TABLE IF NOT EXISTS delivery_lines (
            line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            customer_no TEXT,
            item_number TEXT,
            description TEXT NOT NULL,
            qty REAL NOT NULL,
            FOREIGN KEY (file_id) REFERENCES files(file_id)
        );
        """)


def file_exists(sha256: str) -> bool:
    with connect() as con:
        row = con.execute("SELECT 1 FROM files WHERE sha256 = ?", (sha256,)).fetchone()
        return row is not None


def insert_file(path: str, sha256: str, doc_type: str, created_at: str, match_key: str) -> int:
    with connect() as con:
        cur = con.execute(
            "INSERT INTO files(path, sha256, doc_type, created_at, match_key) VALUES (?,?,?,?,?)",
            (path, sha256, doc_type, created_at, match_key),
        )
        return int(cur.lastrowid)


def insert_invoice_lines(file_id: int, lines: Iterable[Dict[str, Any]]):
    """
    expected line dict:
      {"customer_no": "...", "description": "...", "qty": 123}
    """
    with connect() as con:
        con.executemany(
            "INSERT INTO invoice_lines(file_id, customer_no, description, qty) VALUES (?,?,?,?)",
            [(file_id, l.get("customer_no", ""), l["description"], float(l["qty"])) for l in lines],
        )


def insert_delivery_lines(file_id: int, lines: Iterable[Dict[str, Any]]):
    """
    expected line dict:
      {"customer_no": "...", "item_number": "...", "description": "...", "qty": 123}
    """
    with connect() as con:
        con.executemany(
            "INSERT INTO delivery_lines(file_id, customer_no, item_number, description, qty) VALUES (?,?,?,?,?)",
            [(file_id, l.get("customer_no", ""), l.get("item_number"), l["description"], float(l["qty"])) for l in lines],
        )


def fetch_all_invoice_lines():
    with connect() as con:
        rows = con.execute("""
            SELECT il.customer_no, il.description, il.qty, f.path, f.created_at
            FROM invoice_lines il
            JOIN files f ON f.file_id = il.file_id
            WHERE f.doc_type='invoice'
        """).fetchall()
        return [dict(r) for r in rows]


def fetch_all_delivery_lines():
    with connect() as con:
        rows = con.execute("""
            SELECT dl.customer_no, dl.item_number, dl.description, dl.qty, f.path, f.created_at
            FROM delivery_lines dl
            JOIN files f ON f.file_id = dl.file_id
            WHERE f.doc_type='delivery'
        """).fetchall()
        return [dict(r) for r in rows]


def fetch_invoice_lines_by_customer(customer_no: str):
    with connect() as con:
        rows = con.execute("""
            SELECT il.customer_no, il.description, il.qty, f.path, f.created_at
            FROM invoice_lines il
            JOIN files f ON f.file_id = il.file_id
            WHERE il.customer_no = ?
        """, (customer_no,)).fetchall()
        return [dict(r) for r in rows]


def fetch_delivery_lines_by_customer(customer_no: str):
    with connect() as con:
        rows = con.execute("""
            SELECT dl.customer_no, dl.item_number, dl.description, dl.qty, f.path, f.created_at
            FROM delivery_lines dl
            JOIN files f ON f.file_id = dl.file_id
            WHERE dl.customer_no = ?
        """, (customer_no,)).fetchall()
        return [dict(r) for r in rows]