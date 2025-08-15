import os
import random
import string
import json
import traceback
import psycopg2.extras
from psycopg2.extras import execute_values
from flask import Flask, render_template, url_for, request, jsonify, Blueprint, current_app, redirect, make_response
from flask_login import login_user, logout_user, login_required, current_user
from app.db.db import get_db_connection, release_db_connection
from werkzeug.utils import secure_filename
from PIL import Image
from datetime import datetime, timedelta
from weasyprint import HTML

buyers = Blueprint('buyers', __name__, url_prefix='/')

# Rote to our home page
@buyers.route('/')
def home():
    return render_template('/buyers/buyers.html', user = current_user)



@buyers.route("/my-orders")
@login_required
def my_orders():
    user_id = current_user.id
    total_orders, active_orders, total_spent, satisfaction_rate, customer_orders = get_buyer_orders(user_id)
    return render_template('/buyers/my_orders.html',
                        user=current_user,
                        total_orders=total_orders,
                        active_orders=active_orders,
                        total_spent=total_spent,
                        satisfaction_rate=satisfaction_rate,
                        customer_orders=customer_orders)




def get_buyer_orders(user_id):
    buyer_user_id = user_id
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # Get orders
        cur.execute("""
            SELECT * FROM buyer_order_grouped_view 
            WHERE buyer_user_id = %s AND order_item_status!= 'cancelled'
            ORDER BY order_date DESC
        """, (buyer_user_id,))
        
        orders = cur.fetchall()
        order_list = []  # Using order_list instead of processed_orders to avoid any conflicts
        
        for order in orders:
            try:
                # Convert to regular dictionary safely
                current_order = dict(order) if not isinstance(order, dict) else order

                # Handle datetime conversion
                if isinstance(current_order.get('order_date'), datetime):
                    current_order['order_date'] = current_order['order_date'].isoformat()
                
                # Ensure items is a list
                current_items = current_order.get('items', [])
                if isinstance(current_items, str):
                    current_items = json.loads(current_items)
                current_order['items'] = current_items

                # Convert numeric fields
                current_order['subtotal'] = float(current_order.get('subtotal', 0))
                current_order['delivery_fee'] = float(current_order.get('delivery_fee', 0))
                current_order['total_amount'] = float(current_order.get('total_amount', 0))
                
                order_list.append(current_order)
                
            except Exception as inner_e:
                print(f"Error processing order {order.get('order_id')}: {inner_e}")
                continue
        # Calculate statistics - using different variable names to avoid conflicts
        orders_count = len(order_list)
        active_count = sum(1 for ord in order_list 
                         if str(ord.get('status', '')).lower() in ['pending', 'confirmed'])
        spent_total = sum(ord.get('total_amount', 0) for ord in order_list)
        delivered_count = sum(1 for ord in order_list 
                          if str(ord.get('status', '')).lower() == 'delivered')
        satisfaction = round((delivered_count / orders_count * 100), 1) if orders_count > 0 else 0

        return orders_count, active_count, spent_total, satisfaction, order_list
        
        
    except Exception as e:
        print(f"Error in my_orders route: {e}")
        return None
    finally:
        cur.close()
        release_db_connection(conn)


# Additional routes for order actions
@buyers.route("/order/<order_reference>/track")
@login_required
def track_order(order_reference):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        cur.execute("""
            SELECT 
                o.order_reference_number,
                o.order_drop_location as delivery_address,
                o.order_date,
                MODE() WITHIN GROUP (ORDER BY oi.order_item_status) as status
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_item_order_id
            WHERE o.order_reference_number = %s 
            AND o.order_buyer_id = %s
            GROUP BY o.order_reference_number, o.order_drop_location, o.order_date
        """, (order_reference, current_user.id))
        
        order = cur.fetchone()
        
        if order:
            # Calculate estimated delivery (example logic)
            from datetime import datetime, timedelta
            estimated_delivery = (order['order_date'] + timedelta(days=2)).strftime('%B %d, %Y')
            
            tracking_info = {
                'order_id': order_reference,
                'status': order['status'],
                'estimated_delivery': estimated_delivery,
                'delivery_address': order['delivery_address'],
                'driver_info': 'John Kamau (+254712345678)'  # This could come from a drivers table
            }
            return jsonify({'success': True, 'data': tracking_info})
        else:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
            
    except Exception as e:
        print(f"Error tracking order: {e}")
        return jsonify({'success': False, 'message': 'Error tracking order'}), 500
    finally:
        cur.close()
        release_db_connection(conn)


