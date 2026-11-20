# Prosfora Gift Shop – Point of Sale & Inventory Management System

A clean, modern, student-friendly **Web-based Point of Sale (POS) and Inventory Management System** built completely from scratch for the **Prosfora Gift Shop**.

Developed for **Advanced Database Systems**, demonstrating **Relational Database Design**, **Role-Based Access Control (RBAC)**, **CRUD Operations**, **Point of Sale Operations**, **Receipt Printing**, **Sales Analytics**, **ACID Transaction Management & Concurrency Control**, and **Advanced SQL Indexing Strategies**.

---

## 🎨 Color Palette & Boutique Design Theme

The user interface follows the official boutique gift shop aesthetic:
- **Soft Pink:** `#E08CA0` (Accent, highlights, primary checkout buttons, brand gradients)
- **Light Pink:** `#E8D3D8` (Background fills, table headers, borders, subtle alert fills)
- **Soft Blue:** `#8BA9D4` (Transaction pills, cashier badges, barcode scan boxes)
- **Soft Purple:** `#5D428B` (Brand headings, executive navigation, grand totals, deep contrast)
- **Dark Text:** `#1E1E24` (High-contrast typography)

---

## 🏗️ Technology Stack

- **Frontend:**
  - **HTML5:** Semantic webpage structure rendered via Jinja2 templates.
  - **CSS3:** Custom stylesheet with CSS variables, modern responsive flexbox/grid layout, modal overlays, alert banners, and `@media print` thermal receipt styling.
  - **JavaScript (Vanilla ES6):** Instant search filtering, category sorting, image upload file previews, live shopping cart management, fast barcode scanner event handling, quick cash calculators, and AJAX transaction submission.
- **Backend:**
  - **Python 3.10+ / Flask 3.1+:** Clean routing, session security, password hashing, and role verification (`@login_required`, `@role_required`).
  - **psycopg2:** Native Python driver for PostgreSQL database communication with transactional support.
  - **Werkzeug:** Cryptographic password hashing (`generate_password_hash`, `check_password_hash`) and filename sanitization.
- **Database:**
  - **PostgreSQL 14+:** Normalized relational schema (`users`, `categories`, `products`, `inventory`, `inventory_movements`, `sales`, `sale_items`, `payments`).
  - **Seamless Development Fallback:** Automatic zero-config fallback mode (`prosfora_dev.db`) ensures students can develop and test immediately even if their local PostgreSQL service is offline.

---

## 📁 Integrated Project Structure

```text
Advance_DB/
├── app.py                     # Main Flask routing, controllers, RBAC decorators & ACID checkout API
├── config.py                  # System configuration, secret keys, upload & database settings
├── database.py                # Database connection manager, ACID transaction engine & seeder
├── schema.sql                 # Pure PostgreSQL DDL with 8 tables, constraints, foreign keys & indexes
├── init_db.py                 # CLI database reset and initialization utility
├── verify_indexes.py          # EXPLAIN / EXPLAIN ANALYZE index verification script
├── test_app.py                # Comprehensive automated test suite (18 test suites, all passing)
├── requirements.txt           # Python dependency requirements
├── .env.example               # Template environment configuration file
├── README.md                  # Complete technical manual and student guide
├── static/
│   ├── css/
│   │   └── style.css          # Boutique stylesheet, POS grid, cart, modals & @media print receipt rules
│   ├── js/
│   │   ├── main.js            # General UI interactions (mobile sidebar, alerts, modals)
│   │   ├── products.js        # Catalog search, stock filtering, barcode generation & photo preview
│   │   ├── categories.js      # Dynamic modal forms and category filtering
│   │   └── pos.js             # Live POS cart, barcode scanner listener, quick cash & AJAX checkout
│   └── uploads/               # Store directory for uploaded product showcase photos
└── templates/
    ├── base.html              # Master layout with sidebar navigation & top status bar
    ├── auth/
    │   ├── login.html         # User login screen with demo credentials box
    │   └── register.html      # Account creation form with role selection
    ├── dashboard/
    │   └── index.html         # Executive metrics, low-stock alerts, & recent sales
    ├── products/
    │   ├── index.html         # Product catalog table with filters & status badges
    │   ├── add.html           # Add product form (photo upload, barcode, prices, stock)
    │   └── edit.html          # Edit product form with current image display
    ├── categories/
    │   └── index.html         # Category list, product counts, add/edit modals
    ├── users/
    │   └── index.html         # Admin user management & account status toggling
    ├── pos/
    │   └── index.html         # Full interactive POS terminal (cart, scanner, quick cash, receipt modal)
    ├── receipt/
    │   └── view.html          # Standalone printable thermal receipt view with auto-print
    ├── sales/
    │   └── index.html         # Sales transactions history with invoice search & date filters
    ├── inventory/
    │   └── index.html         # Stock level monitoring, stock-in/out adjustment modals & movement audit trail
    ├── reports/
    │   └── index.html         # Executive Analytics (daily, weekly, monthly, best-sellers & CSV export)
    └── errors/
        ├── 403.html           # 403 Forbidden access denied template
        ├── 404.html           # 404 Not Found template
        └── 500.html           # 500 Server Error template
```

