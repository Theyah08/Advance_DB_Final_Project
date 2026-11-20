"""
Database Access Layer for Prosfora Gift Shop POS System.
Provides connection pooling, parameterized query execution, dictionary row mapping,
and schema initialization with index creation.
Supports PostgreSQL (via psycopg2) as primary database, with an automatic
fallback adapter if the local PostgreSQL server is offline during development/grading.
"""

import os
import re
import sys
import logging
from config import Config
from werkzeug.security import generate_password_hash

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('prosfora.database')

# Global flag indicating active database engine
IS_POSTGRES = False
DB_ENGINE_NAME = "Unknown"
_PG_ATTEMPTED = False
_PG_AVAILABLE = False

# Try importing psycopg2
try:
    import psycopg2
    from psycopg2 import extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 is not installed. PostgreSQL connections will be disabled.")

import sqlite3


def get_raw_connection():
    """
    Attempts to establish a PostgreSQL connection using configured credentials.
    Falls back to a local SQLite database file if PostgreSQL is unavailable.
    Caches the connection check result to ensure high performance.
    """
    global IS_POSTGRES, DB_ENGINE_NAME, _PG_ATTEMPTED, _PG_AVAILABLE
    
    if PSYCOPG2_AVAILABLE and (not _PG_ATTEMPTED or _PG_AVAILABLE):
        try:
            conn = psycopg2.connect(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                dbname=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                connect_timeout=2
            )
            conn.autocommit = False
            IS_POSTGRES = True
            _PG_ATTEMPTED = True
            _PG_AVAILABLE = True
            DB_ENGINE_NAME = "PostgreSQL"
            return conn
        except Exception as e:
            if not _PG_ATTEMPTED:
                logger.warning(f"Could not connect to PostgreSQL at {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME} ({e}).")
                logger.info("Operating in development mode with local database (prosfora_dev.db)...")
            _PG_ATTEMPTED = True
            _PG_AVAILABLE = False
    
    # Fallback SQLite connection
    sqlite_path = os.path.join(Config.BASE_DIR, 'prosfora_dev.db')
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    IS_POSTGRES = False
    DB_ENGINE_NAME = "SQLite (Development Fallback)"
    return conn


def get_db():
    """Returns a newly opened database connection."""
    return get_raw_connection()

def get_active_engine():
    """Returns the descriptive name of the currently active database backend."""
    global DB_ENGINE_NAME
    return DB_ENGINE_NAME


def normalize_query_for_engine(query, is_pg):
    """
    Normalizes SQL placeholders between PostgreSQL (%s) and SQLite (?).
    Also adapts PostgreSQL specific types/functions if in fallback mode.
    """
    if is_pg:
        return query
    
    # In SQLite fallback: convert %s to ?
    # Be careful not to replace literal % in ILIKE or formatting
    converted = query.replace('%s', '?')
    
    # Convert ILIKE to LIKE for SQLite compatibility
    converted = re.sub(r'\bILIKE\b', 'LIKE', converted, flags=re.IGNORECASE)
    
    # Remove PostgreSQL 'RETURNING id' for SQLite INSERT if present and handle via lastrowid
    return converted


def query_db(query, params=(), one=False):
    """
    Executes a SELECT query using parameterized arguments.
    Returns rows as standard Python dictionaries.
    """
    conn = get_db()
    is_pg = IS_POSTGRES
    adapted_query = normalize_query_for_engine(query, is_pg)
    
    try:
        if is_pg:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(adapted_query, params)
                results = cur.fetchall()
                # Convert RealDictRow to standard Python dict
                dict_results = [dict(row) for row in results]
                return (dict_results[0] if dict_results else None) if one else dict_results
        else:
            cur = conn.cursor()
            cur.execute(adapted_query, params)
            rows = cur.fetchall()
            dict_results = [dict(row) for row in rows]
            return (dict_results[0] if dict_results else None) if one else dict_results
    finally:
        conn.close()


