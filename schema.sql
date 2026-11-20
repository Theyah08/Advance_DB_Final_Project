DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS sale_items CASCADE;
DROP TABLE IF EXISTS sales CASCADE;
DROP TABLE IF EXISTS inventory_movements CASCADE;
DROP TABLE IF EXISTS inventory CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS categories CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'cashier')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    barcode VARCHAR(50) UNIQUE,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    category_id INT REFERENCES categories(id) ON DELETE SET NULL,
    cost_price NUMERIC(10, 2) NOT NULL CHECK (cost_price >= 0),
    selling_price NUMERIC(10, 2) NOT NULL CHECK (selling_price >= 0),
    stock_quantity INT NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    min_stock_level INT NOT NULL DEFAULT 5 CHECK (min_stock_level >= 0),
    image_url VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE inventory (
    id SERIAL PRIMARY KEY,
    product_id INT UNIQUE NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    current_stock INT NOT NULL DEFAULT 0 CHECK (current_stock >= 0),
    reorder_level INT NOT NULL DEFAULT 5 CHECK (reorder_level >= 0),
    last_restocked_at TIMESTAMP WITHOUT TIME ZONE,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE inventory_movements (
    id SERIAL PRIMARY KEY,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    movement_type VARCHAR(20) NOT NULL CHECK (movement_type IN ('in', 'out', 'adjustment', 'return')),
    quantity INT NOT NULL,
    reference_note VARCHAR(255),
    performed_by INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sales (
    id SERIAL PRIMARY KEY,
    invoice_number VARCHAR(50) UNIQUE NOT NULL,
    user_id INT REFERENCES users(id) ON DELETE SET NULL,
    subtotal NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (subtotal >= 0),
    discount_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (discount_amount >= 0),
    tax_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (tax_amount >= 0),
    total_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (total_amount >= 0),
    payment_status VARCHAR(20) NOT NULL DEFAULT 'completed' CHECK (payment_status IN ('pending', 'completed', 'cancelled', 'refunded')),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sale_items (
    id SERIAL PRIMARY KEY,
    sale_id INT NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity INT NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    subtotal NUMERIC(10, 2) NOT NULL CHECK (subtotal >= 0)
);

CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    sale_id INT NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    payment_method VARCHAR(30) NOT NULL CHECK (payment_method IN ('cash', 'credit_card', 'debit_card', 'e_wallet', 'other')),
    amount_tendered NUMERIC(10, 2) NOT NULL CHECK (amount_tendered >= 0),
    change_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (change_amount >= 0),
    payment_date TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_products_name ON products(name);

CREATE INDEX idx_products_barcode ON products(barcode);

CREATE INDEX idx_products_category_id ON products(category_id);

CREATE INDEX idx_sales_created_at ON sales(created_at);

CREATE INDEX idx_products_active_stock ON products(is_active, stock_quantity);

CREATE INDEX idx_sale_items_sale_id ON sale_items(sale_id);

CREATE INDEX idx_sale_items_product_id ON sale_items(product_id);

CREATE INDEX idx_users_username ON users(username);

CREATE INDEX idx_sales_user_id ON sales(user_id);

CREATE INDEX idx_inventory_movements_product_id ON inventory_movements(product_id);
CREATE INDEX idx_inventory_movements_created_at ON inventory_movements(created_at);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'prosfora_reporting_user') THEN
        CREATE ROLE prosfora_reporting_user WITH LOGIN PASSWORD 'ReportingUserPass2026!';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'prosfora_cashier_user') THEN
        CREATE ROLE prosfora_cashier_user WITH LOGIN PASSWORD 'CashierUserPass2026!';
    END IF;
END $$;

REVOKE INSERT, UPDATE, DELETE ON users, products, categories, inventory, sales, sale_items, payments, inventory_movements FROM prosfora_reporting_user;
REVOKE SELECT ON users FROM prosfora_reporting_user;

CREATE OR REPLACE PROCEDURE GenerateRegionalReport(
    IN p_start_date TIMESTAMP,
    IN p_end_date TIMESTAMP,
    IN p_requested_by VARCHAR(100)
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RAISE NOTICE 'AUDIT: Regional sales report generated by % for window % to %', p_requested_by, p_start_date, p_end_date;

    PERFORM
        COUNT(s.id) AS total_transactions,
        COALESCE(SUM(s.total_amount), 0.00) AS gross_revenue
    FROM sales s
    WHERE s.created_at >= p_start_date AND s.created_at <= p_end_date;
END;
$$;

GRANT EXECUTE ON PROCEDURE GenerateRegionalReport(TIMESTAMP, TIMESTAMP, VARCHAR) TO prosfora_reporting_user;

CREATE OR REPLACE FUNCTION ProcessSecureCheckout(
    p_invoice VARCHAR(50),
    p_user_id INT,
    p_subtotal NUMERIC(10,2),
    p_discount NUMERIC(10,2),
    p_tax NUMERIC(10,2),
    p_total NUMERIC(10,2)
)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_sale_id INT;
BEGIN
    IF p_total < 0 THEN
        RAISE EXCEPTION 'Security Violation: Total amount cannot be negative.';
    END IF;

    INSERT INTO sales (invoice_number, user_id, subtotal, discount_amount, tax_amount, total_amount, payment_status, created_at)
    VALUES (p_invoice, p_user_id, p_subtotal, p_discount, p_tax, p_total, 'completed', CURRENT_TIMESTAMP)
    RETURNING id INTO v_sale_id;

    RETURN v_sale_id;
END;
$$;

GRANT EXECUTE ON FUNCTION ProcessSecureCheckout(VARCHAR, INT, NUMERIC, NUMERIC, NUMERIC, NUMERIC) TO prosfora_cashier_user;
