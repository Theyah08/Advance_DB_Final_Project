"""
Database Initialization Script for Prosfora Gift Shop POS System.
Run this script to initialize or reset tables, apply constraints,
create database indexes, and seed default administrative & test data.

Usage:
    python init_db.py
"""

import sys
import logging
from database import init_database, get_active_engine
from config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('prosfora.init')

def main():
    print("=" * 70)
    print("  PROSFORA GIFT SHOP POS - DATABASE INITIALIZATION UTILITY")
    print("=" * 70)
    print(f"Target Configuration:")
    print(f"  - PostgreSQL Host: {Config.DB_HOST}:{Config.DB_PORT}")
    print(f"  - Database Name:   {Config.DB_NAME}")
    print(f"  - User:            {Config.DB_USER}")
    print("-" * 70)
    
    try:
        init_database()
        print("\n" + "=" * 70)
        print(f"SUCCESS: Database initialization completed using engine [{get_active_engine()}].")
        print("Created Tables:")
        print("  - users (Admin & Cashier accounts)")
        print("  - categories (Gift shop product classifications)")
        print("  - products (Catalog items, prices, barcodes)")
        print("  - inventory & inventory_movements (Stock monitoring & audit logs)")
        print("  - sales, sale_items & payments (POS transaction architecture)")
        print("\nCreated Indexes:")
        print("  - idx_products_name")
        print("  - idx_products_barcode")
        print("  - idx_products_category_id")
        print("  - idx_sales_created_at")
        print("  - idx_products_active_stock")
        print("  - idx_sale_items_sale_id")
        print("  - idx_users_username")
        print("\nDefault Accounts:")
        print("  1. Administrator -> Username: admin   | Password: admin123")
        print("  2. Cashier       -> Username: cashier | Password: cashier123")
        print("=" * 70)
    except Exception as e:
        print(f"\nERROR: Database initialization failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