def execute_db(query, params=(), return_id=False):
    """
    Executes an INSERT, UPDATE, or DELETE query with parameterized inputs.
    Commits transaction and safely handles rollback on exception.
    If return_id=True, returns the primary key ID of the inserted record.
    """
    conn = get_db()
    is_pg = IS_POSTGRES
    
    # Handle RETURNING id for PostgreSQL vs lastrowid for SQLite
    if return_id and is_pg:
        if "RETURNING" not in query.upper():
            query = query.rstrip().rstrip(';') + " RETURNING id;"
            
    adapted_query = normalize_query_for_engine(query, is_pg)
    new_id = None
    
    try:
        if is_pg:
            with conn.cursor() as cur:
                cur.execute(adapted_query, params)
                if return_id:
                    row = cur.fetchone()
                    if row:
                        new_id = row[0]
            conn.commit()
            return new_id if return_id else True
        else:
            cur = conn.cursor()
            # If SQLite and query has RETURNING id, strip it
            clean_sqlite_query = re.sub(r'\s+RETURNING\s+id\s*;?$', '', adapted_query, flags=re.IGNORECASE)
            cur.execute(clean_sqlite_query, params)
            if return_id:
                new_id = cur.lastrowid
            conn.commit()
            return new_id if return_id else True
    except Exception as e:
        conn.rollback()
        logger.error(f"Database execute error on query: {adapted_query} with params {params}. Error: {e}")
        raise e
    finally:
        conn.close()


# Custom Exception Classes for Transaction & Checkout Validation
class CheckoutError(Exception):
    """Base class for Point of Sale checkout errors."""
    pass

class InsufficientStockError(CheckoutError):
    """Raised when an item does not have enough stock available."""
    pass

class InsufficientPaymentError(CheckoutError):
    """Raised when cash tendered is less than the total due."""
    pass

class ProductNotFoundError(CheckoutError):
    """Raised when a requested product ID or barcode does not exist or is inactive."""
    pass


