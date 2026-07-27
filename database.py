import sqlite3
import os
import pandas as pd

DB_NAME = "library.db"
CSV_FILE = "Books.csv"

def get_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def sync_csv_from_db():
    """Syncs updated book quantities back to Books.csv."""
    with get_connection() as conn:
        df = pd.read_sql_query("SELECT title AS name, author, rating, quantity FROM books", conn)
        df.to_csv(CSV_FILE, index=False)

def init_db():
    """Initializes tables and loads/cleans Books.csv dataset."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)
        
        # 2. Books Catalog Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT UNIQUE NOT NULL,
                author TEXT NOT NULL,
                rating REAL NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 10
            )
        """)
        
        # 3. Book Issues Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS book_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                college_id TEXT NOT NULL,
                student_name TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                branch TEXT NOT NULL,
                semester TEXT NOT NULL,
                book_title TEXT NOT NULL,
                image_path TEXT NOT NULL,
                issued_by TEXT NOT NULL,
                issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Load & Clean Books Dataset if table is empty
        cursor.execute("SELECT COUNT(*) as count FROM books")
        if cursor.fetchone()['count'] == 0 and os.path.exists(CSV_FILE):
            df = pd.read_csv(CSV_FILE)
            
            # Clean dataset: select name, author, rating, drop duplicates, add quantity=10
            df_clean = df[['name', 'author', 'rating']].drop_duplicates(subset=['name']).copy()
            df_clean['quantity'] = 10
            
            for _, row in df_clean.iterrows():
                cursor.execute("""
                    INSERT OR IGNORE INTO books (title, author, rating, quantity)
                    VALUES (?, ?, ?, ?)
                """, (str(row['name']), str(row['author']), float(row['rating']), int(row['quantity'])))
            
            conn.commit()
            sync_csv_from_db()

# --- USER AUTH LOGIC ---

def create_user(username, email, hashed_password):
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)", 
                           (username, email, hashed_password))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False

def get_user_by_username(username):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cursor.fetchone()

# --- BOOK CATALOG & QUANTITY LOGIC ---

def get_all_books():
    """Retrieves all books in the catalog."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM books ORDER BY title ASC")
        return cursor.fetchall()

def get_available_books():
    """Retrieves books that have quantity > 0 for issuing."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM books WHERE quantity > 0 ORDER BY title ASC")
        return cursor.fetchall()

def deduct_book_quantity(book_title):
    """Deducts 1 from quantity in database and updates Books.csv."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE books SET quantity = quantity - 1 WHERE title = ? AND quantity > 0", (book_title,))
        conn.commit()
    sync_csv_from_db()

def restore_book_quantity(book_title):
    """Increments 1 to quantity in database and updates Books.csv upon return."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE books SET quantity = quantity + 1 WHERE title = ?", (book_title,))
        conn.commit()
    sync_csv_from_db()

# --- ISSUE RECORD LOGIC ---

def add_issue_record(college_id, name, phone, branch, semester, book_title, image_path, issued_by):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO book_issues (college_id, student_name, phone_number, branch, semester, book_title, image_path, issued_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (college_id, name, phone, branch, semester, book_title, image_path, issued_by))
        conn.commit()

def get_all_records():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM book_issues ORDER BY issued_at DESC")
        return cursor.fetchall()

def get_record_by_id(record_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM book_issues WHERE id = ?", (record_id,))
        return cursor.fetchone()

def delete_record(record_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM book_issues WHERE id = ?", (record_id,))
        conn.commit()

def get_dashboard_metrics():
    """Calculates metrics for home dashboard."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT SUM(quantity) as total_remaining FROM books")
        remaining_books = cursor.fetchone()['total_remaining'] or 0
        
        cursor.execute("SELECT COUNT(*) as count FROM book_issues")
        issued_count = cursor.fetchone()['count']
        
        return {
            'books_remaining': remaining_books,
            'issued_count': issued_count
        }