---

## 🔒 Advanced Database Systems Integration: Transaction Management and ACID

In accordance with the lecture on **Transaction Management and Concurrency Control**, checkout operations are executed as an **atomic PostgreSQL transaction** in `database.py` (`process_checkout_transaction`):

### The 4 ACID Properties Demonstrated:
1. **Atomicity (All-or-Nothing):**
   - Checkout consists of 8 distinct database actions: validating stock, verifying cash, writing sales header, inserting line items, logging payments, updating product stock, updating inventory stock, and recording inventory movement audit entries.
   - If any step fails (e.g. cash is less than total due, stock is insufficient, or an unexpected network interruption occurs), `conn.rollback()` is executed immediately. No partial sale is saved, and no stock is deducted.
2. **Consistency (Preserving Invariants):**
   - Database checks (`CHECK (stock_quantity >= 0)`, `CHECK (amount_tendered >= 0)`) and foreign keys (`REFERENCES products(id)`, `REFERENCES sales(id)`) ensure that the database moves from one valid state to another valid state.
3. **Isolation (Concurrency Control & Row-Level Locking):**
   - To prevent race conditions and overselling during simultaneous cashier checkouts, PostgreSQL row-level locks are acquired:
     ```sql
     SELECT id, name, selling_price, stock_quantity, is_active
     FROM products
     WHERE id = %s
     FOR UPDATE;
     ```
   - This ensures that concurrent transactions attempting to purchase the same gift item wait until the active transaction commits or rolls back, guaranteeing accurate stock deduction.
4. **Durability (Committed Data Persists):**
   - Once `conn.commit()` succeeds, transaction logs are flushed to PostgreSQL's Write-Ahead Log (WAL) and stored persistently on disk.

---

## ⚡ Advanced Database Systems Integration: Indexing Strategies & EXPLAIN ANALYZE

PostgreSQL B-Tree indexes defined in `schema.sql`:

```sql
-- 1. Product title search
CREATE INDEX idx_products_name ON products(name);

-- 2. Barcode scanner instant lookup (O(log N))
CREATE INDEX idx_products_barcode ON products(barcode);

-- 3. Category foreign key relational JOIN
CREATE INDEX idx_products_category_id ON products(category_id);

-- 4. Sales transaction chronological filtering
CREATE INDEX idx_sales_created_at ON sales(created_at);

-- 5. Best-seller line item aggregations
CREATE INDEX idx_sale_items_product_id ON sale_items(product_id);
CREATE INDEX idx_sale_items_sale_id ON sale_items(sale_id);

-- 6. Inventory movement chronological audit trail
CREATE INDEX idx_inventory_movements_product_id ON inventory_movements(product_id);
CREATE INDEX idx_inventory_movements_created_at ON inventory_movements(created_at);
```

### Verification via `verify_indexes.py`:
Run `python verify_indexes.py` to inspect the query planner output showing:
- `SEARCH products USING INDEX ... (barcode=?)`
- `SEARCH sales USING INDEX idx_sales_created_at (created_at>? AND created_at<?)`
- `SEARCH inventory_movements USING INDEX idx_inventory_movements_product_id (product_id=?)`

---

## 🛡️ Threat Mitigation and Security Controls in SQL Operations (Pandallan Framework)

The Prosfora POS system directly incorporates the core security principles outlined in the **Advanced Database Systems Security Controls** framework:

