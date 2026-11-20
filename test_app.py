"""
Comprehensive Automated Test Suite for Prosfora Gift Shop POS (Part 1).
Validates authentication, role enforcement, dashboard metrics, product CRUD,
category CRUD, inventory tracking, and database indexing.
"""

import os
import unittest
from app import app
from database import init_database, query_db, execute_db

class ProsforaPOSPart1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepare database and test client."""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        cls.client = app.test_client()
        init_database()

    def login_as(self, username, password):
        """Helper to simulate user login."""
        return self.client.post('/login', data={
            'username': username,
            'password': password
        }, follow_redirects=True)

    def logout(self):
        """Helper to simulate logout."""
        return self.client.get('/logout', follow_redirects=True)

    # -------------------------------------------------------------------------
    # 1. Authentication & Role-Based Access Control Tests
    # -------------------------------------------------------------------------
    def test_01_login_admin_success(self):
        """Test admin login with valid credentials."""
        response = self.login_as('admin', 'admin123')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Executive Dashboard', response.data)
        self.logout()

    def test_02_login_cashier_success_and_role_redirect(self):
        """Test cashier login and ensure cashier is redirected to products or POS."""
        response = self.login_as('cashier', 'cashier123')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Product Catalog', response.data)
        self.logout()

    def test_03_login_invalid_password(self):
        """Test invalid credentials rejection."""
        response = self.login_as('admin', 'wrong_password')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid username or password', response.data)

    def test_04_cashier_forbidden_on_admin_pages(self):
        """Test that a Cashier cannot access Admin Dashboard or User Management."""
        self.login_as('cashier', 'cashier123')
        
        # Cashier trying to access Dashboard
        dash_resp = self.client.get('/dashboard')
        self.assertEqual(dash_resp.status_code, 403)
        self.assertIn(b'403 - Access Denied', dash_resp.data)

        # Cashier trying to access Users list
        users_resp = self.client.get('/users')
        self.assertEqual(users_resp.status_code, 403)

        # Cashier trying to access Categories list
        cats_resp = self.client.get('/categories')
        self.assertEqual(cats_resp.status_code, 403)
        
        self.logout()

    # -------------------------------------------------------------------------
    # 2. Dashboard Metrics Verification
    # -------------------------------------------------------------------------
    def test_05_admin_dashboard_metrics(self):
        """Verify the dashboard retrieves actual aggregated statistics from the DB."""
        self.login_as('admin', 'admin123')
        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        
        # Check that metrics elements exist
        self.assertIn(b'Total Sales', response.data)
        self.assertIn(b'Transactions', response.data)
        self.assertIn(b'Catalog Items', response.data)
        self.assertIn(b'Low Stock Alert', response.data)
        self.assertIn(b'Inventory Valuation', response.data)
        self.logout()

    # -------------------------------------------------------------------------
    # 3. Product Management CRUD Tests
    # -------------------------------------------------------------------------
    def test_06_product_crud_lifecycle(self):
        """Tests complete Product CRUD cycle: Create, Read, Update, Status Toggle, Delete."""
        self.login_as('admin', 'admin123')

        # Step A: Create Product
        new_barcode = "TEST-BARCODE-999"
        add_resp = self.client.post('/products/add', data={
            'name': 'Test Artisanal Teacup',
            'barcode': new_barcode,
            'category_id': 1,
            'cost_price': '120.00',
            'selling_price': '250.00',
            'stock_quantity': '15',
            'min_stock_level': '4',
            'description': 'Automated test teacup item',
            'is_active': '1'
        }, follow_redirects=True)
        self.assertEqual(add_resp.status_code, 200)
        self.assertIn(b'Test Artisanal Teacup', add_resp.data)

        # Verify DB entry
        prod = query_db("SELECT * FROM products WHERE barcode = %s;", (new_barcode,), one=True)
        self.assertIsNotNone(prod)
        prod_id = prod['id']
        self.assertEqual(float(prod['selling_price']), 250.00)

        # Verify Inventory & Movement record was created
        inv = query_db("SELECT * FROM inventory WHERE product_id = %s;", (prod_id,), one=True)
        self.assertIsNotNone(inv)
        self.assertEqual(inv['current_stock'], 15)

        # Step B: Read Product Edit Page
        edit_page = self.client.get(f'/products/edit/{prod_id}')
        self.assertEqual(edit_page.status_code, 200)
        self.assertIn(b'Test Artisanal Teacup', edit_page.data)

        # Step C: Update Product
        update_resp = self.client.post(f'/products/edit/{prod_id}', data={
            'name': 'Test Artisanal Teacup (Premium Edition)',
            'barcode': new_barcode,
            'category_id': 1,
            'cost_price': '140.00',
            'selling_price': '300.00',
            'stock_quantity': '20',  # Restocked by +5
            'min_stock_level': '5',
            'description': 'Updated description',
            'is_active': '1'
        }, follow_redirects=True)
        self.assertEqual(update_resp.status_code, 200)
        self.assertIn(b'Test Artisanal Teacup (Premium Edition)', update_resp.data)

        # Verify stock and price updated
        updated_prod = query_db("SELECT * FROM products WHERE id = %s;", (prod_id,), one=True)
        self.assertEqual(float(updated_prod['selling_price']), 300.00)
        self.assertEqual(updated_prod['stock_quantity'], 20)

        # Step D: Toggle Status
        toggle_resp = self.client.post(f'/products/toggle-status/{prod_id}', follow_redirects=True)
        self.assertEqual(toggle_resp.status_code, 200)
        toggled_prod = query_db("SELECT is_active FROM products WHERE id = %s;", (prod_id,), one=True)
        self.assertFalse(toggled_prod['is_active'])

        # Step E: Delete Product
        del_resp = self.client.post(f'/products/delete/{prod_id}', follow_redirects=True)
        self.assertEqual(del_resp.status_code, 200)
        deleted_prod = query_db("SELECT id FROM products WHERE id = %s;", (prod_id,), one=True)
        self.assertIsNone(deleted_prod)

        self.logout()

    # -------------------------------------------------------------------------
    # 4. Category Management CRUD Tests
    # -------------------------------------------------------------------------
    def test_07_category_crud_lifecycle(self):
        """Tests complete Category CRUD operations."""
        self.login_as('admin', 'admin123')

        # Step A: Add Category
        cat_name = "Holiday Gift Boxes"
        add_resp = self.client.post('/categories/add', data={
            'name': cat_name,
            'description': 'Festive gift packaging and seasonal gift boxes',
            'is_active': '1'
        }, follow_redirects=True)
        self.assertEqual(add_resp.status_code, 200)
        self.assertIn(b'Holiday Gift Boxes', add_resp.data)

        cat = query_db("SELECT * FROM categories WHERE name = %s;", (cat_name,), one=True)
        self.assertIsNotNone(cat)
        cat_id = cat['id']

        # Step B: Edit Category
        updated_name = "Luxury Holiday Gift Sets"
        edit_resp = self.client.post(f'/categories/edit/{cat_id}', data={
            'name': updated_name,
            'description': 'Updated festive description',
            'is_active': '1'
        }, follow_redirects=True)
        self.assertEqual(edit_resp.status_code, 200)
        self.assertIn(b'Luxury Holiday Gift Sets', edit_resp.data)

        # Step C: Delete Category
        del_resp = self.client.post(f'/categories/delete/{cat_id}', follow_redirects=True)
        self.assertEqual(del_resp.status_code, 200)
        deleted_cat = query_db("SELECT id FROM categories WHERE id = %s;", (cat_id,), one=True)
        self.assertIsNone(deleted_cat)

        self.logout()

    # -------------------------------------------------------------------------
    # 5. User Account Management Tests
    # -------------------------------------------------------------------------
    def test_08_admin_creates_new_user(self):
        """Admin creates a new cashier account and toggles status."""
        self.login_as('admin', 'admin123')
        
        new_username = "test_cashier_2"
        create_resp = self.client.post('/users/create', data={
            'full_name': 'Test Cashier Two',
            'username': new_username,
            'email': 'cashier2@prosfora.com',
            'role': 'cashier',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(create_resp.status_code, 200)
        self.assertIn(b'Test Cashier Two', create_resp.data)

        user = query_db("SELECT * FROM users WHERE username = %s;", (new_username,), one=True)
        self.assertIsNotNone(user)
        self.assertEqual(user['role'], 'cashier')

        # Clean up
        execute_db("DELETE FROM users WHERE username = %s;", (new_username,))
        self.logout()

    # -------------------------------------------------------------------------
    # 6. Database Indexing Verification
    # -------------------------------------------------------------------------
    def test_09_database_indexes_exist(self):
        """Verifies that schema.sql defines all required indexes."""
        with open('schema.sql', 'r', encoding='utf-8') as f:
            sql_text = f.read()

        required_indexes = [
            'idx_products_name',
            'idx_products_barcode',
            'idx_products_category_id',
            'idx_sales_created_at'
        ]

        for idx in required_indexes:
            self.assertIn(idx, sql_text, f"Index {idx} is missing from schema.sql!")

    # -------------------------------------------------------------------------
    # 7. PART 2 TESTS: POS Checkout & ACID Transaction Management
    # -------------------------------------------------------------------------
    def test_10_pos_interface_accessible(self):
        """Test that POS page loads with products for cashiers."""
        self.login_as('cashier', 'cashier123')
        resp = self.client.get('/pos')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Point of Sale Terminal', resp.data)
        self.assertIn(b'Current Order', resp.data)
        self.logout()

    def test_11_checkout_successful_atomic_transaction(self):
        """
        Tests ACID checkout:
        - Validates stock deduction
        - Verifies sales record, sale_items, payments, and inventory_movements
        - Verifies change calculation
        """
        self.login_as('cashier', 'cashier123')

        # Get an active product with stock
        prod = query_db("SELECT id, name, selling_price, stock_quantity FROM products WHERE is_active = TRUE AND stock_quantity >= 5 LIMIT 1;", one=True)
        self.assertIsNotNone(prod)
        prod_id = prod['id']
        initial_stock = prod['stock_quantity']
        unit_price = float(prod['selling_price'])
        buy_qty = 2

        subtotal = unit_price * buy_qty
        tax = round(subtotal * 0.12, 2)
        total_due = round(subtotal + tax, 2)
        tendered = total_due + 100.00
        expected_change = 100.00

        # Perform Checkout POST
        checkout_resp = self.client.post('/pos/checkout', json={
            'items': [{'product_id': prod_id, 'quantity': buy_qty}],
            'amount_tendered': tendered,
            'discount_amount': 0.0,
            'payment_method': 'cash'
        })

        self.assertEqual(checkout_resp.status_code, 200)
        data = checkout_resp.get_json()
        self.assertTrue(data['success'])
        receipt = data['receipt']
        self.assertEqual(receipt['total_amount'], total_due)
        self.assertEqual(receipt['amount_tendered'], tendered)
        self.assertEqual(receipt['change_amount'], expected_change)
        sale_id = receipt['sale_id']

        # ACID Consistency & Durability: Check database state directly
        # 1. Product stock deducted
        updated_prod = query_db("SELECT stock_quantity FROM products WHERE id = %s;", (prod_id,), one=True)
        self.assertEqual(updated_prod['stock_quantity'], initial_stock - buy_qty)

        # 2. Inventory record updated
        inv = query_db("SELECT current_stock FROM inventory WHERE product_id = %s;", (prod_id,), one=True)
        self.assertEqual(inv['current_stock'], initial_stock - buy_qty)

        # 3. Inventory movement audit record inserted
        mov = query_db("SELECT * FROM inventory_movements WHERE product_id = %s ORDER BY id DESC LIMIT 1;", (prod_id,), one=True)
        self.assertEqual(mov['movement_type'], 'out')
        self.assertEqual(mov['quantity'], buy_qty)
        self.assertIn(receipt['invoice_number'], mov['reference_note'])

        # 4. Sale items inserted
        item_row = query_db("SELECT * FROM sale_items WHERE sale_id = %s;", (sale_id,), one=True)
        self.assertEqual(item_row['product_id'], prod_id)
        self.assertEqual(item_row['quantity'], buy_qty)

        # 5. Payment record inserted
        pmt = query_db("SELECT * FROM payments WHERE sale_id = %s;", (sale_id,), one=True)
        self.assertEqual(float(pmt['amount_tendered']), tendered)
        self.assertEqual(float(pmt['change_amount']), expected_change)

        self.logout()

    def test_12_checkout_insufficient_payment_rollback(self):
        """
        Tests ACID Atomicity: If customer tenders less than total amount,
        the transaction must fail and ROLLBACK (zero inventory change, zero sale recorded).
        """
        self.login_as('cashier', 'cashier123')

        prod = query_db("SELECT id, name, selling_price, stock_quantity FROM products WHERE is_active = TRUE AND stock_quantity >= 5 LIMIT 1;", one=True)
        prod_id = prod['id']
        initial_stock = prod['stock_quantity']
        sales_count_before = query_db("SELECT COUNT(*) as c FROM sales;", one=True)['c']

        # Attempt to checkout with insufficient cash (₱10 when total is much higher)
        checkout_resp = self.client.post('/pos/checkout', json={
            'items': [{'product_id': prod_id, 'quantity': 1}],
            'amount_tendered': 10.00,  # Insufficient
            'discount_amount': 0.0,
            'payment_method': 'cash'
        })

        self.assertEqual(checkout_resp.status_code, 400)
        data = checkout_resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('Insufficient payment', data['error'])

        # Verify no stock was deducted
        prod_after = query_db("SELECT stock_quantity FROM products WHERE id = %s;", (prod_id,), one=True)
        self.assertEqual(prod_after['stock_quantity'], initial_stock)

        # Verify no incomplete sale record was written
        sales_count_after = query_db("SELECT COUNT(*) as c FROM sales;", one=True)['c']
        self.assertEqual(sales_count_before, sales_count_after)

        self.logout()

    def test_13_checkout_insufficient_stock_rollback(self):
        """
        Tests ACID Atomicity: Attempting to buy more than available stock
        must trigger a rollback and prevent overselling.
        """
        self.login_as('cashier', 'cashier123')

        prod = query_db("SELECT id, stock_quantity FROM products WHERE is_active = TRUE LIMIT 1;", one=True)
        prod_id = prod['id']
        current_stock = prod['stock_quantity']

        # Request more units than available in stock
        checkout_resp = self.client.post('/pos/checkout', json={
            'items': [{'product_id': prod_id, 'quantity': current_stock + 100}],
            'amount_tendered': 100000.00,
            'discount_amount': 0.0,
            'payment_method': 'cash'
        })

        self.assertEqual(checkout_resp.status_code, 400)
        data = checkout_resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('Insufficient stock', data['error'])

        # Verify stock remains unchanged
        prod_after = query_db("SELECT stock_quantity FROM products WHERE id = %s;", (prod_id,), one=True)
        self.assertEqual(prod_after['stock_quantity'], current_stock)

        self.logout()

    def test_14_checkout_multiple_products_atomic(self):
        """Tests purchasing multiple distinct products in one transaction."""
        self.login_as('cashier', 'cashier123')

        prods = query_db("SELECT id, selling_price, stock_quantity FROM products WHERE is_active = TRUE AND stock_quantity >= 5 LIMIT 2;")
        self.assertGreaterEqual(len(prods), 2)
        p1, p2 = prods[0], prods[1]

        checkout_resp = self.client.post('/pos/checkout', json={
            'items': [
                {'product_id': p1['id'], 'quantity': 1},
                {'product_id': p2['id'], 'quantity': 2}
            ],
            'amount_tendered': 5000.00,
            'discount_amount': 50.00,
            'payment_method': 'cash'
        })

        self.assertEqual(checkout_resp.status_code, 200)
        data = checkout_resp.get_json()
        self.assertTrue(data['success'])
        receipt = data['receipt']
        self.assertEqual(receipt['discount_amount'], 50.00)

        # Verify line items count
        sale_items = query_db("SELECT * FROM sale_items WHERE sale_id = %s;", (receipt['sale_id'],))
        self.assertEqual(len(sale_items), 2)

        self.logout()

    def test_15_receipt_view_and_reprint(self):
        """Verifies receipt viewing and reprint functionality."""
        self.login_as('cashier', 'cashier123')

        # Fetch latest sale
        sale = query_db("SELECT id, invoice_number FROM sales ORDER BY id DESC LIMIT 1;", one=True)
        self.assertIsNotNone(sale)

        # 1. View Receipt Page
        resp = self.client.get(f"/receipt/{sale['id']}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(bytes(sale['invoice_number'], 'utf-8'), resp.data)
        self.assertIn(b'PROSFORA GIFT SHOP', resp.data)

        # 2. Print Receipt Page
        print_resp = self.client.get(f"/receipt/{sale['id']}/print")
        self.assertEqual(print_resp.status_code, 200)
        self.assertIn(b'window.print()', print_resp.data)

        self.logout()

    def test_16_stock_adjustment_operations(self):
        """Tests admin stock-in, stock-out, and audit adjustment."""
        self.login_as('admin', 'admin123')

        prod = query_db("SELECT id, stock_quantity FROM products LIMIT 1;", one=True)
        prod_id = prod['id']
        start_stock = prod['stock_quantity']

        # Test Stock-In (+10)
        in_resp = self.client.post('/inventory/adjust', data={
            'product_id': prod_id,
            'movement_type': 'in',
            'quantity': '10',
            'notes': 'Test Supplier Restock PO-101'
        }, follow_redirects=True)
        self.assertEqual(in_resp.status_code, 200)
        after_in = query_db("SELECT stock_quantity FROM products WHERE id = %s;", (prod_id,), one=True)
        self.assertEqual(after_in['stock_quantity'], start_stock + 10)

        # Test Stock-Out (-5)
        out_resp = self.client.post('/inventory/adjust', data={
            'product_id': prod_id,
            'movement_type': 'out',
            'quantity': '5',
            'notes': 'Damaged display unit'
        }, follow_redirects=True)
        self.assertEqual(out_resp.status_code, 200)
        after_out = query_db("SELECT stock_quantity FROM products WHERE id = %s;", (prod_id,), one=True)
        self.assertEqual(after_out['stock_quantity'], start_stock + 5)

        self.logout()

    def test_17_sales_history_and_date_filtering(self):
        """Tests sales history retrieval and search filters."""
        self.login_as('cashier', 'cashier123')

        # Get existing sale
        sale = query_db("SELECT invoice_number FROM sales LIMIT 1;", one=True)
        self.assertIsNotNone(sale)
        inv = sale['invoice_number']

        # Filter by exact invoice
        filter_resp = self.client.get(f'/sales?invoice={inv}')
        self.assertEqual(filter_resp.status_code, 200)
        self.assertIn(bytes(inv, 'utf-8'), filter_resp.data)

        self.logout()

    def test_18_reports_and_analytics_access_and_export(self):
        """Tests reports generation (day, week, month) and CSV export."""
        self.login_as('admin', 'admin123')

        # 1. Month overview
        rep_month = self.client.get('/reports?period=month')
        self.assertEqual(rep_month.status_code, 200)
        self.assertIn(b'Reports & Business Analytics', rep_month.data)
        self.assertIn(b'Best-Selling Products', rep_month.data)

        # 2. Week overview
        rep_week = self.client.get('/reports?period=week')
        self.assertEqual(rep_week.status_code, 200)

        # 3. CSV Export
        csv_resp = self.client.get('/reports/export/sales.csv?period=month')
        self.assertEqual(csv_resp.status_code, 200)
        self.assertEqual(csv_resp.mimetype, 'text/csv')
        self.assertIn(b'Invoice Number', csv_resp.data)

        self.logout()

        # 4. Verify Cashier is forbidden on Reports
        self.login_as('cashier', 'cashier123')
        cashier_rep = self.client.get('/reports')
        self.assertEqual(cashier_rep.status_code, 403)
        self.logout()

if __name__ == '__main__':
    unittest.main()
