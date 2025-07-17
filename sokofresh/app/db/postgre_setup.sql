CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    user_email VARCHAR(255) UNIQUE NOT NULL,
    user_password TEXT,
    user_full_name VARCHAR(255) NOT NULL,
    user_contacts TEXT[],
    user_date_of_birth DATE,
    user_oauth_id TEXT UNIQUE,
    user_profile_picture TEXT
);

CREATE TABLE account_details (
    account_id SERIAL PRIMARY KEY,
    account_user_id INTEGER UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    account_oauth_provider TEXT DEFAULT 'system' CHECK(account_oauth_provider IN('system', 'google')),
    account_status TEXT DEFAULT 'active' CHECK (account_status IN ('active', 'inactive', 'suspended', 'banned')),
    account_last_login  TIMESTAMP,
    account_email_verified  BOOLEAN DEFAULT FALSE,
    account_profile_completed   BOOLEAN DEFAULT FALSE,
    account_creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE account_verification (
    account_verification_id SERIAL PRIMARY KEY,
    account_verification_user_id INTEGER UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    account_verification_code VARCHAR(10),
    account_verification_started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    account_verification_code_expires TIMESTAMP,
    account_verification_complete BOOLEAN DEFAULT FALSE
);


CREATE TABLE roles (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(50) CHECK(role_name IN ('buyer', 'farmer', 'admin')) UNIQUE NOT NULL
);

CREATE TABLE user_roles (
    user_role_user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    user_role_role_id INTEGER REFERENCES roles(role_id) ON DELETE CASCADE,
    PRIMARY KEY (user_role_user_id, user_role_role_id)
);

CREATE TABLE farmer (
    farmer_id SERIAL PRIMARY KEY,
    farmer_user_id INTEGER UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    farmer_farm_location VARCHAR(255) NOT NULL,
    farmer_farm_size_acres DECIMAL(5,2),
    farmer_produce_category INTEGER[] NOT NULL,
    farmer_produce_types INTEGER [] NOT NULL,
    farmer_farming_methods TEXT[] NOT NULL,
    farmer_produce_availability_schedule TEXT[],
    farmer_mpesa_number VARCHAR(20),
    farmer_transport_available BOOLEAN DEFAULT FALSE,
    farmer_storage_available BOOLEAN DEFAULT FALSE,
    farmer_account_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE farming_methods (
    farming_method_id SERIAL PRIMARY KEY,
    farming_method_name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE availability_months (
    availability_month_id SERIAL PRIMARY KEY,
    availability_month_name VARCHAR(20) UNIQUE NOT NULL
);


CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    product_farmer_id INTEGER REFERENCES farmer(farmer_id) ON DELETE SET NULL,
    product_type_id INTEGER REFERENCES product_types(product_type_id) ON DELETE SET NULL,
    product_name VARCHAR(255) NOT NULL,
    product_description TEXT,
    product_unit_price DECIMAL(10, 2) NOT NULL,
    product_quantity INTEGER NOT NULL,
    product_unit VARCHAR(50), -- e.g. 'kg', 'crate', 'bunch'
    product_status VARCHAR(20) DEFAULT 'active',
    product_views INTEGER DEFAULT 0,
    product_image_url TEXT,
    product_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    product_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE cart_items (
    cart_item_id SERIAL PRIMARY KEY,
    cart_item_user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    cart_item_product_id INTEGER REFERENCES products(product_id) ON DELETE CASCADE,
    cart_item_product_quantity INTEGER NOT NULL CHECK (cart_item_product_quantity > 0),
    cart_item_added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE liked_products (
    liked_product_id SERIAL PRIMARY KEY,
    liked_product_user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    liked_product_product_id INTEGER REFERENCES products(product_id) ON DELETE CASCADE,
    liked_product_liked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(liked_product_user_id, liked_product_product_id)
);



CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    order_buyer_id INTEGER REFERENCES users(id),
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    order_status VARCHAR(50) DEFAULT 'pending'  -- pending, accepted, delivered
);

CREATE TABLE order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_item_order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    order_product_id INTEGER REFERENCES products(id),
    order_quantity INTEGER NOT NULL,
    order_unit_price DECIMAL(10, 2) NOT NULL
);


CREATE TABLE product_categories (
    product_category_id SERIAL PRIMARY KEY,
    product_category_name_en VARCHAR(100) UNIQUE NOT NULL,
    product_category_name_sw VARCHAR(100) UNIQUE NOT NULL,
    product_category_image_url TEXT
);

CREATE TABLE product_types (
    product_type_id SERIAL PRIMARY KEY,
    product_type_category_id INTEGER REFERENCES product_categories(product_category_id) ON DELETE CASCADE,
    product_type_name_en VARCHAR(100) NOT NULL,
    product_type_name_sw VARCHAR(100),
    product_type_name_local VARCHAR(100),
    product_type_image_url TEXT
);