@buyers.route('/buyers/orders/<int:order_id>/cancel/<int:order_item_id>', methods=['POST'])
@login_required
def cancel_order(order_id, order_item_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Update order items status to cancelled
        cur.execute("""
            UPDATE order_items 
            SET order_item_status = 'cancelled'
            FROM orders o
            WHERE order_items.order_item_order_id = o.order_id
            AND order_items.order_item_id = %s
            AND o.order_id = %s 
            AND o.order_buyer_id = %s
            AND order_items.order_item_status IN ('pending', 'confirmed')
        """, (order_item_id, order_id, current_user.id))
        
        if cur.rowcount > 0:
            conn.commit()
            return jsonify({'success': True, 'message': 'Order cancelled successfully'})
        else:
            return jsonify({'success': False, 'message': 'Order cannot be cancelled or not found'}), 400
            
    except Exception as e:
        conn.rollback()
        print(f"Error cancelling order: {e}")
        return jsonify({'success': False, 'message': 'Error cancelling order'}), 500
    finally:
        cur.close()
        release_db_connection(conn)


@buyers.route("/order/<order_reference>/reorder", methods=['POST'])
@login_required
def reorder_items(order_reference):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # Get order items
        cur.execute("""
            SELECT oi.order_product_id as product_id, oi.order_quantity as quantity
            FROM order_items oi
            JOIN orders o ON oi.order_item_order_id = o.order_id
            WHERE o.order_reference_number = %s 
            AND o.order_buyer_id = %s
        """, (order_reference, current_user.id))
        
        items = cur.fetchall()
        
        if items:
            # Add items back to cart
            for item in items:
                # Check if item already exists in cart
                cur.execute("""
                    SELECT cart_item_id, cart_item_product_quantity 
                    FROM cart_items 
                    WHERE cart_item_user_id = %s AND cart_item_product_id = %s
                """, (current_user.id, item['product_id']))
                
                existing_item = cur.fetchone()
                
                if existing_item:
                    # Update quantity
                    cur.execute("""
                        UPDATE cart_items 
                        SET cart_item_product_quantity = cart_item_product_quantity + %s
                        WHERE cart_item_id = %s
                    """, (item['quantity'], existing_item['cart_item_id']))
                else:
                    # Add new item to cart
                    cur.execute("""
                        INSERT INTO cart_items (cart_item_user_id, cart_item_product_id, cart_item_product_quantity)
                        VALUES (%s, %s, %s)
                    """, (current_user.id, item['product_id'], item['quantity']))
            
            conn.commit()
            return jsonify({'success': True, 'message': 'Items added to cart successfully'})
        else:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
            
    except Exception as e:
        conn.rollback()
        print(f"Error reordering items: {e}")
        return jsonify({'success': False, 'message': 'Error adding items to cart'}), 500
    finally:
        cur.close()
        release_db_connection(conn)


@buyers.route("/order/<order_reference>/rate", methods=['POST'])
@login_required
def rate_order(order_reference):
    # You'll need to create a ratings table for this
    # For now, just return success
    try:
        data = request.get_json()
        rating = data.get('rating', 5)
        comment = data.get('comment', '')
        
        # TODO: Insert into ratings table when you create it
        # CREATE TABLE order_ratings (
        #     rating_id SERIAL PRIMARY KEY,
        #     rating_order_reference VARCHAR(20) REFERENCES orders(order_reference_number),
        #     rating_user_id INTEGER REFERENCES users(user_id),
        #     rating_score INTEGER CHECK (rating_score BETWEEN 1 AND 5),
        #     rating_comment TEXT,
        #     rating_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        # );
        
        return jsonify({'success': True, 'message': 'Rating submitted successfully'})
        
    except Exception as e:
        print(f"Error submitting rating: {e}")
        return jsonify({'success': False, 'message': 'Error submitting rating'}), 500





# Function to get the total orders
def get_total_orders(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT COUNT(*) FROM orders WHERE order_buyer_id = %s', (user_id,))
        return cur.fetchone()[0]
    except Exception as e:
        print(f"Error getting total count of orders for this user: {e}")
        return[]
    finally:
        cur.close()
        release_db_connection(conn)



# Route to marketplace
@buyers.route('/marketplace')
@login_required
def marketplace():
    page = int(request.args.get('page', 1))
    limit = 12
    offset = (page - 1) * limit
    category_filter = request.args.get('category', '').strip()
    search_query = request.args.get('q', '').strip()

    products = get_all_available_products(limit=limit, offset=offset,
                                          category=category_filter,
                                          search=search_query)

    cart_items = get_user_cart_products(current_user.id)

    total_products = count_available_products(category_filter, search_query)
    total_pages = max((total_products + limit - 1) // limit, 1)
    
    categories = get_product_categories()
    user_liked_ids = [product['product_id'] for product in get_user_liked_products(current_user.id)]
    return render_template('/shared/marketplace.html',
                       products=products, page=page,
                       total_pages=total_pages,
                       total_products=total_products,
                       user=current_user, categories=categories,
                       user_liked_ids=user_liked_ids,
                       cart_items=cart_items)





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
    # Ensure product_id and quantity are valid integers
    try:
        product_id = int(data.get('product_id'))
        quantity = int(data.get('quantity', 1))
        # New parameter to distinguish between add and set operations
        set_absolute = data.get('set_absolute', False)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Invalid product ID or quantity'}), 400
    
    if product_id <= 0:
        return jsonify({'status': 'error', 'message': 'Invalid product ID'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if quantity == 0:
            # REMOVE from cart
            cur.execute('''
                DELETE FROM cart_items
                WHERE cart_item_user_id = %s AND cart_item_product_id = %s
            ''', (current_user.id, product_id))
            conn.commit()
            return jsonify({'status': 'success', 'message': 'Item removed from cart'})
        
        if quantity < 0:
            return jsonify({'status': 'error', 'message': 'Quantity must be at least 1'}), 400
        
        # Check if already in cart
        cur.execute('''
            SELECT cart_item_id FROM cart_items
            WHERE cart_item_user_id = %s AND cart_item_product_id = %s
        ''', (current_user.id, product_id))
        existing = cur.fetchone()
        
        if existing:
            if set_absolute:
                # Set to absolute quantity
                cur.execute('''
                    UPDATE cart_items
                    SET cart_item_product_quantity = %s
                    WHERE cart_item_user_id = %s AND cart_item_product_id = %s
                ''', (quantity, current_user.id, product_id))
            else:
                # Add to existing quantity
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
        return jsonify({'status': 'success', 'message': 'Cart updated'})
        
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



# Function to get user's cart items
def get_user_cart_products(user_id):
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute('''
            SELECT
                ci.cart_item_id,
                ci.cart_item_user_id,
                ci.cart_item_product_id,
                ci.cart_item_product_quantity,
                ci.cart_item_added_at,
                p.product_name,
                p.product_unit_price
            FROM cart_items ci
            JOIN products p ON ci.cart_item_product_id = p.product_id
            WHERE ci.cart_item_user_id = %s
        ''', (user_id,))
        
        rows = cur.fetchall()

        # Convert to a list of clean JSON-safe dicts
        cart_items = []
        for row in rows:
            cart_items.append({
                'cart_item_id': row[0],
                'cart_item_user_id': row[1],
                'cart_item_product_id': row[2],
                'cart_item_product_quantity': row[3],
                'created_at': row[4].isoformat(),
                'product_name': row[5],
                'product_unit_price': float(row[6]),
            })

        return cart_items

    except Exception as e:
        print(f"Error fetching cart items: {e}")
        return []
    finally:
        cur.close()
        release_db_connection(conn)




# User settings routes
@buyers.route('/settings')
@login_required
def settings():
    conn = get_db_connection()
    cart_items = get_user_cart_products(current_user.id)
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
        categories=categories,
        cart_items=cart_items
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



@buyers.route('/marketplace/place-order', methods=['POST'])
@login_required
def place_order():
    if not current_user.id:
        return jsonify({'message': 'User not logged in'}), 401
    
    data = request.get_json()
    cart_items = data.get('cart_items', [])
    
    drop_location = data.get('drop_location')
    payment_method = data.get('payment_method')
    user_id = current_user.id
    
    if not cart_items or not drop_location or not payment_method:
        return jsonify({'message': 'Incomplete order data'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        order_reference = generate_reference()
        
        # First, check if all products have sufficient quantity
        for item in cart_items:
            product_id = item.get('cart_item_product_id')
            quantity = item.get('cart_item_product_quantity')
            
            if not product_id or not quantity:
                return jsonify({'message': 'Invalid cart item data'}), 400
            
            # Check current product quantity
            cur.execute("""
                SELECT product_quantity FROM products 
                WHERE product_id = %s AND product_status = 'active'
            """, (product_id,))
            
            result = cur.fetchone()
            if not result:
                return jsonify({'message': f'Product {product_id} not found or inactive'}), 400
            
            current_quantity = result[0]
            if current_quantity < quantity:
                return jsonify({
                    'message': f'Insufficient quantity for product {product_id}. Available: {current_quantity}, Requested: {quantity}'
                }), 400
        
        # Insert order
        cur.execute("""
            INSERT INTO orders (order_buyer_id, order_reference_number, order_date, order_drop_location, order_payment_method)
            VALUES (%s, %s, %s, %s, %s) RETURNING order_id
        """, (user_id, order_reference, datetime.now(), drop_location, payment_method))
        
        order_id = cur.fetchone()[0]
        order_items = []
        product_ids_to_clear = []
        
        # Process each cart item
        for item in cart_items:
            product_id = item.get('cart_item_product_id')
            quantity = item.get('cart_item_product_quantity')
            unit_price = item.get('product_unit_price')
                        
            if not product_id or not quantity or not unit_price:
                print(f"Missing product data: {item}")
                continue
            
            # Update product quantity (reduce by ordered amount)
            cur.execute("""
                UPDATE products 
                SET product_quantity = product_quantity - %s,
                    product_updated_at = CURRENT_TIMESTAMP
                WHERE product_id = %s
            """, (quantity, product_id))
            
            # Check if product quantity is now 0 and update status if needed
            cur.execute("""
                UPDATE products 
                SET product_status = 'out_of_stock'
                WHERE product_id = %s AND product_quantity = 0
            """, (product_id,))
            
            order_items.append((order_id, product_id, quantity, unit_price))
            product_ids_to_clear.append(product_id)
        
        # Delete cart items by user_id and product_id
        if product_ids_to_clear:
            cur.execute("""
                DELETE FROM cart_items
                WHERE cart_item_user_id = %s AND cart_item_product_id = ANY(%s)
            """, (user_id, product_ids_to_clear))
            
            print(f"Deleted {cur.rowcount} items from cart")
        
        # Insert order items
        if order_items:
            execute_values(cur, """
                INSERT INTO order_items (order_item_order_id, order_product_id, order_quantity, order_unit_price)
                VALUES %s
            """, order_items)
            
            print(f"Inserted {len(order_items)} order items")
        
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Order placed successfully', 'order_reference': order_reference}), 200
        
    except Exception as e:
        conn.rollback()
        print('Order Error:', e)
        traceback.print_exc()
        return jsonify({'message': 'Could not place order'}), 500
        
    finally:
        cur.close()
        release_db_connection(conn)



# Generating Reference number
def generate_reference():
    now = datetime.now().strftime('%Y%m%d%H%M%S')
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ORD-{now}-{random_part}"




@buyers.route('/buyers/receipt/<int:order_id>')
@login_required
def view_receipt(order_id):
    """Display order receipt details"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Fetch detailed order information using the view
    cur.execute('''
        SELECT * FROM order_receipt_grouped_view_for_farmers
        WHERE order_id = %s
    ''', (order_id,))
    
    order_items = cur.fetchall()
    
    if not order_items:
        cur.close()
        release_db_connection(conn)
        return "Order not found", 404
    
    # Calculate order total
    order_total = sum(item['item_total'] for item in order_items)
    
    # Get the order info.
    order_info = order_items[0]
    
    cur.close()
    release_db_connection(conn)
    
    return render_template('shared/receipt.html', 
                         order=order_info, 
                         order_items=order_items, 
                         order_total=order_total)


@buyers.route('/buyers/receipt/<int:order_id>/pdf')
def download_receipt_pdf(order_id):
    """Generate and download PDF receipt"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cur.execute('''
        SELECT * FROM order_receipt_grouped_view_for_farmers 
        WHERE order_id = %s
    ''', (order_id,))
    
    order_items = cur.fetchall()
    
    if not order_items:
        cur.close()
        release_db_connection(conn)
        return "Order not found", 404
    
    # Calculate order total
    order_total = sum(item['item_total'] for item in order_items)
    
    # Get the order info
    order_info = order_items[0]
    
    # Generate PDF
    html = render_template('shared/receipt.html', 
                         order=order_info, 
                         order_items=order_items, 
                         order_total=order_total)
    pdf = HTML(string=html, base_url=request.host_url).write_pdf()
        
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=receipt_{order_id}.pdf'
    
    cur.close()
    release_db_connection(conn)
    return response




@buyers.route('/marketplace/saved')
@login_required
def saved_products():
    """Display user's saved/liked products"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get saved products with product details
        cur.execute('''
            SELECT 
                p.product_id,
                p.product_name,
                p.product_description,
                p.product_unit_price,
                p.product_quantity,
                p.product_unit,
                p.product_image_url,
                p.product_views,
                pc.product_category_name_en as category_name,
                pt.product_type_name_en as type_name,
                u.user_full_name as farmer_name,
                f.farmer_farm_location,
                lp.liked_product_liked_at
            FROM liked_products lp
            JOIN products p ON lp.liked_product_product_id = p.product_id
            LEFT JOIN product_types pt ON p.product_type_id = pt.product_type_id
            LEFT JOIN product_categories pc ON pt.product_type_category_id = pc.product_category_id
            LEFT JOIN farmer f ON p.product_farmer_id = f.farmer_id
            LEFT JOIN users u ON f.farmer_user_id = u.user_id
            WHERE lp.liked_product_user_id = %s
            AND p.product_status = 'active'
            ORDER BY lp.liked_product_liked_at DESC
        ''', (current_user.id,))
        
        saved_products = cur.fetchall()

        # Convert to list of dictionaries for easier template handling
        products_list = []
        for product in saved_products:
            products_list.append({
                'product_id': product[0],
                'product_name': product[1],
                'product_description': product[2],
                'product_unit_price': float(product[3]) if product[3] else 0,
                'product_quantity': product[4],
                'product_unit': product[5],
                'product_image_url': product[6],
                'product_views': product[7],
                'category_name': product[8],
                'type_name': product[9],
                'farmer_name': product[10],
                'farmer_farm_location': product[11],
                'liked_at': product[12]
            })
        
        return render_template('buyers/saved_products.html', 
                             saved_products=products_list,
                             total_saved=len(products_list),
                             user=current_user)
        
    except Exception as e:
        current_app.logger.error(f"Error fetching saved products: {e}")
        return render_template('buyers/saved_products.html', 
                             saved_products=[],
                             total_saved=0,
                             error="Failed to load saved products",
                             user=current_user)
    finally:
        cur.close()
        release_db_connection(conn)


@buyers.route('/marketplace/saved/toggle', methods=['POST'])
@login_required
def toggle_saved_product():
    """Add or remove product from saved list"""
    data = request.get_json()
    
    try:
        product_id = int(data.get('product_id'))
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Invalid product ID'}), 400
    
    if product_id <= 0:
        return jsonify({'status': 'error', 'message': 'Invalid product ID'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if product is already saved
        cur.execute('''
            SELECT liked_product_id FROM liked_products
            WHERE liked_product_user_id = %s AND liked_product_product_id = %s
        ''', (current_user.id, product_id))
        
        existing = cur.fetchone()
        
        if existing:
            # Remove from saved products
            cur.execute('''
                DELETE FROM liked_products
                WHERE liked_product_user_id = %s AND liked_product_product_id = %s
            ''', (current_user.id, product_id))
            conn.commit()
            return jsonify({
                'status': 'success', 
                'message': 'Product removed from saved list',
                'action': 'removed',
                'is_saved': False
            })
        else:
            # Verify product exists and is active
            cur.execute('''
                SELECT product_id FROM products
                WHERE product_id = %s AND product_status = 'active'
            ''', (product_id,))
            
            if not cur.fetchone():
                return jsonify({'status': 'error', 'message': 'Product not found'}), 404
            
            # Add to saved products
            cur.execute('''
                INSERT INTO liked_products (liked_product_user_id, liked_product_product_id)
                VALUES (%s, %s)
            ''', (current_user.id, product_id))
            conn.commit()
            return jsonify({
                'status': 'success', 
                'message': 'Product added to saved list',
                'action': 'added',
                'is_saved': True
            })
            
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Error toggling saved product: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to update saved products'}), 500
    finally:
        cur.close()
        release_db_connection(conn)


@buyers.route('/marketplace/saved/remove', methods=['POST'])
@login_required
def remove_saved_product():
    """Remove specific product from saved list"""
    data = request.get_json()
    
    try:
        product_id = int(data.get('product_id'))
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Invalid product ID'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Remove from saved products
        cur.execute('''
            DELETE FROM liked_products
            WHERE liked_product_user_id = %s AND liked_product_product_id = %s
        ''', (current_user.id, product_id))
        
        if cur.rowcount == 0:
            return jsonify({'status': 'error', 'message': 'Product not found in saved list'}), 404
        
        conn.commit()
        return jsonify({
            'status': 'success', 
            'message': 'Product removed from saved list'
        })
        
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Error removing saved product: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to remove product'}), 500
    finally:
        cur.close()
        release_db_connection(conn)


@buyers.route('/marketplace/saved/clear', methods=['POST'])
@login_required
def clear_saved_products():
    """Clear all saved products for current user"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('''
            DELETE FROM liked_products
            WHERE liked_product_user_id = %s
        ''', (current_user.id,))
        
        removed_count = cur.rowcount
        conn.commit()
        
        return jsonify({
            'status': 'success', 
            'message': f'{removed_count} products removed from saved list',
            'removed_count': removed_count
        })
        
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Error clearing saved products: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to clear saved products'}), 500
    finally:
        cur.close()
        release_db_connection(conn)


@buyers.route('/api/product/<int:product_id>/saved-status')
@login_required
def get_product_saved_status(product_id):
    """Check if a product is saved by current user"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('''
            SELECT liked_product_id FROM liked_products
            WHERE liked_product_user_id = %s AND liked_product_product_id = %s
        ''', (current_user.id, product_id))
        
        is_saved = cur.fetchone() is not None
        
        return jsonify({
            'status': 'success',
            'is_saved': is_saved,
            'product_id': product_id
        })
        
    except Exception as e:
        current_app.logger.error(f"Error checking saved status: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to check saved status'}), 500
    finally:
        cur.close()
        release_db_connection(conn)




@buyers.route("/purchase-report")
@login_required
def view_purchase_report():
    """View purchase report before downloading"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # Get date range
        end_date = datetime.now()
        start_date = end_date.date().replace(day=1)
        
        if request.args.get('start_date'):
            start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d')
        if request.args.get('end_date'):
            end_date = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d')
        
        # Get previous month for comparison
        prev_month_end = start_date - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        
        # Get all report data
        kpis = calculate_buyer_kpis(cur, start_date, end_date, prev_month_start, prev_month_end, current_user.id)
        top_products = get_buyer_top_products(cur, start_date, end_date, current_user.id)
        favorite_farmers = get_favorite_farmers(cur, start_date, end_date, current_user.id)
        spending_by_category = get_spending_by_category(cur, start_date, end_date, current_user.id)
        monthly_spending = get_monthly_spending_trend(cur, current_user.id, 6)
        order_history = get_recent_orders(cur, start_date, end_date, current_user.id)
        daily_spending = get_daily_spending(cur, start_date, end_date, current_user.id)

        return render_template('buyers/report.html', 
                                 user=current_user,
                                 kpis=kpis,
                                 abs=abs,
                                 top_products=top_products,
                                 favorite_farmers=favorite_farmers,
                                 spending_by_category=spending_by_category,
                                 monthly_spending=monthly_spending,
                                 daily_spending=daily_spending,
                                 order_history=order_history,
                                 start_date=start_date.strftime('%B %d, %Y'),
                                 end_date=end_date.strftime('%B %d, %Y'),
                                 generated_date=datetime.now().strftime('%A, %B %d, %Y'))

    except Exception as e:
        print(f"Unable to generate report: {e}")

    finally:
        cur.close()
        release_db_connection(conn)
        



@buyers.route("/purchase-report/download")
@login_required
def download_purchase_report():
    """Download purchase report as PDF"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # Get date range
        end_date = datetime.now()
        start_date = end_date.date().replace(day=1)
        
        if request.args.get('start_date'):
            start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d')
        if request.args.get('end_date'):
            end_date = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d')
        
        # Get previous month for comparison
        prev_month_end = start_date - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        
        # Get all report data
        kpis = calculate_buyer_kpis(cur, start_date, end_date, prev_month_start, prev_month_end, current_user.id)
        top_products = get_buyer_top_products(cur, start_date, end_date, current_user.id)
        favorite_farmers = get_favorite_farmers(cur, start_date, end_date, current_user.id)
        spending_by_category = get_spending_by_category(cur, start_date, end_date, current_user.id)
        monthly_spending = get_monthly_spending_trend(cur, current_user.id, 6)
        order_history = get_recent_orders(cur, start_date, end_date, current_user.id)
        daily_spending = get_daily_spending(cur, start_date, end_date, current_user.id)
        
        # Generate PDF
        html = render_template('buyers/report.html', 
                             user=current_user,
                             kpis=kpis,
                             abs=abs,
                             top_products=top_products,
                             favorite_farmers=favorite_farmers,
                             spending_by_category=spending_by_category,
                             monthly_spending=monthly_spending,
                             daily_spending=daily_spending,
                             order_history=order_history,
                             start_date=start_date.strftime('%B %d, %Y'),
                             end_date=end_date.strftime('%B %d, %Y'),
                             generated_date=datetime.now().strftime('%A, %B %d, %Y'))
        
        pdf = HTML(string=html, base_url=request.host_url).write_pdf()
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=purchase_report_{current_user.id}_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}.pdf'
        
        return response
    
    finally:
        cur.close()
        release_db_connection(conn)

# Helper functions for buyer analytics
def calculate_buyer_kpis(cur, start_date, end_date, prev_start, prev_end, user_id):
    """Calculate key performance indicators for buyers"""
    
    # Total spending this period
    cur.execute("""
        SELECT COALESCE(SUM(oi.order_quantity * oi.order_unit_price), 0) as total_spending
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_item_order_id
        WHERE o.order_buyer_id = %s 
        AND o.order_date >= %s AND o.order_date <= %s
        AND oi.order_item_status != 'cancelled'
        AND oi.order_item_status = 'completed'
    """, (user_id, start_date, end_date))
    current_spending = cur.fetchone()['total_spending']
    
    # Previous period spending
    cur.execute("""
        SELECT COALESCE(SUM(oi.order_quantity * oi.order_unit_price), 0) as total_spending
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_item_order_id
        WHERE o.order_buyer_id = %s 
        AND o.order_date >= %s AND o.order_date <= %s
        AND oi.order_item_status != 'cancelled'
        AND oi.order_item_status = 'completed'
    """, (user_id, prev_start, prev_end))
    prev_spending = cur.fetchone()['total_spending']
    
    # Total orders this period
    cur.execute("""
        SELECT COUNT(*) as total_orders
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_item_order_id
        WHERE o.order_buyer_id = %s 
        AND o.order_date >= %s AND o.order_date <= %s
        AND oi.order_item_status != 'cancelled'
        AND oi.order_item_status = 'completed'
    """, (user_id, start_date, end_date))
    current_orders = cur.fetchone()['total_orders']
    
    # Previous period orders
    cur.execute("""
        SELECT COUNT(*) as total_orders
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_item_order_id
        WHERE o.order_buyer_id = %s 
        AND o.order_date >= %s AND o.order_date <= %s
        AND oi.order_item_status != 'cancelled'
        AND oi.order_item_status = 'completed'
    """, (user_id, prev_start, prev_end))
    prev_orders = cur.fetchone()['total_orders']
    
    # Average order value
    avg_order_value = current_spending / current_orders if current_orders > 0 else 0
    prev_avg_order_value = prev_spending / prev_orders if prev_orders > 0 else 0
    
    # Unique farmers purchased from
    cur.execute("""
        SELECT COUNT(DISTINCT f.farmer_id) as unique_farmers
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_item_order_id
        JOIN products p ON oi.order_product_id = p.product_id
        JOIN farmer f ON p.product_farmer_id = f.farmer_id
        WHERE o.order_buyer_id = %s 
        AND o.order_date >= %s AND o.order_date <= %s
        AND oi.order_item_status != 'cancelled'
        AND oi.order_item_status = 'completed'
    """, (user_id, start_date, end_date))
    unique_farmers = cur.fetchone()['unique_farmers']
    
    # Calculate percentage changes
    spending_change = ((current_spending - prev_spending) / prev_spending * 100) if prev_spending > 0 else 0
    orders_change = ((current_orders - prev_orders) / prev_orders * 100) if prev_orders > 0 else 0
    avg_order_change = ((avg_order_value - prev_avg_order_value) / prev_avg_order_value * 100) if prev_avg_order_value > 0 else 0
    
    return {
        'total_spending': float(current_spending),
        'spending_change': spending_change,
        'total_orders': current_orders,
        'orders_change': orders_change,
        'avg_order_value': float(avg_order_value),
        'avg_order_change': avg_order_change,
        'unique_farmers': unique_farmers
    }

def get_buyer_top_products(cur, start_date, end_date, user_id, limit=10):
    """Get buyer's most purchased products"""
    cur.execute("""
        SELECT 
            p.product_name,
            pc.product_category_name_en as category,
            SUM(oi.order_quantity) as total_quantity,
            SUM(oi.order_quantity * oi.order_unit_price) as total_spent,
            COUNT(*) as order_count,
            p.product_unit
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_item_order_id
        JOIN products p ON oi.order_product_id = p.product_id
        JOIN product_types pt ON p.product_type_id = pt.product_type_id
        JOIN product_categories pc ON pt.product_type_category_id = pc.product_category_id
        WHERE o.order_buyer_id = %s 
        AND o.order_date >= %s AND o.order_date <= %s
        AND oi.order_item_status != 'cancelled'
        AND oi.order_item_status = 'completed'
        GROUP BY p.product_id, p.product_name, pc.product_category_name_en, p.product_unit
        ORDER BY total_spent DESC
        LIMIT %s
    """, (user_id, start_date, end_date, limit))
    
    return cur.fetchall()

def get_favorite_farmers(cur, start_date, end_date, user_id, limit=5):
    """Get buyer's most frequently purchased from farmers"""
    cur.execute("""
        SELECT 
            u.user_full_name as farmer_name,
            f.farmer_farm_location,
            COUNT(DISTINCT o.order_id) as total_orders,
            SUM(oi.order_quantity * oi.order_unit_price) as total_spent,
            AVG(oi.order_quantity * oi.order_unit_price) as avg_order_value
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_item_order_id
        JOIN products p ON oi.order_product_id = p.product_id
        JOIN farmer f ON p.product_farmer_id = f.farmer_id
        JOIN users u ON f.farmer_user_id = u.user_id
        WHERE o.order_buyer_id = %s 
        AND o.order_date >= %s AND o.order_date <= %s
        GROUP BY f.farmer_id, u.user_full_name, f.farmer_farm_location
        ORDER BY total_spent DESC
        LIMIT %s
    """, (user_id, start_date, end_date, limit))
    
    return cur.fetchall()

def get_spending_by_category(cur, start_date, end_date, user_id):
    """Get spending breakdown by product category"""
    cur.execute("""
        SELECT 
            pc.product_category_name_en as category,
            SUM(oi.order_quantity * oi.order_unit_price) as total_spent,
            COUNT(*) as item_count,
            AVG(oi.order_quantity * oi.order_unit_price) as avg_item_cost
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_item_order_id
        JOIN products p ON oi.order_product_id = p.product_id
        JOIN product_types pt ON p.product_type_id = pt.product_type_id
        JOIN product_categories pc ON pt.product_type_category_id = pc.product_category_id
        WHERE o.order_buyer_id = %s 
        AND o.order_date >= %s AND o.order_date <= %s
        AND oi.order_item_status != 'cancelled'
        AND oi.order_item_status = 'completed'
        GROUP BY pc.product_category_id, pc.product_category_name_en
        ORDER BY total_spent DESC
    """, (user_id, start_date, end_date))
    
    result = cur.fetchall()

    if not result:
        return []
    
    total_money_spent = sum(float(row['total_spent'] or 0) for row in result)
    
    if total_money_spent == 0:
        return []
    
    return [
        {
            'category': row['category'], 
            'percentage': round((float(row['total_spent'] or 0) / total_money_spent * 100), 2),
            'total_spent': float(row['total_spent'] or 0),
            'items': int(row['item_count'] or 0)
        } 
        for row in result
    ]

def get_daily_spending(cur, start_date, end_date, user_id):
    cur.execute("""
        SELECT 
            DATE(o.order_date) as order_date,
            SUM(oi.order_quantity * oi.order_unit_price) as daily_spending,
            COUNT(DISTINCT o.order_id) as daily_orders
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_item_order_id
        WHERE o.order_buyer_id = %s 
          AND o.order_date BETWEEN %s AND %s
          AND oi.order_item_status != 'cancelled'
          AND oi.order_item_status = 'completed'
        GROUP BY DATE(o.order_date)
        ORDER BY DATE(o.order_date)
    """, (user_id, start_date, end_date))
    
    result = cur.fetchall()
    if not result:
        return []

    return [
        {
            'date': row['order_date'].strftime('%b %d'),  # format date
            'spending': float(row['daily_spending'] or 0),
            'orders': int(row['daily_orders'] or 0)
        }
        for row in result
    ]

def get_monthly_spending_trend(cur, user_id, months=6):
    cur.execute("""
        SELECT
            TO_CHAR(o.order_date, 'YYYY-MM') as month_year,
            TO_CHAR(o.order_date, 'Month') as month,
            SUM(oi.order_quantity * oi.order_unit_price) as total_spent,
            COUNT(DISTINCT o.order_id) as total_orders
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_item_order_id
        WHERE o.order_buyer_id = %s 
          AND o.order_date >= CURRENT_DATE - INTERVAL '%s months'
          AND oi.order_item_status != 'cancelled'
          AND oi.order_item_status = 'completed'
        GROUP BY TO_CHAR(o.order_date, 'YYYY-MM'), TO_CHAR(o.order_date, 'Month')
        ORDER BY month_year
    """, (user_id, months))

    result = cur.fetchall()
    if not result:
        return []

    return [
        {
            'month': row['month'].strip()[:3],  # e.g. 'Jul'
            'total_spent': float(row['total_spent'] or 0),
            'total_orders': int(row['total_orders'] or 0)
        }
        for row in result
    ]



def get_recent_orders(cur, start_date, end_date, user_id, limit=20):
    """Get recent order history for the buyer"""
    cur.execute("""
        SELECT 
            o.order_reference_number,
            o.order_date,
            o.order_drop_location,
            o.order_payment_method,
            SUM(oi.order_quantity * oi.order_unit_price) as order_total,
            COUNT(oi.order_item_id) as item_count,
            STRING_AGG(DISTINCT oi.order_item_status, ', ') as order_status
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_item_order_id
        WHERE o.order_buyer_id = %s 
        AND o.order_date >= %s AND o.order_date <= %s
        GROUP BY o.order_id, o.order_reference_number, o.order_date, 
                 o.order_drop_location, o.order_payment_method
        ORDER BY o.order_date DESC
        LIMIT %s
    """, (user_id, start_date, end_date, limit))
    
    return cur.fetchall()

