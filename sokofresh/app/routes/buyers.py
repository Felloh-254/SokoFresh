import os
import psycopg2.extras
from flask import Flask, render_template, url_for, request, jsonify, Blueprint, current_app, redirect
from flask_login import login_user, logout_user, login_required, current_user
from app.db.db import get_db_connection, release_db_connection
from werkzeug.utils import secure_filename
from PIL import Image

buyers = Blueprint('buyers', __name__, url_prefix='/')

# Rote to our home page
@buyers.route('/')
def home():
    return render_template('/buyers/buyers.html', user = current_user)



@buyers.route('/my-orders')
def my_orders():
    return render_template('/buyers/my_orders.html', user = current_user)



# Route to marketplace
@buyers.route('/marketplace')
def marketplace():
    page = int(request.args.get('page', 1))
    limit = 12
    offset = (page - 1) * limit
    category_filter = request.args.get('category', '').strip()
    search_query = request.args.get('q', '').strip()

    products = get_all_available_products(limit=limit, offset=offset,
                                          category=category_filter,
                                          search=search_query)

    total_products = count_available_products(category_filter, search_query)
    total_pages = max((total_products + limit - 1) // limit, 1)
    
    categories = get_product_categories()
    user_liked_ids = [product['product_id'] for product in get_user_liked_products(current_user.id)]
    return render_template('/shared/marketplace.html',
                       products=products, page=page,
                       total_pages=total_pages,
                       total_products=total_products,
                       user=current_user, categories=categories,
                       user_liked_ids=user_liked_ids)





# Function to like a product
@buyers.route('/marketplace/like/<int:product_id>', methods=['POST'])
@login_required
def like_product(product_id):
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute('''
            SELECT 1 FROM liked_products
            WHERE liked_product_user_id = %s AND liked_product_product_id = %s
        ''', (current_user.id, product_id))
        already_liked = cur.fetchone()

        if already_liked:
            cur.execute('''
                DELETE FROM liked_products
                WHERE liked_product_user_id = %s AND liked_product_product_id = %s
            ''', (current_user.id, product_id))
            action = 'unliked'
        else:
            cur.execute('''
                INSERT INTO liked_products (liked_product_user_id, liked_product_product_id)
                VALUES (%s, %s)
            ''', (current_user.id, product_id))
            action = 'liked'

        conn.commit()
        return jsonify({'status': 'success', 'action': action})

    except Exception as e:
        conn.rollback()
        print("Error toggling like:", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500

    finally:
        cur.close()
        release_db_connection(conn)



@buyers.route('/marketplace/cart/add', methods=['POST'])
@login_required
def add_to_cart():
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)

    if not product_id or quantity < 1:
        return jsonify({'status': 'error', 'message': 'Invalid input'}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Check if already in cart
        cur.execute('''
            SELECT cart_item_id FROM cart_items
            WHERE cart_item_user_id = %s AND cart_item_product_id = %s
        ''', (current_user.id, product_id))
        existing = cur.fetchone()

        if existing:
            # Update quantity
            cur.execute('''
                UPDATE cart_items
                SET cart_item_product_quantity = cart_item_product_quantity + %s
                WHERE cart_item_user_id = %s AND cart_item_product_id = %s
            ''', (quantity, current_user.id, product_id))
        else:
            # Insert new
            cur.execute('''
                INSERT INTO cart_items (cart_item_user_id, cart_item_product_id, cart_item_product_quantity)
                VALUES (%s, %s, %s)
            ''', (current_user.id, product_id, quantity))

        conn.commit()
        return jsonify({'status': 'success', 'message': 'Added to cart'})

    except Exception as e:
        conn.rollback()
        print("Error adding to cart:", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500

    finally:
        cur.close()
        release_db_connection(conn)



# Function to get all the available products
def get_all_available_products(limit=12, offset=0, category='', search=''):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    try:
        query = '''
            SELECT p.*
            FROM products p
            JOIN product_types pt ON p.product_type_id = pt.product_type_id
            JOIN product_categories pc ON pt.product_type_category_id = pc.product_category_id
            WHERE p.product_status = 'active'
            '''
            
        values = []

        if category:
            query += ''' AND (
                LOWER(pc.product_category_name_en) = LOWER(%s)
                OR LOWER(pt.product_type_name_en) = LOWER(%s)
                OR LOWER(pt.product_type_name_local) = LOWER(%s)
            )'''
            values.extend([category, category, category])

        if search:
            query += ''' AND (
                LOWER(p.product_name) LIKE LOWER(%s)
                OR LOWER(pt.product_type_name_en) LIKE LOWER(%s)
                OR LOWER(pt.product_type_name_local) LIKE LOWER(%s)
            )'''
            like = f"%{search}%"
            values.extend([like, like, like])

        query += ''' ORDER BY p.product_id DESC LIMIT %s OFFSET %s'''
        values.extend([limit, offset])

        cur.execute(query, tuple(values))
        return cur.fetchall()

    except Exception as e:
        print("Error fetching products:", e)
        return []
    finally:
        cur.close()
        release_db_connection(conn)




# Countnig the available products for pagination
def count_available_products(category='', search=''):
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        query = '''
            SELECT COUNT(*)
            FROM products p
            JOIN product_types pt ON p.product_type_id = pt.product_type_id
            JOIN product_categories pc ON pt.product_type_category_id = pc.product_category_id
            WHERE p.product_status = 'active'
        '''
        values = []

        if category:
            query += ''' AND (
                LOWER(pc.product_category_name_en) = LOWER(%s)
                OR LOWER(pt.product_type_name_en) = LOWER(%s)
                OR LOWER(pt.product_type_name_local) = LOWER(%s)
            )'''
            values.extend([category, category, category])

        if search:
            query += ''' AND (
                LOWER(p.product_name) LIKE LOWER(%s)
                OR LOWER(pt.product_type_name_en) LIKE LOWER(%s)
                OR LOWER(pt.product_type_name_local) LIKE LOWER(%s)
            )'''
            like = f"%{search}%"
            values.extend([like, like, like])

        cur.execute(query, tuple(values))
        total = cur.fetchone()[0]
        return total

    except Exception as e:
        print("Error counting products:", e)
        return 0
    finally:
        cur.close()
        release_db_connection(conn)




# Function to get all available categories
def get_product_categories():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        query = '''
            SELECT
            product_category_id,
            product_category_name_en,
            product_category_name_sw
            FROM product_categories
            ORDER BY product_category_name_en'''

        cur.execute(query)

        categories = cur.fetchall()
        return categories
    except Exception as e:
        print(f"Error fetching categories: {e}")
        return e
    finally:
        cur.close()
        release_db_connection(conn)


# Function to get all the user liked products
def get_user_liked_products(user_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    try:
        cur.execute('''
            SELECT p.*
            FROM liked_products lp
            JOIN products p ON lp.liked_product_product_id = p.product_id
            WHERE lp.liked_product_user_id = %s
            ORDER BY lp.liked_product_liked_at DESC
        ''', (user_id,))
        return cur.fetchall()
    
    except Exception as e:
        print("Error fetching liked products:", e)
        return []

    finally:
        cur.close()
        release_db_connection(conn)




# User settings routes
@buyers.route('/settings')
@login_required
def settings():
    conn = get_db_connection()
    if not conn:
        print("Error connecting to Database")
        return render_template('shared/settings.html', error="Database connection failed")

    try:
        cur = conn.cursor()

        # Get all the farming methods
        cur.execute('''SELECT farming_method_name FROM farming_methods''')
        farming_methods = cur.fetchall()

        # Get all the seasons available
        cur.execute('''SELECT availability_month_name FROM availability_months''')
        months = cur.fetchall()

        # Get all product categories
        categories = get_product_categories()

    except Exception as e:
        print(f"Error encountered: {e}")
        farming_methods = []
        months = []
        categories = []

    finally:
        cur.close()
        release_db_connection(conn)

    # Pass categories to template
    return render_template(
        'shared/settings.html',
        user=current_user,
        farming_methods=farming_methods,
        months=months,
        categories=categories
    )


@buyers.route('/start-selling', methods=['POST'])
@login_required
def add_farmer_role():
    # Get the farmer details
    farm_location = request.form.get('farm_location')
    farm_size = request.form.get('farm_size')
    produce_category = safe_int_list('produce_category[]')
    produce_type = safe_int_list('produce_types[]')
    farming_methods = request.form.getlist('farming_methods[]') if request.form.getlist('farming_methods[]') else []
    availability_schedule = request.form.getlist('availability_schedule[]') if request.form.getlist('availability_schedule[]') else []

    mpesa_number = request.form.get('mpesa_number')
    transport = True if request.form.get('transport') else False
    storage = True if request.form.get('storage') else False

    print(f"Category: {produce_category}, Type: {produce_type}, methods: {farming_methods}, Schedule: {availability_schedule}")

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Add the farmer information
        query = """ INSERT INTO farmer
            (farmer_user_id, farmer_farm_location, farmer_farm_size_acres, farmer_produce_category,
            farmer_produce_types, farmer_farming_methods, farmer_produce_availability_schedule, farmer_mpesa_number,
            farmer_transport_available, farmer_storage_available)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

        cur.execute(query, (current_user.id, farm_location, farm_size, produce_category, produce_type,
            farming_methods, availability_schedule, mpesa_number, transport, storage))

        # Get the farmer role_id
        cur.execute("SELECT role_id FROM roles WHERE role_name = 'farmer';")
        role_id = cur.fetchone()
        if role_id:

            # Add the farmer role
            cur.execute('''
                INSERT INTO user_roles (user_role_user_id, user_role_role_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING;
            ''', (current_user.id, role_id[0]))

        conn.commit()
        return jsonify({"message": "Your registration to sell was successfull"}), 200
    except Exception as e:
        print(f"Error adding role: {e}")
    finally:
        cur.close()
        release_db_connection(conn)


@buyers.route('/remove_farmer_role', methods=['POST'])
@login_required
def remove_farmer_role():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            DELETE FROM user_roles
            USING roles
            WHERE roles.role_id = user_roles.user_role_role_id
              AND roles.role_name = 'farmer'
              AND user_roles.user_role_user_id = %s;
        ''', (current_user.id,))
        conn.commit()
        flash("Farmer role removed.")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('profile'))


def safe_int_list(form_key):
    return [int(x) for x in request.form.getlist(form_key) if x.isdigit()]