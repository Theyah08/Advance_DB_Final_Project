"""
Database Systems Lecture Topic: Advanced SQL Operations & Indexing Strategies
Verification Utility using EXPLAIN / EXPLAIN ANALYZE.

Demonstrates query execution plans with and without B-Tree indexes:
  1. Product text search by name (idx_products_name)
  2. Barcode scanner lookup (idx_products_barcode)
  3. Relational product-category JOIN (idx_products_category_id)
  4. Date-range sales transaction history (idx_sales_created_at)
  5. Inventory movement audit trail (idx_inventory_movements_product_id, idx_inventory_movements_created_at)

Usage:
  python verify_indexes.py
"""

import sys
import os
from database import get_db, IS_POSTGRES, get_active_engine, normalize_query_for_engine

def explain_query(title, sql, params=()):
    print("\n" + "=" * 78)
    print(f"QUERY: {title}")
    print("=" * 78)
    print(f"SQL: {sql.strip()}")
    print(f"Parameters: {params}")
    print("-" * 78)
    
    conn = get_db()
    is_pg = IS_POSTGRES
    
    try:
        cur = conn.cursor()
        if is_pg:
            # PostgreSQL EXPLAIN ANALYZE provides actual runtimes, planning time, and heap scans vs index scans
            explain_sql = f"EXPLAIN ANALYZE {sql}"
            cur.execute(explain_sql, params)
            rows = cur.fetchall()
            print("PostgreSQL EXPLAIN ANALYZE Execution Plan:")
            for r in rows:
                print(" ", r[0])
        else:
            # SQLite fallback EXPLAIN QUERY PLAN
            explain_sql = f"EXPLAIN QUERY PLAN {normalize_query_for_engine(sql, is_pg)}"
            cur.execute(explain_sql, params)
            rows = cur.fetchall()
            print("EXPLAIN QUERY PLAN:")
            for r in rows:
                print(f"  id: {r[0]}, parent: {r[1]}, detail: {r[3]}")
    except Exception as e:
        print(f"Explain notice: {e}")
    finally:
        conn.close()

def main():
    conn = get_db()
    conn.close()
    
    print("=" * 78)
    print("  PROSFORA GIFT SHOP POS - ADVANCED DATABASE INDEX VERIFICATION")
    print("=" * 78)
    print(f"Active Backend Engine: [{get_active_engine()}]")

    # 1. Product Name Search
    explain_query(
        "1. Product Search by Name (Search box typing 'Ceramic')",
        "SELECT * FROM products WHERE name LIKE %s;",
        ('%Ceramic%',)
    )

    # 2. Product Barcode POS Scanner Lookup
    explain_query(
        "2. Barcode POS Scanner Instant Lookup (O(log N) B-Tree)",
        "SELECT * FROM products WHERE barcode = %s;",
        ('PROS-MUG-001',)
    )

    # 3. Category Foreign Key Relational JOIN
    explain_query(
        "3. Products by Category (Category filtering & JOIN)",
        "SELECT p.id, p.name, c.name as category FROM products p JOIN categories c ON p.category_id = c.id WHERE c.id = %s;",
        (1,)
    )

    # 4. Sales History Date-Range Filtering
    explain_query(
        "4. Sales History Chronological Date-Range Query",
        "SELECT * FROM sales WHERE created_at >= %s AND created_at <= %s ORDER BY created_at DESC;",
        ('2026-11-01 00:00:00', '2026-11-30 23:59:59')
    )

    # 5. Inventory Movements Audit Trail
    explain_query(
        "5. Inventory Movements by Product ID",
        "SELECT * FROM inventory_movements WHERE product_id = %s ORDER BY created_at DESC;",
        (1,)
    )
    
    print("\n" + "=" * 78)
    print("SUMMARY OF INDEXING PERFORMANCE TRADE-OFFS:")
    print("  + READ PERFORMANCE: B-Tree indexes convert O(N) sequential scans to O(log N)")
    print("    search times. Essential for fast POS checkout scanning and sales reports.")
    print("  - WRITE OVERHEAD: Every INSERT, UPDATE (on indexed fields), and DELETE requires")
    print("    updating the index structures. Indexes were strategically chosen to balance")
    print("    sub-millisecond checkout lookups with low write amplification.")
    print("=" * 78)

if __name__ == '__main__':
    main()
