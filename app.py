"""
Prosfora Gift Shop - Point of Sale and Inventory Management System
Main Flask Application Controller
Implements Part 1: Foundation, User Roles, Dashboard, Product & Category CRUD, and Advanced Indexing.
"""

import os
import io
import csv
import uuid
import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for, flash, session, g, jsonify, Response
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from database import (
    get_db, query_db, execute_db, init_database, get_active_engine,
    process_checkout_transaction, record_inventory_adjustment, get_receipt_data,
    CheckoutError, InsufficientStockError, InsufficientPaymentError, ProductNotFoundError
)

# -----------------------------------------------------------------------------
# Application Setup & Initialization
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def allowed_file(filename):
    """Validates uploaded image file extensions."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# Auto-initialize database on application startup if needed
with app.app_context():
    try:
        # Check if users table exists; if not, initialize schema & seeds
        query_db("SELECT 1 FROM users LIMIT 1;")
    except Exception:
        init_database()


@app.before_request
def before_request():
    """Injects database engine status into the template context."""
    g.db_engine_name = get_active_engine()


# -----------------------------------------------------------------------------
# Authentication & Role-Based Access Control Decorators
# -----------------------------------------------------------------------------
def login_required(f):
    """Restricts view to authenticated users with an active session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please sign in to access the Prosfora POS system.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """Restricts view to users matching specific roles (e.g., 'admin', 'cashier')."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to continue.', 'warning')
                return redirect(url_for('login'))
            user_role = session.get('role')
            if user_role not in allowed_roles:
                return render_template('errors/403.html'), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# -----------------------------------------------------------------------------
# Authentication Routes (Login, Logout, Register)
# -----------------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Authenticates users via username/email and password."""
    if 'user_id' in session:
        return redirect(url_for('dashboard' if session.get('role') == 'admin' else 'products_list'))

    if request.method == 'POST':
        identifier = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not identifier or not password:
            flash('Please provide both username and password.', 'danger')
            return render_template('auth/login.html')

        # Parameterized query to look up user safely
        user = query_db(
            "SELECT * FROM users WHERE (username = %s OR email = %s);",
            (identifier, identifier),
            one=True
        )

        if user and check_password_hash(user['password_hash'], password):
            if not user.get('is_active', True):
                flash('This account has been deactivated. Please consult your store administrator.', 'danger')
                return render_template('auth/login.html')

            # Populate session
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']

            flash(f"Welcome back, {user['full_name']}! You are logged in as {user['role'].capitalize()}.", 'success')
            
            # Redirect by role
            next_url = request.args.get('next')
            if next_url:
                return redirect(next_url)
            return redirect(url_for('dashboard') if user['role'] == 'admin' else url_for('products_list'))
        else:
            flash('Invalid username or password. Please try again.', 'danger')

    return render_template('auth/login.html')