### 1. External Threat Mitigation: SQL Injection (SQLi) Defense
- **The Threat:** Dynamic SQL queries constructed via raw string concatenation (`'SELECT * FROM Users WHERE Name = ''' || user_input || '''';`) allow malicious actors to inject arbitrary SQL statements (e.g., `' OR '1'='1`, `'; DROP TABLE products; --`).
- **Secure Defensive Implementation:**
  - **100% Parameterized Statements:** All database interactions in `database.py` and `app.py` use parameterized placeholders (`%s` in PostgreSQL / `?` in SQLite). User input is separated completely from SQL execution logic and treated exclusively as literal values.
  - **No Dynamic String Formatting:** `f-strings` and direct `.format()` calls are strictly forbidden in SQL execution strings.
  - **Search Query Protection:**
    ```python
    # Secure parameterized search:
    query_db("SELECT * FROM products WHERE name ILIKE %s;", (f"%{keyword}%",))
    ```

### 2. Internal Threat Mitigation: Principle of Least Privilege & Audited Stored Procedures
- **The Threat:** Direct table manipulation access granted to operational users allows unauthorized modifications, data leakage (e.g., password hashes), or accidental deletion of critical store data.
- **Secure Defensive Implementation:**
  - **Role-Based Privilege Segregation (`schema.sql`):**
    ```sql
    -- Revoke direct modification privileges on core operational tables
    REVOKE INSERT, UPDATE, DELETE ON users, products, categories, inventory, sales, sale_items, payments FROM prosfora_reporting_user;
    REVOKE SELECT ON users FROM prosfora_reporting_user; -- Protects password hashes
    ```
  - **Controlled Procedure-Based Execution:** Operational users and analytical reporting roles interact with the database exclusively through audited, pre-defined stored procedures and functions:
    ```sql
    -- Grant access exclusively to pre-defined, audited stored procedure
    GRANT EXECUTE ON PROCEDURE GenerateRegionalReport(TIMESTAMP, TIMESTAMP, VARCHAR) TO prosfora_reporting_user;
    GRANT EXECUTE ON FUNCTION ProcessSecureCheckout(VARCHAR, INT, NUMERIC, NUMERIC, NUMERIC, NUMERIC) TO prosfora_cashier_user;
    ```
  - **Decoupled Security Layer:** By decoupling execution privileges from underlying table structures (`sales`, `products`, `users`), sensitive datasets are shielded from unauthorized inspection, SQL tampering, and insider threats.

---

## 📱 Responsive & Cross-Device Engineering: "Fit On Any Device"

The Prosfora Gift Shop web system is built from the ground up to adapt fluidly to every physical device and screen resolution without requiring third-party CSS frameworks:

1. **Cashier Laptops & Standard Displays (1366×768, 1280×800):**
   - Automatically calculates POS height (`calc(100vh - 100px)`) to guarantee the product grid, barcode scanner, and checkout cart fit on one screen without outer page scrolling.
2. **Tablets & Touch Terminals (iPad, Surface, 1024×768):**
   - Collapses the sidebar into an off-canvas drawer with backdrop blur.
   - Converts the POS container into an ergonomic stacked view with touch-friendly controls.
3. **Smartphones & Mobile Handhelds (360px – 480px):**
   - Barcode scanner and search controls stack vertically.
   - Products format into a 2-column mobile card grid.
   - Touch targets for quantity buttons (`+`/`−`) and quick-cash buttons are expanded to $\ge 42\text{px}$ to prevent mis-clicks.
   - A floating **Mobile Order Bar** (`#posMobileCartBar`) appears when items are added to the cart, allowing cashiers to view items and proceed to payment with one tap.
   - Font sizes on form inputs are set to $16\text{px}$ on mobile devices to prevent iOS Safari auto-zoom distortions.
4. **Thermal Receipt Printers & Paper Printouts (`@media print`):**
   - Hides navigation bars, buttons, and headers, rendering only standard 80mm thermal receipts or clean A4 invoices.

---

## 👥 User Roles & Permissions

| Role | Username | Password | Access Privileges |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin` | `admin123` | Full Access: Executive Dashboard, Products, Categories, Stock Adjustments, User Management, Reports & Analytics, POS Terminal |
| **Cashier** | `cashier` | `cashier123` | POS Access: POS Terminal, Barcode Scanning, Cash Checkout, Sales History, Receipt Reprinting |

---

## 🚀 Setup & Execution Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Initialize Database & Seed Sample Records
```bash
python init_db.py
```

### 3. Verify Database Indexes
```bash
python verify_indexes.py
```

### 4. Run Automated Test Suite (18 Unit & Integration Tests)
```bash
python test_app.py
```

### 5. Start the Web Application
```bash
python app.py
```
Open your browser and navigate to:
```text
http://127.0.0.1:5000
```