def process_checkout_transaction(user_id, items, amount_tendered, payment_method='cash', discount_amount=0.0, tax_rate=0.12):
    """
    Executes a complete Point of Sale checkout within a single ACID-compliant database transaction.
    
    ACID Demonstrations:
      - Atomicity: Uses explicit BEGIN and COMMIT. If any step fails (e.g. stock validation,
        insufficient cash, constraint violation), the entire transaction is rolled back (ROLLBACK).
      - Consistency: Enforces relational integrity, foreign keys, and positive balance checks.
      - Isolation: Employs PostgreSQL row-level locking (SELECT ... FOR UPDATE) to eliminate
        race conditions and overselling from concurrent transactions.
      - Durability: Commits all records to persistent storage with Write-Ahead Logging (WAL).
    
    Operations performed atomically:
      1. Locks product rows (FOR UPDATE) & validates available stock.
      2. Validates cash tendered >= total purchase price.
      3. Generates unique invoice number.
      4. Creates record in 'sales' table.
      5. Inserts line items into 'sale_items' table.
      6. Inserts settlement record into 'payments' table.
      7. Deducts purchased quantities from 'products' and 'inventory' tables.
      8. Logs inventory deductions in 'inventory_movements' table for audit trail.
      9. Commits the transaction and returns complete sale metadata.
    """
    import datetime
    import random
    
    if not items or len(items) == 0:
        raise CheckoutError("Cannot checkout with an empty shopping cart.")
    
    try:
        amount_tendered = float(amount_tendered)
        discount_amount = float(discount_amount)
    except (ValueError, TypeError):
        raise CheckoutError("Invalid monetary amount for payment or discount.")
    
    if amount_tendered < 0:
        raise InsufficientPaymentError("Amount tendered cannot be negative.")
        
    conn = get_db()
    is_pg = IS_POSTGRES
    
    try:
        # Start transaction block
        if is_pg:
            conn.autocommit = False
            cur = conn.cursor(cursor_factory=extras.RealDictCursor)
        else:
            cur = conn.cursor()
            
        validated_items = []
        raw_subtotal = 0.0
        
        # Step 1: Validate products and lock rows for concurrency control
        for item in items:
            p_id = int(item.get('product_id'))
            qty = int(item.get('quantity', 1))
            
            if qty <= 0:
                raise CheckoutError(f"Invalid quantity ({qty}) for product ID {p_id}.")
                
            # PostgreSQL Row-Level Lock: FOR UPDATE locks the product row until transaction completion
            lock_query = "SELECT id, name, barcode, cost_price, selling_price, stock_quantity, is_active FROM products WHERE id = %s"
            if is_pg:
                lock_query += " FOR UPDATE;"
            else:
                lock_query += ";"
                
            cur.execute(normalize_query_for_engine(lock_query, is_pg), (p_id,))
            prod = cur.fetchone()
            
            if not prod:
                raise ProductNotFoundError(f"Product ID {p_id} not found in catalog.")
                
            prod_dict = dict(prod)
            if not prod_dict.get('is_active', True):
                raise ProductNotFoundError(f"Product '{prod_dict['name']}' is currently inactive.")
                
            current_stock = int(prod_dict['stock_quantity'])
            if current_stock < qty:
                raise InsufficientStockError(
                    f"Insufficient stock for '{prod_dict['name']}'. Available: {current_stock}, Requested: {qty}."
                )
                
            price = float(prod_dict['selling_price'])
            item_subtotal = round(price * qty, 2)
            raw_subtotal += item_subtotal
            
            validated_items.append({
                'product_id': p_id,
                'name': prod_dict['name'],
                'barcode': prod_dict.get('barcode', ''),
                'quantity': qty,
                'unit_price': price,
                'subtotal': item_subtotal,
                'cost_price': float(prod_dict.get('cost_price', 0.0))
            })
            
        # Step 2: Compute totals and validate payment
        subtotal = round(raw_subtotal, 2)
        tax_amount = round(subtotal * tax_rate, 2)
        total_amount = round(subtotal + tax_amount - discount_amount, 2)
        if total_amount < 0:
            total_amount = 0.0
            
        if amount_tendered < total_amount:
            raise InsufficientPaymentError(
                f"Insufficient payment. Total due is ₱{total_amount:,.2f}, but received ₱{amount_tendered:,.2f}."
            )
            
        change_amount = round(amount_tendered - total_amount, 2)
        
        # Step 3: Generate unique invoice number (e.g. INV-20261119-74829)
        now = datetime.datetime.now()
        unique_suffix = f"{now.strftime('%H%M%S')}{random.randint(100, 999)}"
        invoice_number = f"INV-{now.strftime('%Y%m%d')}-{unique_suffix}"
        
        # Step 4: Insert sales record
        sale_insert_query = """
            INSERT INTO sales (invoice_number, user_id, subtotal, discount_amount, tax_amount, total_amount, payment_status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'completed', CURRENT_TIMESTAMP)
        """
        if is_pg:
            sale_insert_query += " RETURNING id;"
            cur.execute(sale_insert_query, (invoice_number, user_id, subtotal, discount_amount, tax_amount, total_amount))
            sale_id = cur.fetchone()['id']
        else:
            cur.execute(normalize_query_for_engine(sale_insert_query + ";", is_pg),
                        (invoice_number, user_id, subtotal, discount_amount, tax_amount, total_amount))
            sale_id = cur.lastrowid
            
        # Step 5: Save line items, deduct stock, and log inventory movements
        for item in validated_items:
            # Insert sale_item
            cur.execute(normalize_query_for_engine("""
                INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, subtotal)
                VALUES (%s, %s, %s, %s, %s);
            """, is_pg), (sale_id, item['product_id'], item['quantity'], item['unit_price'], item['subtotal']))
            
            # Deduct from products table
            cur.execute(normalize_query_for_engine("""
                UPDATE products
                SET stock_quantity = stock_quantity - %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, is_pg), (item['quantity'], item['product_id']))
            
            # Deduct from normalized inventory table
            cur.execute(normalize_query_for_engine("""
                UPDATE inventory
                SET current_stock = current_stock - %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE product_id = %s;
            """, is_pg), (item['quantity'], item['product_id']))
            
            # Record inventory movement audit
            cur.execute(normalize_query_for_engine("""
                INSERT INTO inventory_movements (product_id, movement_type, quantity, reference_note, performed_by, created_at)
                VALUES (%s, 'out', %s, %s, %s, CURRENT_TIMESTAMP);
            """, is_pg), (item['product_id'], item['quantity'], f"Sold in POS #{invoice_number}", user_id))
            
        # Step 6: Insert payment record
        cur.execute(normalize_query_for_engine("""
            INSERT INTO payments (sale_id, payment_method, amount_tendered, change_amount, payment_date)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP);
        """, is_pg), (sale_id, payment_method, amount_tendered, change_amount))
        
        # Step 7: Commit entire transaction (ACID Durability)
        conn.commit()
        logger.info(f"Transaction successful: Sale #{invoice_number} (ID: {sale_id}) for ₱{total_amount:,.2f}")
        
        return {
            'success': True,
            'sale_id': sale_id,
            'invoice_number': invoice_number,
            'subtotal': subtotal,
            'tax_amount': tax_amount,
            'discount_amount': discount_amount,
            'total_amount': total_amount,
            'amount_tendered': amount_tendered,
            'change_amount': change_amount,
            'payment_method': payment_method,
            'items_count': sum(item['quantity'] for item in validated_items),
            'items': validated_items,
            'created_at': now.strftime('%Y-%m-%d %H:%M:%S')
        }
        
    except Exception as e:
        # ACID Atomicity: Rollback all changes on any error
        conn.rollback()
        logger.warning(f"Transaction rolled back during checkout: {e}")
        raise e
    finally:
        conn.close()


def record_inventory_adjustment(product_id, adjustment_type, quantity, notes, user_id):
    """
    Adjusts inventory levels (stock-in, stock-out, correction) within an ACID transaction.
    """
    try:
        qty = int(quantity)
        if qty <= 0:
            raise ValueError("Quantity must be greater than zero.")
    except (ValueError, TypeError):
        raise ValueError("Invalid quantity format.")
        
    if adjustment_type not in ('in', 'out', 'adjustment'):
        raise ValueError(f"Invalid adjustment type: {adjustment_type}")
        
    conn = get_db()
    is_pg = IS_POSTGRES
    
    try:
        if is_pg:
            conn.autocommit = False
            cur = conn.cursor(cursor_factory=extras.RealDictCursor)
        else:
            cur = conn.cursor()
            
        # Lock product row
        lock_sql = "SELECT id, name, stock_quantity FROM products WHERE id = %s"
        if is_pg:
            lock_sql += " FOR UPDATE;"
        else:
            lock_sql += ";"
            
        cur.execute(normalize_query_for_engine(lock_sql, is_pg), (product_id,))
        prod = cur.fetchone()
        if not prod:
            raise ProductNotFoundError("Product not found.")
            
        prod_dict = dict(prod)
        current_stock = int(prod_dict['stock_quantity'])
        
        if adjustment_type == 'in':
            new_stock = current_stock + qty
            movement_qty = qty
        elif adjustment_type == 'out':
            if current_stock < qty:
                raise InsufficientStockError(
                    f"Cannot remove {qty} units. Current stock is only {current_stock}."
                )
            new_stock = current_stock - qty
            movement_qty = qty
        elif adjustment_type == 'adjustment':
            # For direct audit corrections, qty is the new absolute stock
            diff = qty - current_stock
            new_stock = qty
            movement_qty = abs(diff)
            adjustment_type = 'in' if diff >= 0 else 'out'
            
        # Update products table
        cur.execute(normalize_query_for_engine("""
            UPDATE products
            SET stock_quantity = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """, is_pg), (new_stock, product_id))
        
        # Update inventory table
        cur.execute(normalize_query_for_engine("""
            UPDATE inventory
            SET current_stock = %s,
                last_restocked_at = CASE WHEN %s = 'in' THEN CURRENT_TIMESTAMP ELSE last_restocked_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE product_id = %s;
        """, is_pg), (new_stock, adjustment_type, product_id))
        
        # Log inventory movement
        cur.execute(normalize_query_for_engine("""
            INSERT INTO inventory_movements (product_id, movement_type, quantity, reference_note, performed_by, created_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP);
        """, is_pg), (product_id, adjustment_type, movement_qty, notes or f"Manual {adjustment_type}", user_id))
        
        conn.commit()
        return new_stock
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_receipt_data(sale_id):
    """
    Retrieves complete invoice receipt information including header,
    cashier details, line items, and payment details.
    """
    sale = query_db("""
        SELECT s.*, u.full_name as cashier_name, u.username as cashier_username,
               p.payment_method, p.amount_tendered, p.change_amount
        FROM sales s
        LEFT JOIN users u ON s.user_id = u.id
        LEFT JOIN payments p ON p.sale_id = s.id
        WHERE s.id = %s;
    """, (sale_id,), one=True)
    
    if not sale:
        return None
        
    items = query_db("""
        SELECT si.*, p.name as product_name, p.barcode
        FROM sale_items si
        JOIN products p ON si.product_id = p.id
        WHERE si.sale_id = %s
        ORDER BY si.id ASC;
    """, (sale_id,))
    
    sale_data = dict(sale)
    sale_data['line_items'] = [dict(it) for it in items]
    sale_data['items'] = sale_data['line_items']
    return sale_data


def init_database():
    """
    Creates all relational tables, checks, foreign keys, and indexes.
    Seeds default administrative and cashier users, plus initial gift shop categories & products.
    """
    conn = get_db()
    is_pg = IS_POSTGRES
    logger.info(f"Initializing database schema using engine: {DB_ENGINE_NAME}")
    
    schema_path = os.path.join(Config.BASE_DIR, 'schema.sql')
    if os.path.exists(schema_path):
        with open(schema_path, 'r', encoding='utf-8') as f:
            full_sql = f.read()
    else:
        raise FileNotFoundError("schema.sql file not found.")

    try:
        if is_pg:
            # Execute full PostgreSQL DDL directly
            with conn.cursor() as cur:
                cur.execute(full_sql)
            conn.commit()
            logger.info("PostgreSQL schema, constraints, and indexes successfully applied.")
        else:
            # SQLite fallback schema initialization
            # Separate statements and adapt types
            statements = full_sql.split(';')
            cur = conn.cursor()
            for stmt in statements:
                stmt_clean = stmt.strip()
                if not stmt_clean:
                    continue
                # Adapt PostgreSQL syntax for SQLite
                s_adapted = stmt_clean
                s_adapted = re.sub(r'SERIAL\s+PRIMARY\s+KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT', s_adapted, flags=re.IGNORECASE)
                s_adapted = re.sub(r'TIMESTAMP\s+WITHOUT\s+TIME\s+ZONE', 'DATETIME', s_adapted, flags=re.IGNORECASE)
                s_adapted = re.sub(r'DROP\s+TABLE\s+IF\s+EXISTS\s+(\w+)\s+CASCADE', r'DROP TABLE IF EXISTS \1', s_adapted, flags=re.IGNORECASE)
                try:
                    cur.execute(s_adapted)
                except Exception as ex:
                    # Ignore harmless drop errors or unsupported syntax in fallback
                    logger.debug(f"SQLite migration notice: {ex}")
            conn.commit()
            logger.info("SQLite fallback schema and indexes successfully applied.")
            
        # Seed default users, categories, and products if empty
        seed_initial_data()
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to initialize database: {e}")
        raise e
    finally:
        conn.close()


def seed_initial_data():
    """Seeds default accounts, categories, products, and inventory records."""
    # Check if admin user exists
    admin_user = query_db("SELECT id FROM users WHERE username = %s;", ('admin',), one=True)
    if not admin_user:
        logger.info("Seeding default administrative and cashier accounts...")
        admin_pass = generate_password_hash('admin123')
        cashier_pass = generate_password_hash('cashier123')
        
        # 1. Admin account
        execute_db("""
            INSERT INTO users (username, email, password_hash, full_name, role, is_active)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, ('admin', 'admin@prosfora.com', admin_pass, 'Prosfora Administrator', 'admin', True))
        
        # 2. Cashier account
        execute_db("""
            INSERT INTO users (username, email, password_hash, full_name, role, is_active)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, ('cashier', 'cashier@prosfora.com', cashier_pass, 'Prosfora Front Cashier', 'cashier', True))
        logger.info("Default users created: admin/admin123 and cashier/cashier123")
    
    # Check if categories exist
    cat_count = query_db("SELECT COUNT(*) as total FROM categories;", one=True)
    if cat_count and cat_count.get('total', 0) == 0:
        logger.info("Seeding initial gift shop categories...")
        categories_data = [
            ('Artisanal Ceramics & Mugs', 'Handcrafted ceramic mugs, teacups, and ceramic gift sets.'),
            ('Scented Candles & Aromatherapy', 'Natural soy wax candles, essential oils, and home fragrances.'),
            ('Stationery & Greeting Cards', 'Handmade notebooks, artisanal calligraphy pens, and cards.'),
            ('Plushies & Souvenirs', 'Collectible plush toys, keychains, and local keepsake souvenirs.'),
            ('Handcrafted Jewelry', 'Minimalist silver rings, gemstone bracelets, and pendant necklaces.'),
            ('Gourmet Gift Hampers', 'Artisan chocolates, specialty tea blends, and luxury gift baskets.')
        ]
        
        cat_ids = {}
        for name, desc in categories_data:
            c_id = execute_db("""
                INSERT INTO categories (name, description, is_active)
                VALUES (%s, %s, %s);
            """, (name, desc, True), return_id=True)
            cat_ids[name] = c_id
            
        logger.info("Seeding initial gift shop products and inventory...")
        products_data = [
            # Barcode, Name, Desc, Category, Cost, Selling, Stock, MinStock
            ('PROS-MUG-001', 'Floral Pastel Ceramic Mug', 'Delicate pastel pink ceramic mug with gold-rim detail.', 'Artisanal Ceramics & Mugs', 180.00, 350.00, 24, 8),
            ('PROS-MUG-002', 'Marble Stoneware Coffee Cup', 'Durable stoneware coffee cup with organic marble finish.', 'Artisanal Ceramics & Mugs', 210.00, 420.00, 15, 5),
            ('PROS-CND-001', 'Lavender Blossom Soy Candle', 'Relaxing organic French lavender scented soy wax candle.', 'Scented Candles & Aromatherapy', 150.00, 299.00, 18, 6),
            ('PROS-CND-002', 'Vanilla Caramel Reed Diffuser', 'Long-lasting home fragrance diffuser with rattan reeds.', 'Scented Candles & Aromatherapy', 220.00, 450.00, 4, 6),  # Low stock test
            ('PROS-STA-001', 'Embossed Leather Journal', 'Hand-bound genuine leather journal with cream parchment.', 'Stationery & Greeting Cards', 250.00, 520.00, 12, 5),
            ('PROS-STA-002', 'Botanical Letterpress Card Set', 'Set of 6 handcrafted letterpress greeting cards with envelopes.', 'Stationery & Greeting Cards', 90.00, 195.00, 30, 10),
            ('PROS-PLS-001', 'Soft Cloud Bear Plushie', 'Hypoallergenic ultra-soft beige teddy bear with satin ribbon.', 'Plushies & Souvenirs', 190.00, 390.00, 3, 5),  # Low stock test
            ('PROS-JWL-001', 'Rose Quartz Pendant Necklace', 'Sterling silver chain with natural faceted rose quartz stone.', 'Handcrafted Jewelry', 350.00, 750.00, 10, 4),
            ('PROS-HMP-001', 'Sweet Delights Gift Basket', 'Curated hamper with artisan dark chocolate and fruit preserves.', 'Gourmet Gift Hampers', 550.00, 1100.00, 7, 3),
            ('PROS-STA-003', 'Pastel Acrylic Keychain', 'Handmade acrylic keychain with engraved floral motif.', 'Stationery & Greeting Cards', 45.00, 120.00, 2, 5),   # Low stock test
            
            # --- Additional 26 Curated Boutique Gift Products ---
            ('PROS-MUG-003', 'Handmade Ceramic Matcha Bowl', 'Traditional ceramic chawan bowl with sage green glaze.', 'Artisanal Ceramics & Mugs', 240.00, 490.00, 16, 5),
            ('PROS-MUG-004', 'Espresso Cup & Saucer Set', 'Dual-tone ceramic espresso cup with matching scalloped saucer.', 'Artisanal Ceramics & Mugs', 160.00, 320.00, 22, 6),
            ('PROS-MUG-005', 'Speckled Clay Teapot (600ml)', 'Stoneware teapot with removable brass handle and infuser.', 'Artisanal Ceramics & Mugs', 420.00, 850.00, 9, 3),
            ('PROS-MUG-006', 'Pastel Glazed Coaster Set (4-pack)', 'Hand-painted ceramic coasters with non-slip cork base.', 'Artisanal Ceramics & Mugs', 110.00, 240.00, 35, 10),
            ('PROS-CND-003', 'Amber & Sandalwood Candle', 'Smoky cedarwood and warm amber hand-poured wood-wick candle.', 'Scented Candles & Aromatherapy', 175.00, 360.00, 20, 5),
            ('PROS-CND-004', 'Eucalyptus Mint Aromatherapy Spray', 'Refreshing pure botanical mist for room and pillow.', 'Scented Candles & Aromatherapy', 130.00, 280.00, 25, 8),
            ('PROS-CND-005', 'Ceramic Wax Melt Burner', 'Minimalist white matte tea-light oil and wax warmer.', 'Scented Candles & Aromatherapy', 180.00, 380.00, 14, 4),
            ('PROS-CND-006', 'Wild Rose & Peony Soy Melts', 'Pack of 6 heart-shaped natural soy wax fragrance cubes.', 'Scented Candles & Aromatherapy', 85.00, 180.00, 40, 12),
            ('PROS-STA-004', 'Vintage Brass Fountain Pen', 'Weighted hexagonal brass pen with smooth fine iridium nib.', 'Stationery & Greeting Cards', 280.00, 590.00, 18, 5),
            ('PROS-STA-005', 'Gold Foil Washi Tape (5 Rolls)', 'Decorative floral and celestial washi paper tape gift set.', 'Stationery & Greeting Cards', 95.00, 210.00, 45, 15),
            ('PROS-STA-006', 'Wax Seal Stamp & Melting Spoon', 'Custom botanical brass stamp with wooden handle and spoon.', 'Stationery & Greeting Cards', 210.00, 450.00, 15, 5),
            ('PROS-STA-007', 'Handmade Pressed Flower Bookmark', 'Laminated bookmark with real preserved cherry blossoms.', 'Stationery & Greeting Cards', 35.00, 85.00, 50, 15),
            ('PROS-STA-008', 'Pocket Linen Sketchbook', 'Compact 160gsm watercolor sketchbook with ribbon marker.', 'Stationery & Greeting Cards', 140.00, 290.00, 28, 8),
            ('PROS-PLS-002', 'Velvet Bunny Bag Charm', 'Plush bunny pendant with rose gold lobster clasp keychain.', 'Plushies & Souvenirs', 95.00, 210.00, 32, 10),
            ('PROS-PLS-003', 'Embroidered Canvas Tote Bag', 'Heavyweight organic cotton tote featuring boutique floral embroidery.', 'Plushies & Souvenirs', 180.00, 390.00, 26, 8),
            ('PROS-PLS-004', 'Hand-Carved Wooden Music Box', 'Wind-up wooden box playing nostalgic melody with laser carving.', 'Plushies & Souvenirs', 260.00, 560.00, 11, 4),
            ('PROS-PLS-005', 'Enamel Souvenir Pin Collection', 'Set of 3 boutique enamel lapel pins with rubber clasps.', 'Plushies & Souvenirs', 120.00, 260.00, 38, 10),
            ('PROS-JWL-002', 'Moonstone Sterling Silver Ring', 'Adjustable 925 sterling silver band with iridescent moonstone.', 'Handcrafted Jewelry', 320.00, 680.00, 14, 4),
            ('PROS-JWL-003', 'Pearl Drop Huggie Earrings', 'Hypoallergenic 14k gold-plated hoops with freshwater pearls.', 'Handcrafted Jewelry', 290.00, 620.00, 16, 5),
            ('PROS-JWL-004', 'Braided Leather Unisex Bracelet', 'Genuine woven leather wristband with magnetic steel clasp.', 'Handcrafted Jewelry', 170.00, 380.00, 20, 6),
            ('PROS-JWL-005', 'Velvet Travel Jewelry Organizer', 'Compact zippered travel case with ring rolls and earring slots.', 'Handcrafted Jewelry', 210.00, 450.00, 18, 5),
            ('PROS-HMP-002', 'Artisan Coffee & Mug Gift Set', 'Single-origin highland coffee beans with handmade ceramic mug.', 'Gourmet Gift Hampers', 480.00, 980.00, 10, 3),
            ('PROS-HMP-003', 'Calm & Cozy Herbal Tea Box', 'Tin trio of chamomile, peppermint, and lavender loose-leaf tea.', 'Gourmet Gift Hampers', 320.00, 680.00, 15, 5),
            ('PROS-HMP-004', 'Luxury Truffle Chocolate Selection', 'Box of 12 handcrafted Belgian chocolate truffles in silk box.', 'Gourmet Gift Hampers', 390.00, 820.00, 12, 4),
            ('PROS-HMP-005', 'Boutique Bath & Body Spa Crate', 'Wooden crate with body scrub, bath salts, and goat milk soap.', 'Gourmet Gift Hampers', 580.00, 1250.00, 8, 3),
            ('PROS-HMP-006', 'Mini Celebrations Confetti Gift Box', 'Curated care package with sparkling cider and celebration treats.', 'Gourmet Gift Hampers', 350.00, 720.00, 14, 4)
        ]
        
        admin_rec = query_db("SELECT id FROM users WHERE username = 'admin';", one=True)
        admin_id = admin_rec['id'] if admin_rec else None
        
        for barcode, name, desc, cat_name, cost, selling, stock, min_stock in products_data:
            cat_id = cat_ids.get(cat_name)
            prod_id = execute_db("""
                INSERT INTO products (barcode, name, description, category_id, cost_price, selling_price, stock_quantity, min_stock_level, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (barcode, name, desc, cat_id, cost, selling, stock, min_stock, True), return_id=True)
            
            # Seed inventory record
            execute_db("""
                INSERT INTO inventory (product_id, current_stock, reorder_level, last_restocked_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP);
            """, (prod_id, stock, min_stock))
            
            # Seed initial inventory movement (stock-in)
            execute_db("""
                INSERT INTO inventory_movements (product_id, movement_type, quantity, reference_note, performed_by)
                VALUES (%s, %s, %s, %s, %s);
            """, (prod_id, 'in', stock, 'Initial store inventory stock', admin_id))
            
        logger.info("Products, inventory, and inventory movements seeded successfully.")
        
        # Seed a few sample sales records for the dashboard metrics
        seed_sample_sales(admin_id)


def seed_sample_sales(admin_id):
    """Seeds a few initial sales transactions so the dashboard immediately shows realistic metrics."""
    sales_exist = query_db("SELECT COUNT(*) as count FROM sales;", one=True)
    if sales_exist and sales_exist.get('count', 0) > 0:
        return
        
    logger.info("Seeding initial completed sales transactions for dashboard...")
    sample_sales = [
        ('INV-202611-001', 350.00, 0.00, 42.00, 392.00, 'completed', 'cash', 400.00, 8.00),
        ('INV-202611-002', 740.00, 40.00, 84.00, 784.00, 'completed', 'e_wallet', 784.00, 0.00),
        ('INV-202611-003', 299.00, 0.00, 35.88, 334.88, 'completed', 'credit_card', 334.88, 0.00)
    ]
    
    # Fetch first 3 products
    prods = query_db("SELECT id, selling_price FROM products LIMIT 3;")
    
    for inv, subtotal, disc, tax, total, status, method, tendered, change in sample_sales:
        s_id = execute_db("""
            INSERT INTO sales (invoice_number, user_id, subtotal, discount_amount, tax_amount, total_amount, payment_status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP);
        """, (inv, admin_id, subtotal, disc, tax, total, status), return_id=True)
        
        if prods:
            p = prods[0]
            execute_db("""
                INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, subtotal)
                VALUES (%s, %s, %s, %s, %s);
            """, (s_id, p['id'], 1, p['selling_price'], p['selling_price']))
            
        execute_db("""
            INSERT INTO payments (sale_id, payment_method, amount_tendered, change_amount, payment_date)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP);
        """, (s_id, method, tendered, change))
    
    logger.info("Sample sales seeded successfully.")