@app.route('/logout')
def logout():
    """Terminates user session and redirects to login."""
    session.clear()
    flash('You have been successfully logged out of Prosfora POS.', 'info')
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Self-registration for employees or staff members."""
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip().lower()
        email = request.form.get('email', '').strip().lower()
        role = request.form.get('role', 'cashier').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validations
        if not full_name or not username or not email or not password:
            flash('All fields marked with an asterisk are required.', 'danger')
            return render_template('auth/register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('auth/register.html')

        if role not in ('admin', 'cashier'):
            role = 'cashier'

        # Check existing user
        existing = query_db(
            "SELECT id FROM users WHERE username = %s OR email = %s;",
            (username, email),
            one=True
        )
        if existing:
            flash('A user with that username or email already exists.', 'danger')
            return render_template('auth/register.html')

        # Insert new user with hashed password
        hashed_pw = generate_password_hash(password)
        try:
            execute_db("""
                INSERT INTO users (username, email, password_hash, full_name, role, is_active)
                VALUES (%s, %s, %s, %s, %s, %s);
            """, (username, email, hashed_pw, full_name, role, True))
            flash(f"Account for '{username}' created successfully! You can now log in.", 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f"Database error during registration: {e}", 'danger')

    return render_template('auth/register.html')


# -----------------------------------------------------------------------------
# Dashboard Module
# -----------------------------------------------------------------------------
@app.route('/')
@app.route('/dashboard')
@login_required
@role_required('admin')
def dashboard():
    """
    Renders the executive admin dashboard.
    Retrieves live aggregations directly from PostgreSQL:
      - Total completed sales volume
      - Transaction order count
      - Total active products
      - Low-stock inventory alert count
      - Total cost inventory valuation
      - Recent transactions with cashier details
      - Category distribution summaries
    """
    # 1. Total Sales Amount
    sales_stat = query_db("""
        SELECT COALESCE(SUM(total_amount), 0.0) as total_sales,
               COUNT(id) as total_transactions
        FROM sales
        WHERE payment_status = 'completed';
    """, one=True)
    total_sales = sales_stat['total_sales'] if sales_stat else 0.0
    total_transactions = sales_stat['total_transactions'] if sales_stat else 0

    # 2. Total Catalog Products & Valuation
    prod_stat = query_db("""
        SELECT COUNT(id) as total_products,
               COALESCE(SUM(stock_quantity * cost_price), 0.0) as inventory_value
        FROM products
        WHERE is_active = TRUE;
    """, one=True)
    total_products = prod_stat['total_products'] if prod_stat else 0
    inventory_value = prod_stat['inventory_value'] if prod_stat else 0.0

    # 3. Total Categories
    cat_stat = query_db("SELECT COUNT(id) as total_categories FROM categories WHERE is_active = TRUE;", one=True)
    total_categories = cat_stat['total_categories'] if cat_stat else 0

    # 4. Low-Stock Alert Count
    low_stock_stat = query_db("""
        SELECT COUNT(id) as low_count
        FROM products
        WHERE stock_quantity <= min_stock_level AND is_active = TRUE;
    """, one=True)
    low_stock_count = low_stock_stat['low_count'] if low_stock_stat else 0

    # 5. Low-Stock Items List for Restock Box
    low_stock_items = query_db("""
        SELECT id, name, stock_quantity, min_stock_level
        FROM products
        WHERE stock_quantity <= min_stock_level AND is_active = TRUE
        ORDER BY stock_quantity ASC
        LIMIT 5;
    """)

    # 6. Recent Sales with Cashier Name and Payment Method
    recent_sales = query_db("""
        SELECT s.id, s.invoice_number, s.total_amount, s.payment_status, s.created_at,
               u.full_name as cashier_name,
               p.payment_method
        FROM sales s
        LEFT JOIN users u ON s.user_id = u.id
        LEFT JOIN payments p ON p.sale_id = s.id
        ORDER BY s.created_at DESC
        LIMIT 5;
    """)

    # 7. Category Inventory Summary
    category_summary = query_db("""
        SELECT c.id, c.name,
               COUNT(p.id) as product_count,
               COALESCE(SUM(p.stock_quantity), 0) as total_units,
               COALESCE(SUM(p.stock_quantity * p.cost_price), 0.0) as category_value
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.id AND p.is_active = TRUE
        WHERE c.is_active = TRUE
        GROUP BY c.id, c.name
        ORDER BY product_count DESC;
    """)

    metrics = {
        'total_sales': float(total_sales),
        'total_transactions': int(total_transactions),
        'total_products': int(total_products),
        'total_categories': int(total_categories),
        'low_stock_count': int(low_stock_count),
        'inventory_value': float(inventory_value)
    }

    return render_template(
        'dashboard/index.html',
        active_page='dashboard',
        metrics=metrics,
        recent_sales=recent_sales,
        low_stock_items=low_stock_items,
        category_summary=category_summary
    )


# -----------------------------------------------------------------------------
# Product Management Module (CRUD)
# -----------------------------------------------------------------------------
@app.route('/products')
@login_required
def products_list():
    """
    Displays the catalog of gift shop products.
    Includes category name JOIN, stock status, barcode, and pricing.
    """
    category_filter = request.args.get('category', '').strip()
    search_query = request.args.get('search', '').strip()

    # Base query utilizing idx_products_category_id and idx_products_name
    query = """
        SELECT p.*, c.name as category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        ORDER BY p.id DESC;
    """
    products = query_db(query)
    categories = query_db("SELECT id, name FROM categories WHERE is_active = TRUE ORDER BY name ASC;")

    return render_template(
        'products/index.html',
        active_page='products',
        products=products,
        categories=categories
    )


@app.route('/products/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def product_add():
    """Creates a new gift shop product, registers inventory, and uploads image."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        barcode = request.form.get('barcode', '').strip() or None
        description = request.form.get('description', '').strip()
        category_id = request.form.get('category_id') or None
        cost_price = request.form.get('cost_price', '0').strip()
        selling_price = request.form.get('selling_price', '0').strip()
        stock_quantity = request.form.get('stock_quantity', '0').strip()
        min_stock_level = request.form.get('min_stock_level', '5').strip()
        is_active = bool(int(request.form.get('is_active', '1')))

        # Basic validations
        if not name:
            flash('Product name is required.', 'danger')
            return redirect(url_for('product_add'))

        try:
            cost_val = float(cost_price)
            selling_val = float(selling_price)
            stock_val = int(stock_quantity)
            min_stock_val = int(min_stock_level)
        except ValueError:
            flash('Invalid numeric format for price or stock quantity.', 'danger')
            return redirect(url_for('product_add'))

        # Check unique barcode if provided
        if barcode:
            dup_barcode = query_db("SELECT id FROM products WHERE barcode = %s;", (barcode,), one=True)
            if dup_barcode:
                flash(f"Barcode '{barcode}' is already assigned to another product.", 'danger')
                return redirect(url_for('product_add'))

        # Handle image upload
        image_relative_path = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                ext = file.filename.rsplit('.', 1)[1].lower()
                unique_filename = f"prod_{uuid.uuid4().hex[:12]}.{ext}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(save_path)
                image_relative_path = f"uploads/{unique_filename}"

        try:
            # 1. Insert product record
            product_id = execute_db("""
                INSERT INTO products (
                    barcode, name, description, category_id,
                    cost_price, selling_price, stock_quantity, min_stock_level,
                    image_url, is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                barcode, name, description, category_id,
                cost_val, selling_val, stock_val, min_stock_val,
                image_relative_path, is_active
            ), return_id=True)

            # 2. Maintain normalized inventory table
            execute_db("""
                INSERT INTO inventory (product_id, current_stock, reorder_level, last_restocked_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP);
            """, (product_id, stock_val, min_stock_val))

            # 3. Record initial stock movement audit
            execute_db("""
                INSERT INTO inventory_movements (product_id, movement_type, quantity, reference_note, performed_by)
                VALUES (%s, %s, %s, %s, %s);
            """, (product_id, 'in', stock_val, 'Initial catalog stock registration', session.get('user_id')))

            flash(f"Product '{name}' added successfully!", 'success')
            return redirect(url_for('products_list'))

        except Exception as e:
            flash(f"Error saving product: {e}", 'danger')
            return redirect(url_for('product_add'))

    categories = query_db("SELECT id, name FROM categories WHERE is_active = TRUE ORDER BY name ASC;")
    return render_template('products/add.html', active_page='products', categories=categories)


@app.route('/products/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def product_edit(id):
    """Updates an existing product's details, pricing, and stock."""
    product = query_db("SELECT * FROM products WHERE id = %s;", (id,), one=True)
    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('products_list'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        barcode = request.form.get('barcode', '').strip() or None
        description = request.form.get('description', '').strip()
        category_id = request.form.get('category_id') or None
        cost_price = request.form.get('cost_price', '0').strip()
        selling_price = request.form.get('selling_price', '0').strip()
        stock_quantity = request.form.get('stock_quantity', '0').strip()
        min_stock_level = request.form.get('min_stock_level', '5').strip()
        is_active = bool(int(request.form.get('is_active', '1')))

        if not name:
            flash('Product name is required.', 'danger')
            return redirect(url_for('product_edit', id=id))

        try:
            cost_val = float(cost_price)
            selling_val = float(selling_price)
            new_stock = int(stock_quantity)
            min_stock_val = int(min_stock_level)
        except ValueError:
            flash('Invalid numeric format for price or stock quantity.', 'danger')
            return redirect(url_for('product_edit', id=id))

        # Check unique barcode conflict
        if barcode:
            dup = query_db("SELECT id FROM products WHERE barcode = %s AND id != %s;", (barcode, id), one=True)
            if dup:
                flash(f"Barcode '{barcode}' is already used by another product.", 'danger')
                return redirect(url_for('product_edit', id=id))

        # Handle optional new image replacement
        image_relative_path = product['image_url']
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                ext = file.filename.rsplit('.', 1)[1].lower()
                unique_filename = f"prod_{uuid.uuid4().hex[:12]}.{ext}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(save_path)
                image_relative_path = f"uploads/{unique_filename}"

        try:
            old_stock = product['stock_quantity']
            stock_diff = new_stock - old_stock

            # 1. Update product row
            execute_db("""
                UPDATE products SET
                    name = %s,
                    barcode = %s,
                    description = %s,
                    category_id = %s,
                    cost_price = %s,
                    selling_price = %s,
                    stock_quantity = %s,
                    min_stock_level = %s,
                    image_url = %s,
                    is_active = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (
                name, barcode, description, category_id,
                cost_val, selling_val, new_stock, min_stock_val,
                image_relative_path, is_active, id
            ))

            # 2. Update inventory record
            execute_db("""
                UPDATE inventory SET
                    current_stock = %s,
                    reorder_level = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE product_id = %s;
            """, (new_stock, min_stock_val, id))

            # 3. Log stock adjustment movement if quantity changed
            if stock_diff != 0:
                movement_type = 'in' if stock_diff > 0 else 'out'
                execute_db("""
                    INSERT INTO inventory_movements (product_id, movement_type, quantity, reference_note, performed_by)
                    VALUES (%s, %s, %s, %s, %s);
                """, (id, movement_type, abs(stock_diff), f'Manual stock adjustment ({stock_diff:+d})', session.get('user_id')))

            flash(f"Product '{name}' updated successfully!", 'success')
            return redirect(url_for('products_list'))

        except Exception as e:
            flash(f"Error updating product: {e}", 'danger')
            return redirect(url_for('product_edit', id=id))

    categories = query_db("SELECT id, name FROM categories WHERE is_active = TRUE ORDER BY name ASC;")
    return render_template('products/edit.html', active_page='products', product=product, categories=categories)


@app.route('/products/delete/<int:id>', methods=['POST'])
@login_required
@role_required('admin')
def product_delete(id):
    """Deletes or archives a product."""
    product = query_db("SELECT id, name FROM products WHERE id = %s;", (id,), one=True)
    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('products_list'))

    # Check if product is referenced in sale_items
    has_sales = query_db("SELECT id FROM sale_items WHERE product_id = %s LIMIT 1;", (id,), one=True)
    if has_sales:
        # Instead of breaking relational integrity, deactivate the product
        execute_db("UPDATE products SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (id,))
        flash(f"Product '{product['name']}' has sales history, so it was deactivated instead of deleted to protect financial logs.", 'info')
    else:
        execute_db("DELETE FROM products WHERE id = %s;", (id,))
        flash(f"Product '{product['name']}' deleted permanently.", 'success')

    return redirect(url_for('products_list'))


@app.route('/products/toggle-status/<int:id>', methods=['POST'])
@login_required
@role_required('admin')
def product_toggle_status(id):
    """Toggles active/inactive state of a product."""
    product = query_db("SELECT id, name, is_active FROM products WHERE id = %s;", (id,), one=True)
    if product:
        new_state = not product['is_active']
        execute_db("UPDATE products SET is_active = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (new_state, id))
        action = "activated" if new_state else "deactivated"
        flash(f"Product '{product['name']}' is now {action}.", 'success')
    return redirect(url_for('products_list'))


# -----------------------------------------------------------------------------
# Category Management Module (CRUD)
# -----------------------------------------------------------------------------
@app.route('/categories')
@login_required
@role_required('admin')
def categories_list():
    """Lists all product categories with associated item counts."""
    categories = query_db("""
        SELECT c.*, COUNT(p.id) as product_count
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.id
        GROUP BY c.id
        ORDER BY c.name ASC;
    """)
    return render_template('categories/index.html', active_page='categories', categories=categories)


@app.route('/categories/add', methods=['POST'])
@login_required
@role_required('admin')
def category_add():
    """Creates a new product category."""
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    is_active = bool(request.form.get('is_active'))

    if not name:
        flash('Category name is required.', 'danger')
        return redirect(url_for('categories_list'))

    # Check duplicate
    dup = query_db("SELECT id FROM categories WHERE LOWER(name) = LOWER(%s);", (name,), one=True)
    if dup:
        flash(f"A category named '{name}' already exists.", 'danger')
        return redirect(url_for('categories_list'))

    try:
        execute_db("""
            INSERT INTO categories (name, description, is_active)
            VALUES (%s, %s, %s);
        """, (name, description, is_active))
        flash(f"Category '{name}' created successfully!", 'success')
    except Exception as e:
        flash(f"Error creating category: {e}", 'danger')

    return redirect(url_for('categories_list'))


@app.route('/categories/edit/<int:id>', methods=['POST'])
@login_required
@role_required('admin')
def category_edit(id):
    """Updates category name, description, and status."""
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    is_active = bool(request.form.get('is_active'))

    if not name:
        flash('Category name cannot be empty.', 'danger')
        return redirect(url_for('categories_list'))

    # Check duplicate conflict
    dup = query_db("SELECT id FROM categories WHERE LOWER(name) = LOWER(%s) AND id != %s;", (name, id), one=True)
    if dup:
        flash(f"Another category named '{name}' already exists.", 'danger')
        return redirect(url_for('categories_list'))

    try:
        execute_db("""
            UPDATE categories SET
                name = %s,
                description = %s,
                is_active = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """, (name, description, is_active, id))
        flash(f"Category '{name}' updated successfully!", 'success')
    except Exception as e:
        flash(f"Error updating category: {e}", 'danger')

    return redirect(url_for('categories_list'))


@app.route('/categories/delete/<int:id>', methods=['POST'])
@login_required
@role_required('admin')
def category_delete(id):
    """Deletes a category and unlinks any assigned products safely."""
    cat = query_db("SELECT id, name FROM categories WHERE id = %s;", (id,), one=True)
    if not cat:
        flash('Category not found.', 'danger')
        return redirect(url_for('categories_list'))

    try:
        # Unlink products to avoid orphan foreign key errors
        execute_db("UPDATE products SET category_id = NULL WHERE category_id = %s;", (id,))
        # Delete category
        execute_db("DELETE FROM categories WHERE id = %s;", (id,))
        flash(f"Category '{cat['name']}' deleted successfully. Assigned products have been unlinked.", 'success')
    except Exception as e:
        flash(f"Error deleting category: {e}", 'danger')

    return redirect(url_for('categories_list'))


# -----------------------------------------------------------------------------
# User Account Management (Admin only)
# -----------------------------------------------------------------------------
@app.route('/users')
@login_required
@role_required('admin')
def users_list():
    """Lists system users and permissions."""
    users = query_db("SELECT id, username, email, full_name, role, is_active, created_at FROM users ORDER BY id ASC;")
    return render_template('users/index.html', active_page='users', users=users)


@app.route('/users/create', methods=['POST'])
@login_required
@role_required('admin')
def user_create():
    """Admin endpoint to create staff and cashier accounts."""
    full_name = request.form.get('full_name', '').strip()
    username = request.form.get('username', '').strip().lower()
    email = request.form.get('email', '').strip().lower()
    role = request.form.get('role', 'cashier').strip()
    password = request.form.get('password', '')

    if not full_name or not username or not email or not password:
        flash('All fields are required.', 'danger')
        return redirect(url_for('users_list'))

    # Check duplicate
    dup = query_db("SELECT id FROM users WHERE username = %s OR email = %s;", (username, email), one=True)
    if dup:
        flash('A user with that username or email already exists.', 'danger')
        return redirect(url_for('users_list'))

    hashed_pw = generate_password_hash(password)
    try:
        execute_db("""
            INSERT INTO users (username, email, password_hash, full_name, role, is_active)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (username, email, hashed_pw, full_name, role, True))
        flash(f"User account '{username}' created successfully as {role.capitalize()}.", 'success')
    except Exception as e:
        flash(f"Error creating user: {e}", 'danger')

    return redirect(url_for('users_list'))


@app.route('/users/toggle-status/<int:id>', methods=['POST'])
@login_required
@role_required('admin')
def user_toggle_status(id):
    """Enables or disables an employee account."""
    if id == session.get('user_id'):
        flash('You cannot disable your own active account.', 'warning')
        return redirect(url_for('users_list'))

    user = query_db("SELECT id, username, is_active FROM users WHERE id = %s;", (id,), one=True)
    if user:
        new_state = not user['is_active']
        execute_db("UPDATE users SET is_active = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (new_state, id))
        action = "activated" if new_state else "disabled"
        flash(f"User '{user['username']}' is now {action}.", 'success')

    return redirect(url_for('users_list'))


# -----------------------------------------------------------------------------
# Inventory & Movements Module
# -----------------------------------------------------------------------------
@app.route('/inventory')
@login_required
@role_required('admin')
def inventory_overview():
    """Displays stock levels, minimum reorder thresholds, and recent stock movement logs."""
    inventory_items = query_db("""
        SELECT i.*, p.name as product_name, p.cost_price, p.selling_price, c.name as category_name
        FROM inventory i
        JOIN products p ON i.product_id = p.id
        LEFT JOIN categories c ON p.category_id = c.id
        ORDER BY i.current_stock ASC;
    """)

    movements = query_db("""
        SELECT m.*, p.name as product_name, u.full_name as staff_name
        FROM inventory_movements m
        JOIN products p ON m.product_id = p.id
        LEFT JOIN users u ON m.performed_by = u.id
        ORDER BY m.created_at DESC
        LIMIT 25;
    """)

    total_units = sum(item['current_stock'] for item in inventory_items)
    total_val = sum(item['current_stock'] * float(item['cost_price']) for item in inventory_items)
    low_stock_count = sum(1 for item in inventory_items if item['current_stock'] <= item['reorder_level'])

    return render_template(
        'inventory/index.html',
        active_page='inventory',
        inventory_items=inventory_items,
        movements=movements,
        total_units=total_units,
        total_val=total_val,
        low_stock_count=low_stock_count
    )


@app.route('/inventory/adjust', methods=['POST'])
@login_required
@role_required('admin')
def inventory_adjust():
    """
    Records a stock-in, stock-out, or count adjustment within an ACID transaction.
    """
    product_id = request.form.get('product_id')
    movement_type = request.form.get('movement_type', 'in')
    quantity = request.form.get('quantity')
    notes = request.form.get('notes', '').strip()

    if not product_id or not quantity:
        flash('Product and quantity are required for stock adjustments.', 'danger')
        return redirect(url_for('inventory_overview'))

    try:
        new_level = record_inventory_adjustment(
            product_id=int(product_id),
            adjustment_type=movement_type,
            quantity=int(quantity),
            notes=notes,
            user_id=session.get('user_id')
        )
        flash(f"Stock successfully adjusted! New stock level: {new_level} units.", 'success')
    except Exception as e:
        flash(f"Stock adjustment failed: {e}", 'danger')

    return redirect(url_for('inventory_overview'))


# -----------------------------------------------------------------------------
# Point of Sale (POS) & Checkout Module (Part 2)
# -----------------------------------------------------------------------------
@app.route('/pos')
@app.route('/pos/terminal')
@login_required
def pos_terminal():
    """
    Interactive Point of Sale terminal interface for Cashiers and Admins.
    Displays available products, categories, barcode scanner listener, and cart.
    """
    products = query_db("""
        SELECT p.*, c.name as category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_active = TRUE AND p.stock_quantity > 0
        ORDER BY p.name ASC;
    """)

    categories = query_db("""
        SELECT DISTINCT c.id, c.name
        FROM categories c
        JOIN products p ON p.category_id = c.id
        WHERE c.is_active = TRUE AND p.is_active = TRUE AND p.stock_quantity > 0
        ORDER BY c.name ASC;
    """)

    return render_template('pos/index.html', active_page='pos', products=products, categories=categories)


@app.route('/pos/checkout', methods=['POST'])
@login_required
def pos_checkout():
    """
    ACID Transactional Checkout Endpoint.
    Validates cart items, verifies row-level stock locks, computes subtotals,
    records sales header, items, payment tender, deducts inventory, and commits atomically.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': 'Invalid JSON request payload.'}), 400

    items = data.get('items', [])
    amount_tendered = data.get('amount_tendered', 0.0)
    discount_amount = data.get('discount_amount', 0.0)
    payment_method = data.get('payment_method', 'cash')

    try:
        # Execute single ACID checkout transaction with row locking
        result = process_checkout_transaction(
            user_id=session.get('user_id'),
            items=items,
            amount_tendered=amount_tendered,
            payment_method=payment_method,
            discount_amount=discount_amount,
            tax_rate=0.12
        )

        # Retrieve updated stock levels for the cart items so frontend can refresh instantly
        updated_stocks = {}
        for it in items:
            p = query_db("SELECT id, stock_quantity FROM products WHERE id = %s;", (it['product_id'],), one=True)
            if p:
                updated_stocks[p['id']] = p['stock_quantity']

        # Include cashier display name in receipt
        result['cashier_name'] = session.get('full_name') or session.get('username')

        return jsonify({
            'success': True,
            'receipt': result,
            'updated_stocks': updated_stocks
        }), 200

    except InsufficientStockError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except InsufficientPaymentError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except ProductNotFoundError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except CheckoutError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f"Transaction failed and was rolled back: {str(e)}"}), 500


# -----------------------------------------------------------------------------
# Receipt Management Module
# -----------------------------------------------------------------------------
@app.route('/receipt/<int:sale_id>')
@login_required
def view_receipt(sale_id):
    """Renders the official customer receipt for viewing or reprinting."""
    sale_data = get_receipt_data(sale_id)
    if not sale_data:
        flash('Receipt record not found.', 'danger')
        return redirect(url_for('sales_history'))

    return render_template('receipt/view.html', sale=sale_data, auto_print=False)


@app.route('/receipt/<int:sale_id>/print')
@login_required
def print_receipt(sale_id):
    """Renders the official receipt with auto-print triggered on page load."""
    sale_data = get_receipt_data(sale_id)
    if not sale_data:
        flash('Receipt record not found.', 'danger')
        return redirect(url_for('sales_history'))

    return render_template('receipt/view.html', sale=sale_data, auto_print=True)


# -----------------------------------------------------------------------------
# Sales History Module
# -----------------------------------------------------------------------------
@app.route('/sales')
@login_required
def sales_history():
    """
    Displays completed sales transactions.
    Supports search by invoice number and filtering by date range.
    """
    invoice_filter = request.args.get('invoice', '').strip()
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()

    sql = """
        SELECT s.*, u.full_name as cashier_name,
               p.payment_method, p.amount_tendered, p.change_amount,
               COUNT(si.id) as items_count
        FROM sales s
        LEFT JOIN users u ON s.user_id = u.id
        LEFT JOIN payments p ON p.sale_id = s.id
        LEFT JOIN sale_items si ON si.sale_id = s.id
        WHERE 1=1
    """
    params = []

    if invoice_filter:
        sql += " AND s.invoice_number ILIKE %s"
        params.append(f"%{invoice_filter}%")

    if from_date:
        sql += " AND s.created_at >= %s"
        params.append(f"{from_date} 00:00:00")

    if to_date:
        sql += " AND s.created_at <= %s"
        params.append(f"{to_date} 23:59:59")

    sql += " GROUP BY s.id, u.full_name, p.payment_method, p.amount_tendered, p.change_amount ORDER BY s.created_at DESC;"

    sales = query_db(sql, params)
    total_revenue = sum(float(s['total_amount']) for s in sales)

    return render_template(
        'sales/index.html',
        active_page='sales',
        sales=sales,
        total_revenue=total_revenue
    )


# -----------------------------------------------------------------------------
# Reports & Analytics Module (Admin only)
# -----------------------------------------------------------------------------
@app.route('/reports')
@login_required
@role_required('admin')
def reports_overview():
    """
    Executive Sales and Inventory Analytics.
    Provides daily, weekly, monthly aggregations, best sellers, and visual distribution.
    """
    period = request.args.get('period', 'month').lower()
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')

    now = datetime.datetime.now()
    start_time = None
    end_time = now.strftime('%Y-%m-%d 23:59:59')
    period_label = "This Month"

    if from_date and to_date:
        start_time = f"{from_date} 00:00:00"
        end_time = f"{to_date} 23:59:59"
        period_label = f"{from_date} to {to_date}"
    elif period == 'today':
        start_time = now.strftime('%Y-%m-%d 00:00:00')
        period_label = "Today's"
    elif period == 'week':
        week_ago = now - datetime.timedelta(days=7)
        start_time = week_ago.strftime('%Y-%m-%d 00:00:00')
        period_label = "Past 7 Days"
    else: # default: month (past 30 days)
        month_ago = now - datetime.timedelta(days=30)
        start_time = month_ago.strftime('%Y-%m-%d 00:00:00')
        period_label = "Past 30 Days"

    # 1. Summary Metrics
    summary_sql = """
        SELECT COALESCE(SUM(s.total_amount), 0.0) as total_revenue,
               COUNT(s.id) as total_transactions,
               COALESCE(AVG(s.total_amount), 0.0) as avg_order_value,
               COALESCE(SUM(si.quantity), 0) as total_units_sold
        FROM sales s
        LEFT JOIN sale_items si ON si.sale_id = s.id
        WHERE s.payment_status = 'completed' AND s.created_at >= %s AND s.created_at <= %s;
    """
    summary = query_db(summary_sql, (start_time, end_time), one=True) or {}

    # 2. Best-Selling Products (Ranked by Units Sold and Revenue)
    best_sellers_sql = """
        SELECT p.id, p.name, p.barcode, c.name as category_name,
               COALESCE(SUM(si.quantity), 0) as units_sold,
               COALESCE(SUM(si.subtotal), 0.0) as total_revenue
        FROM products p
        JOIN sale_items si ON si.product_id = p.id
        JOIN sales s ON si.sale_id = s.id
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE s.payment_status = 'completed' AND s.created_at >= %s AND s.created_at <= %s
        GROUP BY p.id, p.name, p.barcode, c.name
        ORDER BY units_sold DESC, total_revenue DESC
        LIMIT 10;
    """
    best_sellers = query_db(best_sellers_sql, (start_time, end_time))

    # 3. Category Sales Share Breakdown
    category_sales_sql = """
        SELECT COALESCE(c.name, 'Uncategorized') as category_name,
               COALESCE(SUM(si.subtotal), 0.0) as cat_revenue,
               COALESCE(SUM(si.quantity), 0) as cat_units
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        JOIN products p ON si.product_id = p.id
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE s.payment_status = 'completed' AND s.created_at >= %s AND s.created_at <= %s
        GROUP BY c.name
        ORDER BY cat_revenue DESC;
    """
    category_sales = query_db(category_sales_sql, (start_time, end_time))

    # 4. Daily Sales Timeline
    daily_sql = """
        SELECT SUBSTR(s.created_at, 1, 10) as sale_day,
               COUNT(s.id) as tx_count,
               SUM(s.subtotal) as subtotal,
               SUM(s.tax_amount) as tax,
               SUM(s.total_amount) as total
        FROM sales s
        WHERE s.payment_status = 'completed' AND s.created_at >= %s AND s.created_at <= %s
        GROUP BY SUBSTR(s.created_at, 1, 10)
        ORDER BY sale_day DESC;
    """
    daily_records = query_db(daily_sql, (start_time, end_time))

    return render_template(
        'reports/index.html',
        active_page='reports',
        period=period,
        period_label=period_label,
        from_date=from_date,
        to_date=to_date,
        report_summary=summary,
        best_sellers=best_sellers,
        category_sales=category_sales,
        daily_records=daily_records
    )


@app.route('/reports/export/sales.csv')
@login_required
@role_required('admin')
def export_sales_csv():
    """Streams a CSV file of sales transactions for spreadsheet analysis."""
    period = request.args.get('period', 'month').lower()
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')

    now = datetime.datetime.now()
    start_time = None
    end_time = now.strftime('%Y-%m-%d 23:59:59')

    if from_date and to_date:
        start_time = f"{from_date} 00:00:00"
        end_time = f"{to_date} 23:59:59"
    elif period == 'today':
        start_time = now.strftime('%Y-%m-%d 00:00:00')
    elif period == 'week':
        start_time = (now - datetime.timedelta(days=7)).strftime('%Y-%m-%d 00:00:00')
    else:
        start_time = (now - datetime.timedelta(days=30)).strftime('%Y-%m-%d 00:00:00')

    sales = query_db("""
        SELECT s.invoice_number, s.created_at, u.full_name as cashier,
               s.subtotal, s.tax_amount, s.discount_amount, s.total_amount,
               p.payment_method, s.payment_status
        FROM sales s
        LEFT JOIN users u ON s.user_id = u.id
        LEFT JOIN payments p ON p.sale_id = s.id
        WHERE s.created_at >= %s AND s.created_at <= %s
        ORDER BY s.created_at DESC;
    """, (start_time, end_time))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Invoice Number', 'Transaction Date', 'Cashier',
        'Subtotal (PHP)', 'Tax (PHP)', 'Discount (PHP)',
        'Total (PHP)', 'Payment Method', 'Status'
    ])

    for row in sales:
        writer.writerow([
            row['invoice_number'],
            row['created_at'],
            row['cashier'] or 'Staff',
            f"{float(row['subtotal']):.2f}",
            f"{float(row['tax_amount']):.2f}",
            f"{float(row['discount_amount']):.2f}",
            f"{float(row['total_amount']):.2f}",
            (row['payment_method'] or 'Cash').upper(),
            row['payment_status'].capitalize()
        ])

    csv_data = output.getvalue()
    filename = f"prosfora_sales_report_{now.strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )


# -----------------------------------------------------------------------------
# HTTP Error Handlers
# -----------------------------------------------------------------------------
@app.errorhandler(403)
def forbidden_error(error):
    return render_template('errors/403.html'), 403


@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template('errors/500.html'), 500


# -----------------------------------------------------------------------------
# Application Execution Entry Point
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
