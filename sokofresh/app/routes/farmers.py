import os
import csv
import io
import json
import psycopg2.extras
import calendar
from flask import Flask, render_template, url_for, request, jsonify, Blueprint, current_app, redirect, make_response, send_file
from flask_login import login_user, logout_user, login_required, current_user
from app.db.db import get_db_connection, release_db_connection
from werkzeug.utils import secure_filename
from PIL import Image
from app.routes.buyers import safe_int_list
from weasyprint import HTML
from datetime import datetime, timedelta
from humanize import naturaltime
from collections import defaultdict



farmers = Blueprint('farmers', __name__, url_prefix='/')


@farmers.route('/farmer/dashboard')
@login_required
def farmers_dashboard():        
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get current date for accuracy of stats
        end_date = datetime.now()
        start_date = end_date.date().replace(day=1)

        # Get previous month for comparison
        prev_month_end = start_date - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)

        stats = get_stats_overview(cur, start_date, end_date, prev_month_start, prev_month_end, current_user.id)
        activity = get_latest_activity(cur, current_user.id, hours=24)
        
        if not activity:
            activity = []

        return render_template('/farmers/dashboard.html', 
                             user=current_user, 
                             stats=stats, 
                             activity=activity)
    
    except Exception as e:
        print(f"Error updating dashboard: {str(e)}")
    
    finally:
        cur.close()
        release_db_connection(conn)

@farmers.app_template_filter('timeago')
def timeago(value):
    if value is None:
        return ""
    try:
        if isinstance(value, str):
            value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        return naturaltime(datetime.utcnow() - value)
    except Exception as e:
        print(f"Error in timeago filter: {str(e)}")
        return ""

def get_latest_activity(cur, user_id, hours):
    try:
        cur.execute("""
            SELECT 
                o.order_id,
                o.order_date,
                COALESCE(oi.order_item_status, 'pending') as order_item_status,
                p.product_name,
                (oi.order_quantity * oi.order_unit_price) AS total_amount
            FROM order_items oi
            JOIN orders o ON oi.order_item_order_id = o.order_id
            JOIN products p ON oi.order_product_id = p.product_id
            JOIN farmer f ON p.product_farmer_id = f.farmer_id
            WHERE f.farmer_id = %s
              AND o.order_date >= NOW() - INTERVAL %s
            ORDER BY o.order_date DESC;
            """, (user_id, f'{hours} HOURS'))
        return cur.fetchall()
    except Exception as e:
        print(f"Error fetching activity: {str(e)}")
        return []



def get_stats_overview(cur, start_date, end_date, prev_start, prev_end, user_id):
    # Calculate current month stats
    cur.execute("""
        SELECT
            COUNT(p.product_id) as active_products,
            COUNT (o.order_id) as total_orders,
            COALESCE(SUM(oi.order_unit_price * oi.order_quantity), 0) as monthly_revenue
        FROM products p
        JOIN order_items oi ON p.product_id=oi.order_product_id
        JOIN orders o ON o.order_id = oi.order_item_order_id
        JOIN farmer f ON f.farmer_id = p.product_farmer_id
        JOIN users u ON u.user_id = f.farmer_user_id
        WHERE o.order_date BETWEEN %s AND %s
        AND u.user_id = %s""", (start_date, end_date, user_id))

    current_stats = cur.fetchone()

    # Calculate previous month stats
    cur.execute("""
        SELECT
            COUNT(p.product_id) as active_products,
            COUNT (o.order_id) as total_orders,
            COALESCE(SUM(oi.order_unit_price * oi.order_quantity), 0) as monthly_revenue
        FROM products p
        JOIN order_items oi ON p.product_id=oi.order_product_id
        JOIN orders o ON o.order_id = oi.order_item_order_id
        JOIN farmer f ON f.farmer_id = p.product_farmer_id
        JOIN users u ON u.user_id = f.farmer_user_id
        WHERE o.order_date BETWEEN %s AND %s
        AND u.user_id = %s""", (prev_start, prev_end, user_id))

    previous_stats = cur.fetchone()

    return {
        'active_product': current_stats['active_products'],
        'active_product_change': calc_change(current_stats['active_products'], previous_stats['active_products']),
        'total_orders': current_stats['total_orders'],
        'total_orders_change': calc_change(current_stats['total_orders'], previous_stats['total_orders']),
        'monthly_revenue': current_stats['monthly_revenue'],
        'monthly_revenue_change': calc_change(current_stats['monthly_revenue'], previous_stats['monthly_revenue'])
    }





# Calculate percentage changes
def calc_change(current, previous):
    if previous == 0:
        return 100 if current > 0 else 0
    return ((current - previous) / previous) * 100




@farmers.route('/farmer/update-farm-details', methods=['POST'])
@login_required
def update_farm():
    farm_size = request.form.get('update_farm_size')
    produce_category = safe_int_list('update_produce_category[]')
    produce_type = safe_int_list('update_produce_types[]')
    farming_methods = request.form.getlist('update_farming_methods[]') or []
    availability_schedule = request.form.getlist('update_availability_schedule[]') or []
    mpesa_number = request.form.get('update_mpesa_number')
    transport = bool(request.form.get('update_transport'))
    storage = bool(request.form.get('update_storage'))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = '''UPDATE farmer
            SET
            farmer_farm_size_acres = %s,
            farmer_produce_category = %s,
            farmer_produce_types = %s,
            farmer_farming_methods = %s,
            farmer_produce_availability_schedule = %s,
            farmer_mpesa_number = %s,
            farmer_transport_available = %s,
            farmer_storage_available = %s
            WHERE
            farmer_user_id = %s'''
        cur.execute(
                query,(
                farm_size,
                produce_category,
                produce_type,
                farming_methods,
                availability_schedule,
                mpesa_number,
                transport,
                storage,
                current_user.id))

        conn.commit()
        return jsonify({"message": "Farm details updated successfully!!"})

    except Exception as e:
        print(f"Error updating profile: {e}")
        return jsonify({"message": "An error occurred"})
    finally:
        cur.close()
        release_db_connection(conn)



@farmers.route('/farmer/post-product', methods=['GET', 'POST'])
@login_required
def post_product():
    conn = get_db_connection()
    if not conn:
        return jsonify({"message": "Database connection error"}), 400

    try:
        cur = conn.cursor()

        # Get the farmer data using current user ID
        cur.execute("""
            SELECT farmer_id, farmer_farm_location
            FROM farmer
            WHERE farmer_user_id = %s;
        """, (current_user.id,))

        farmer_data = cur.fetchone()

        if not farmer_data:
            return jsonify({"message": "Unable to verify you!!"})

        farmer_id, farm_location = farmer_data

        if request.method == 'POST':
            product_name = request.form.get('product_name')
            description = request.form.get('product_description')
            unit_price = request.form.get('product_unit_price')
            quantity = request.form.get('product_quantity')
            file = request.files.get('product_image')
            produce_type = request.form.get('product_type_id')
            product_unit = request.form.get('product_unit')

            image_url = None

            # Save image and get image_url
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(upload_path)
                image_url = url_for('static', filename=f'uploads/{filename}')

            cur.execute("""
                INSERT INTO products (
                    product_farmer_id,
                    product_type_id,
                    product_name,
                    product_description,
                    product_unit_price,
                    product_quantity,
                    product_unit,
                    product_image_url
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                farmer_id,
                produce_type,
                product_name,
                description,
                unit_price,
                quantity,
                product_unit,
                image_url
            ))

            conn.commit()
            return jsonify({"message": "Product posted successfully!"}), 200
        return render_template('farmers/post_product.html', user=current_user, farmer_farm_location=farm_location)

    finally:
        cur.close()
        release_db_connection(conn)



@farmers.route("/farmer/listings", methods=['GET', 'POST'])
@login_required
def my_listings():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    user_id = current_user.id
    products = []

    try:
        query = """
            SELECT p.* FROM products p
            JOIN farmer f ON f.farmer_id = p.product_farmer_id
            WHERE f.farmer_user_id = %s
        """
        cur.execute(query, (user_id,))
        products = cur.fetchall() or []
    except Exception as e:
        print(f"Error fetching listings: {e}")
    finally:
        cur.close()
        release_db_connection(conn)

    return render_template('/farmers/listings.html', user=current_user, products=products)



# Function to update farmer product listsing
@farmers.route("/farmer/listings/update-product-details", methods=['POST'])
@login_required
def update_product_details():
    form_data = request.form.to_dict()

    print(f"Form data: {form_data}")

    product_id = form_data.get('edit_product_id')
    name = form_data.get('edit_name')
    unit = form_data.get('edit_unit')
    price = form_data.get('edit_price')
    quantity = form_data.get('edit_quantity')
    description = form_data.get('edit_description')
    user_id = current_user.id
    image_url = None

    if not all([product_id, name, unit, price, quantity, description]):
        return jsonify({"message": "All fields are required"}), 400

    image_file = request.files.get('product_image')
    existing_image_url = request.form.get('existing_image_url')

    # Determine which image to use
    if image_file and image_file.filename != '':
        filename = secure_filename(image_file.filename)
        upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        image_file.save(upload_path)
        image_url = url_for('static', filename=f'uploads/{filename}')
    else:
        image_url = existing_image_url 

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        query = """
            UPDATE products
                SET
                    product_name = %s,
                    product_unit = %s,
                    product_unit_price = %s,
                    product_quantity = %s,
                    product_description = %s,
                    product_image_url = COALESCE(%s, product_image_url),
                    product_status = CASE 
                        WHEN product_quantity > 0 THEN 'active'
                        ELSE product_status
                    END,
                    product_updated_at = CURRENT_TIMESTAMP
                FROM farmer
                WHERE
                    products.product_id = %s
                    AND products.product_farmer_id = farmer.farmer_id
                    AND farmer.farmer_user_id = %s;"""

        cur.execute(query, (
            name, unit, price, quantity, description, image_url,
            product_id, user_id
        ))
        conn.commit()
        return jsonify({"message": "Product updated successfully"}), 200

    except Exception as e:
        print(f"Error updating product: {e}")
        return jsonify({"message": "Something went wrong"}), 500

    finally:
        cur.close()
        release_db_connection(conn)



@farmers.route('/farmer/product/delete', methods=['POST'])
def delete_product():
    product_id = request.json.get('product_id')

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Check for pending orders
    cur.execute("""
        SELECT COUNT(*) AS pending_count
        FROM order_items oi
        JOIN orders o ON oi.order_item_order_id = o.order_id
        WHERE oi.order_product_id = %s AND oi.order_item_status = 'pending'
    """, (product_id,))
    pending_count = cur.fetchone()['pending_count']

    if pending_count > 0:
        return jsonify({
            "success": False, 
            "message": f"This product has {pending_count} pending orders. Please pause and complete them before deleting.",
            "pending_count": pending_count
        }), 400

    # Safe to delete
    cur.execute("DELETE FROM products WHERE product_id = %s", (product_id,))
    conn.commit()

    cur.close()
    release_db_connection(conn)

    return jsonify({"success": True, "message": "Product deleted successfully"})


@farmers.route('/farmer/product/toggle-status', methods=['POST'])
def toggle_product_status():
    try:
        product_id = request.json.get('product_id')

        if not product_id:
            return jsonify({"success": False, "message": "No product ID provided"}), 400

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT product_status FROM products WHERE product_id = %s", (product_id,))
        product = cur.fetchone()

        if not product:
            return jsonify({"success": False, "message": "Product not found"}), 404

        new_status = 'paused' if product['product_status'] == 'active' else 'active'

        cur.execute("""
            UPDATE products 
            SET product_status = %s, product_updated_at = NOW()
            WHERE product_id = %s
        """, (new_status, product_id))
        conn.commit()

        return jsonify({"success": True, "new_status": new_status})

    except Exception as e:
        # Print full traceback in console (helps debugging)
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Internal Server Error: {str(e)}"}), 500

    finally:
        try:
            if cur: 
                cur.close()
            if conn:
                release_db_connection(conn)
        except Exception:
            pass


@farmers.route('/farmer/product/pending-count/<int:product_id>', methods=['GET'])
def get_pending_count(product_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) 
        FROM order_items oi
        JOIN orders o ON oi.order_item_order_id = o.order_id
        WHERE oi.order_product_id = %s AND oi.order_item_status = 'pending'
    """, (product_id,))
    count = cur.fetchone()[0]

    cur.close()
    release_db_connection(conn)

    return jsonify({"pending_count": count})


@farmers.route("/farmer/orders")
@login_required
def orders():
    farmer_user_id = current_user.id
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM farmer_order_grouped_view WHERE farmer_user_id = %s ORDER BY order_date DESC", (farmer_user_id,))
    orders = cur.fetchall()

    grouped_orders = defaultdict(list)
    for o in orders:
        grouped_orders[o['order_reference_number']].append(o)

    cur.close()
    release_db_connection(conn)
    return render_template('farmers/orders.html', user=current_user, grouped_orders=grouped_orders)



@farmers.route("/farmer/update-order-status", methods=["POST"])
@login_required
def update_order_status():
    data = request.get_json()
    order_id = data.get("order_id")
    order_item_id = data.get("order_item_id")
    new_status = data.get("new_status")

    if not order_id or not new_status:
        return jsonify({"success": False, "error": "Missing data"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Update all items in this order to new_status
        cur.execute("""
            UPDATE order_items
            SET order_item_status = %s
            WHERE order_item_order_id = %s
            AND order_item_id = %s
        """, (new_status, order_id, order_item_id))

        conn.commit()
        return jsonify({"success": True, "message": "Order status updated!"})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cur.close()
        release_db_connection(conn)




@farmers.route('/farmer/receipt/<int:order_id>', defaults={'order_item_id': None})
@farmers.route('/farmer/receipt/<int:order_id>/<int:order_item_id>')
@login_required
def view_receipt(order_id, order_item_id):
    """Display order receipt details (single item or full bundle)"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if order_item_id:
        # Fetch a specific order item
        cur.execute('''
            SELECT * FROM order_receipt_grouped_view_for_farmers
            WHERE order_id = %s AND order_item_id = %s AND farmer_user_id = %s
        ''', (order_id, order_item_id, current_user.id))
    else:
        # Fetch the whole order bundle
        cur.execute('''
            SELECT * FROM order_receipt_grouped_view_for_farmers
            WHERE order_id = %s AND farmer_user_id = %s
        ''', (order_id, current_user.id))

    order_items = cur.fetchall()
    if not order_items:
        cur.close()
        release_db_connection(conn)
        return "Order not found", 404

    # Calculate total
    order_total = sum(item['item_total'] for item in order_items)

    # Take general info from the first item
    order_info = order_items[0]

    cur.close()
    release_db_connection(conn)

    return render_template(
        'shared/receipt.html',
        order=order_info,
        order_items=order_items,
        order_total=order_total,
        is_bundle=(order_item_id is None)
    )



@farmers.route('/farmer/receipt/<int:order_id>/pdf', defaults={'order_item_id': None})
@farmers.route('/farmer/receipt/<int:order_id>/<int:order_item_id>/pdf')
@login_required
def download_receipt_pdf(order_id, order_item_id):
    """Generate and download PDF receipt"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    if order_item_id:
        # Fetch a specific order item
        cur.execute('''
            SELECT * FROM order_receipt_grouped_view_for_farmers
            WHERE order_id = %s AND order_item_id = %s AND farmer_user_id = %s
        ''', (order_id, order_item_id, current_user.id))
    else:
        # Fetch the whole order bundle
        cur.execute('''
            SELECT * FROM order_receipt_grouped_view_for_farmers
            WHERE order_id = %s AND farmer_user_id = %s
        ''', (order_id, current_user.id))
    
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


@farmers.route("/farmer/sales-report")
@login_required
def report():
    """Main sales report page"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # Get date range default to current month
        end_date = datetime.now()
        start_date = end_date.date().replace(day=1)
        
        # Override with query parameters if provided
        if request.args.get('start_date'):
            start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d')
        if request.args.get('end_date'):
            end_date = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d')
        
        # Get previous month for comparison
        prev_month_end = start_date - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        
        # Calculate KPIs
        kpis = calculate_kpis(cur, start_date, end_date, prev_month_start, prev_month_end, current_user.id)
        
        # Get top products
        top_products = get_top_products(cur, start_date, end_date, current_user.id)
        
        # Get regional performance
        regional_data = get_regional_performance(cur, start_date, end_date, current_user.id)

        monthly_comparison = get_monthly_comparison(cur, current_user.id, 3)
        sales_summary = get_sales_summary(cur, start_date, end_date)
        
        # Get daily sales data for chart
        daily_sales = get_daily_sales(cur, start_date, end_date, current_user.id)

        # Get category performance
        category_performance = get_category_performance(cur, start_date, end_date, current_user.id)

        return render_template('/farmers/sales_report.html', 
                             user=current_user,
                             kpis=kpis,
                             abs=abs,
                             top_products=top_products,
                             regional_data=regional_data,
                             daily_sales=daily_sales,
                             category_performance=category_performance,
                             start_date=start_date.strftime('%B %d, %Y'),
                             end_date=end_date.strftime('%B %d, %Y'),
                             generated_date=datetime.now().strftime('%A, %B %d, %Y'),
                             monthly_comparison=monthly_comparison,
                             sales_summary=sales_summary)
    
    finally:
        cur.close()
        release_db_connection(conn)




def calculate_kpis(cur, start_date, end_date, prev_start, prev_end, user_id):
    """Calculate Key Performance Indicators"""
    
    # Current period metrics
    cur.execute("""
        SELECT 
            SUM(oi.order_unit_price * oi.order_quantity) as total_revenue,
            COUNT(DISTINCT o.order_id) as total_orders,
            COUNT(DISTINCT o.order_buyer_id) as active_customers,
            COALESCE(AVG(oi.order_unit_price * oi.order_quantity), 0) as avg_order_value
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_item_order_id
        JOIN products p ON p.product_id = oi.order_product_id
        JOIN farmer f ON f.farmer_id = p.product_farmer_id
        JOIN users u ON u.user_id = f.farmer_user_id
        WHERE o.order_date BETWEEN %s AND %s
          AND oi.order_item_status != 'cancelled'
          AND oi.order_item_status = 'completed'
          AND u.user_id = %s
    """, (start_date, end_date, user_id))
    
    current_metrics = cur.fetchone()
    
    # Previous period metrics
    cur.execute("""
        SELECT 
            COALESCE(SUM(oi.order_unit_price * oi.order_quantity), 0) as total_revenue,
            COUNT(DISTINCT o.order_id) as total_orders,
            COUNT(DISTINCT o.order_buyer_id) as active_customers,
            COALESCE(AVG(oi.order_unit_price * oi.order_quantity), 0) as avg_order_value
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_item_order_id
        JOIN products p ON p.product_id = oi.order_product_id
        JOIN farmer f ON f.farmer_id = p.product_farmer_id
        JOIN users u ON u.user_id = f.farmer_user_id
        WHERE o.order_date BETWEEN %s AND %s
          AND oi.order_item_status != 'cancelled'
          AND oi.order_item_status = 'completed'
          AND u.user_id = %s
    """, (prev_start, prev_end, user_id))
    
    prev_metrics = cur.fetchone()
    
    # Active farmers count
    cur.execute("""
        SELECT COUNT(DISTINCT p.product_farmer_id) as active_farmers
        FROM products p
        JOIN order_items oi ON p.product_id = oi.order_product_id
        JOIN orders o ON oi.order_item_order_id = o.order_id
        WHERE o.order_date BETWEEN %s AND %s
          AND oi.order_item_status != 'cancelled'
          AND oi.order_item_status = 'completed'
    """, (start_date, end_date))
    
    current_farmers = cur.fetchone()
    
    cur.execute("""
        SELECT COUNT(DISTINCT p.product_farmer_id) as active_farmers
        FROM products p
        JOIN order_items oi ON p.product_id = oi.order_product_id
        JOIN orders o ON oi.order_item_order_id = o.order_id
        WHERE o.order_date BETWEEN %s AND %s
          AND oi.order_item_status != 'cancelled'
          AND oi.order_item_status = 'completed'
    """, (prev_start, prev_end))
    
    prev_farmers = cur.fetchone()
    
    # Order fulfillment rate
    cur.execute("""
        SELECT 
            COUNT(*) as total_orders,
            SUM(CASE WHEN order_item_status = 'delivered' THEN 1 ELSE 0 END) as delivered_orders
        FROM order_items oi
        JOIN orders o ON oi.order_item_order_id = o.order_id
        WHERE o.order_date BETWEEN %s AND %s
    """, (start_date, end_date))
    
    current_fulfillment = cur.fetchone()
    
    cur.execute("""
        SELECT 
            COUNT(*) as total_orders,
            SUM(CASE WHEN order_item_status = 'delivered' THEN 1 ELSE 0 END) as delivered_orders
        FROM order_items oi
        JOIN orders o ON oi.order_item_order_id = o.order_id
        WHERE o.order_date BETWEEN %s AND %s
    """, (prev_start, prev_end))
    
    prev_fulfillment = cur.fetchone()
    
    current_fulfillment_rate = (current_fulfillment['delivered_orders'] / current_fulfillment['total_orders'] * 100) if current_fulfillment['total_orders'] > 0 else 0
    prev_fulfillment_rate = (prev_fulfillment['delivered_orders'] / prev_fulfillment['total_orders'] * 100) if prev_fulfillment['total_orders'] > 0 else 0
    
    return {
        'total_revenue': current_metrics['total_revenue'],
        'revenue_change': calc_change(current_metrics['total_revenue'], prev_metrics['total_revenue']),
        'total_orders': current_metrics['total_orders'],
        'orders_change': calc_change(current_metrics['total_orders'], prev_metrics['total_orders']),
        'avg_order_value': current_metrics['avg_order_value'],
        'aov_change': calc_change(current_metrics['avg_order_value'], prev_metrics['avg_order_value']),
        'active_customers': current_metrics['active_customers'],
        'customers_change': calc_change(current_metrics['active_customers'], prev_metrics['active_customers']),
        'farmers_change': calc_change(current_farmers['active_farmers'], prev_farmers['active_farmers']),
        'fulfillment_rate': current_fulfillment_rate,
        'fulfillment_change': calc_change(current_fulfillment_rate, prev_fulfillment_rate)
    }

def get_top_products(cur, start_date, end_date, user_id):
    """Get top performing products"""
    cur.execute("""
        SELECT 
            p.product_name,
            pc.product_category_name_en as category,
            SUM(oi.order_quantity) as units_sold,
            p.product_unit,
            SUM(oi.order_unit_price * oi.order_quantity) as revenue,
            CASE 
                WHEN SUM(oi.order_unit_price * oi.order_quantity) > 10000 THEN 'Excellent'
                WHEN SUM(oi.order_unit_price * oi.order_quantity) > 3000 THEN 'Good'
                ELSE 'Needs Focus'
            END as performance
        FROM products p
        JOIN order_items oi ON p.product_id = oi.order_product_id
        JOIN orders o ON oi.order_item_order_id = o.order_id
        JOIN product_types pt ON p.product_type_id = pt.product_type_id
        JOIN product_categories pc ON pt.product_type_category_id = pc.product_category_id
        JOIN farmer f ON f.farmer_id = p.product_farmer_id
        JOIN users u ON u.user_id = f.farmer_user_id
        WHERE o.order_date BETWEEN %s AND %s
          AND oi.order_item_status != 'cancelled'
          AND u.user_id = %s
        GROUP BY p.product_id, p.product_name, pc.product_category_name_en, p.product_unit
        ORDER BY revenue DESC
        LIMIT 10
    """, (start_date, end_date, user_id))
    
    return cur.fetchall()

def get_regional_performance(cur, start_date, end_date, user_id):
    """Get regional sales performance"""
    
    # Initialize variables with defaults
    result = []
    total_revenue = 0
    
    try:
        cur.execute("""
            SELECT 
                DISTINCT o.order_drop_location as region,
                COUNT(DISTINCT o.order_id) as orders,
                SUM(oi.order_unit_price * oi.order_quantity) as revenue
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_item_order_id
            JOIN products p ON p.product_id = oi.order_product_id
            JOIN farmer f ON f.farmer_id = p.product_farmer_id
            JOIN users u ON u.user_id = f.farmer_user_id
            WHERE o.order_date BETWEEN %s AND %s
              AND oi.order_item_status != 'cancelled'
              AND u.user_id = %s
            GROUP BY region
            ORDER BY revenue DESC
        """, (start_date, end_date, user_id))
        
        result = cur.fetchall()
        
        if not result:
            print("No data found for the given date range")
            return []  # Return empty list
        
        # Proceed if result is not empty
        total_revenue = sum(row['revenue'] for row in result)
        
    except Exception as e:
        print(f"Error getting data: {str(e)}")
        return []
    
    # Calculate previous period for growth rate
    prev_month_end = start_date - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    
    try:
        cur.execute("""
            SELECT 
                DISTINCT o.order_drop_location as region,
                COUNT(DISTINCT o.order_id) as orders,
                SUM(oi.order_unit_price * oi.order_quantity) as revenue
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_item_order_id
            JOIN products p ON p.product_id = oi.order_product_id
            JOIN farmer f ON f.farmer_id = p.product_farmer_id
            JOIN users u ON u.user_id = f.farmer_user_id
            WHERE o.order_date BETWEEN %s AND %s
              AND oi.order_item_status != 'cancelled'
              AND u.user_id = %s
            GROUP BY region
        """, (prev_month_start, prev_month_end, user_id))
        
        prev_result = {row['region']: row['revenue'] for row in cur.fetchall()}
    except Exception as e:
        print(f"Error getting previous period data: {str(e)}")
        prev_result = {}
    
    regional_data = []
    for row in result:
        market_share = (row['revenue'] / total_revenue * 100) if total_revenue > 0 else 0
        prev_revenue = prev_result.get(row['region'], 0)
        growth_rate = ((row['revenue'] - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 100
        
        regional_data.append({
            'region': row['region'],
            'orders': row['orders'],
            'revenue': row['revenue'],
            'market_share': market_share,
            'growth_rate': growth_rate
        })
    
    return regional_data


def get_daily_sales(cur, start_date, end_date, user_id):
    """Get daily sales data for charts"""
    try:
        cur.execute("""
            SELECT 
                DATE(o.order_date) as sale_date,
                SUM(oi.order_unit_price * oi.order_quantity) as daily_revenue,
                COUNT(DISTINCT o.order_id) as order_count
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_item_order_id
            JOIN products p ON p.product_id = oi.order_product_id
            JOIN farmer f ON f.farmer_id = p.product_farmer_id
            JOIN users u ON u.user_id = f.farmer_user_id
            WHERE o.order_date BETWEEN %s AND %s
              AND oi.order_item_status != 'cancelled'
              AND oi.order_item_status = 'completed'
              AND u.user_id = %s
            GROUP BY DATE(o.order_date)
            ORDER BY sale_date
        """, (start_date, end_date, user_id))
        
        result = cur.fetchall()
        
        # If no data, return empty list
        if not result:
            return []
        
        return [
            {
                'date': row['sale_date'].strftime('%b %d'), 
                'revenue': float(row['daily_revenue'] or 0),
                'orders': int(row['order_count'] or 0)
            } 
            for row in result
        ]
    except Exception as e:
        print(f"Error in get_daily_sales: {e}")
        return []

def get_category_performance(cur, start_date, end_date, user_id):
    """Get product category performance with better error handling"""
    try:
        cur.execute("""
            SELECT 
                COALESCE(pc.product_category_name_en, 'Unknown') as category,
                SUM(oi.order_unit_price * oi.order_quantity) as revenue,
                COUNT(DISTINCT oi.order_item_id) as item_count
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_item_order_id
            JOIN products p ON oi.order_product_id = p.product_id
            JOIN farmer f ON f.farmer_id = p.product_farmer_id
            JOIN users u ON u.user_id = f.farmer_user_id
            LEFT JOIN product_types pt ON p.product_type_id = pt.product_type_id
            LEFT JOIN product_categories pc ON pt.product_type_category_id = pc.product_category_id
            WHERE o.order_date BETWEEN %s AND %s
              AND oi.order_item_status != 'cancelled'
              AND oi.order_item_status = 'completed'
              AND u.user_id = %s
            GROUP BY pc.product_category_name_en
            HAVING SUM(oi.order_unit_price * oi.order_quantity) > 0
            ORDER BY revenue DESC
            LIMIT 10
        """, (start_date, end_date, user_id))
        
        result = cur.fetchall()
        
        if not result:
            return []
        
        total_revenue = sum(float(row['revenue'] or 0) for row in result)
        
        if total_revenue == 0:
            return []
        
        return [
            {
                'category': row['category'], 
                'percentage': round((float(row['revenue'] or 0) / total_revenue * 100), 2),
                'revenue': float(row['revenue'] or 0),
                'items': int(row['item_count'] or 0)
            } 
            for row in result
        ]
    except Exception as e:
        print(f"Error in get_category_performance: {e}")
        return []




def get_monthly_comparison(cur, user_id, months_back=3):
    """Get monthly revenue comparison for the last N months"""
    try:
        interval = f"{months_back} months"
        cur.execute(f"""
            SELECT
                TO_CHAR(o.order_date, 'YYYY-MM') as month_year,
                TO_CHAR(o.order_date, 'Month') as month_name,
                SUM(oi.order_unit_price * oi.order_quantity) as monthly_revenue,
                COUNT(DISTINCT o.order_id) as order_count
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_item_order_id
            JOIN products p ON p.product_id = oi.order_product_id
            JOIN farmer f ON f.farmer_id = p.product_farmer_id
            JOIN users u ON u.user_id = f.farmer_user_id
            WHERE o.order_date >= CURRENT_DATE - INTERVAL '{interval}'
              AND oi.order_item_status != 'cancelled'
              AND oi.order_item_status = 'completed'
              AND u.user_id = '{user_id}'
            GROUP BY TO_CHAR(o.order_date, 'YYYY-MM'), TO_CHAR(o.order_date, 'Month')
            ORDER BY month_year
        """)
        
        result = cur.fetchall()
        
        if not result:
            return []
        
        return [
            {
                'month': row['month_name'].strip()[:3],  # e.g. 'Jul'
                'revenue': float(row['monthly_revenue'] or 0),
                'orders': int(row['order_count'] or 0)
            }
            for row in result
        ]
    except Exception as e:
        print(f"Error in get_monthly_comparison: {e}")
        return []


def get_sales_summary(cur, start_date, end_date):
    """Get overall sales summary statistics"""
    try:
        cur.execute("""
            SELECT 
                SUM(oi.order_unit_price * oi.order_quantity) as total_revenue,
                COUNT(DISTINCT o.order_id) as total_orders,
                COUNT(DISTINCT o.order_buyer_id) as total_customers,
                AVG(oi.order_unit_price * oi.order_quantity) as avg_order_value
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_item_order_id
            WHERE o.order_date BETWEEN %s AND %s
              AND oi.order_item_status != 'cancelled'
        """, (start_date, end_date))
        
        result = cur.fetchone()
        
        if not result:
            return {
                'total_revenue': 0,
                'total_orders': 0,
                'total_customers': 0,
                'avg_order_value': 0
            }
        
        return {
            'total_revenue': float(result['total_revenue'] or 0),
            'total_orders': int(result['total_orders'] or 0),
            'total_customers': int(result['total_customers'] or 0),
            'avg_order_value': float(result['avg_order_value'] or 0)
        }
    except Exception as e:
        print(f"Error in get_sales_summary: {e}")
        return {
            'total_revenue': 0,
            'total_orders': 0,
            'total_customers': 0,
            'avg_order_value': 0
        }



@farmers.route("/farmer/performance-report/export-csv")
@login_required
def export_csv():
    """Export comprehensive farmer performance report to CSV"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # Get date range (default: current month)
        end_date = datetime.now()
        start_date = end_date.replace(day=1)
        
        if request.args.get('start_date'):
            start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d')
        if request.args.get('end_date'):
            end_date = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d')

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write sales summary section
        writer.writerow(["SALES SUMMARY"])
        writer.writerow(["Metric", "Value"])
        
        cur.execute("""
            SELECT 
                COUNT(DISTINCT o.order_id) as total_orders,
                SUM(oi.order_quantity) as total_units_sold,
                SUM(oi.order_quantity * oi.order_unit_price) as total_revenue,
                AVG(oi.order_quantity * oi.order_unit_price) as avg_order_value
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_item_order_id
            JOIN products p ON oi.order_product_id = p.product_id
            JOIN farmer f ON p.product_farmer_id = f.farmer_id
            WHERE o.order_date BETWEEN %s AND %s
                AND f.farmer_user_id = %s
        """, (start_date, end_date, current_user.id))
        sales_summary = cur.fetchone()
        
        writer.writerow(["Total Orders", sales_summary['total_orders']])
        writer.writerow(["Total Units Sold", sales_summary['total_units_sold']])
        writer.writerow(["Total Revenue", f"Ksh {sales_summary['total_revenue']:,.2f}"])
        writer.writerow(["Average Order Value", f"Ksh {sales_summary['avg_order_value']:,.2f}"])
        writer.writerow([])

        # Write top products section
        writer.writerow(["TOP PRODUCTS (BY REVENUE)"])
        writer.writerow(["Product Name", "Units Sold", "Revenue", "Order Count"])
        
        cur.execute("""
            SELECT 
                p.product_name,
                SUM(oi.order_quantity) as units_sold,
                SUM(oi.order_quantity * oi.order_unit_price) as revenue,
                COUNT(DISTINCT o.order_id) as order_count
            FROM products p
            JOIN order_items oi ON p.product_id = oi.order_product_id
            JOIN orders o ON oi.order_item_order_id = o.order_id
            JOIN farmer f ON p.product_farmer_id = f.farmer_id
            WHERE o.order_date BETWEEN %s AND %s
                AND f.farmer_user_id = %s
            GROUP BY p.product_id, p.product_name
            ORDER BY revenue DESC
            LIMIT 10
        """, (start_date, end_date, current_user.id))
        
        for product in cur.fetchall():
            writer.writerow([
                product['product_name'],
                product['units_sold'],
                f"Ksh {product['revenue']:,.2f}",
                product['order_count']
            ])
        writer.writerow([])

        # Write sales trend section
        writer.writerow(["MONTHLY SALES TREND (LAST 12 MONTHS)"])
        writer.writerow(["Month", "Order Count", "Monthly Revenue"])
        
        cur.execute("""
            SELECT 
                TO_CHAR(DATE_TRUNC('month', o.order_date), 'Mon YYYY') as month,
                COUNT(DISTINCT o.order_id) as order_count,
                SUM(oi.order_quantity * oi.order_unit_price) as monthly_revenue
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_item_order_id
            JOIN products p ON oi.order_product_id = p.product_id
            JOIN farmer f ON p.product_farmer_id = f.farmer_id
            WHERE o.order_date BETWEEN %s AND %s
                AND f.farmer_user_id = %s
            GROUP BY DATE_TRUNC('month', o.order_date)
            ORDER BY DATE_TRUNC('month', o.order_date)
        """, (start_date - timedelta(days=365), end_date, current_user.id))
        
        for trend in cur.fetchall():
            writer.writerow([
                trend['month'],
                trend['order_count'],
                f"Ksh {trend['monthly_revenue']:,.2f}"
            ])
        writer.writerow([])

        # Write customer metrics section
        writer.writerow(["CUSTOMER METRICS"])
        writer.writerow(["Metric", "Value"])
        
        cur.execute("""
            SELECT 
                COUNT(DISTINCT o.order_buyer_id) as unique_customers,
                COUNT(DISTINCT CASE WHEN o.order_date >= (CURRENT_DATE - INTERVAL '30 days') 
                    THEN o.order_buyer_id END) as recent_customers,
                COUNT(DISTINCT CASE WHEN EXISTS (
                    SELECT 1 FROM orders o2 
                    WHERE o2.order_buyer_id = o.order_buyer_id
                    AND o2.order_date BETWEEN %s AND %s
                    AND o2.order_date < o.order_date
                ) THEN o.order_buyer_id END) as repeat_customers
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_item_order_id
            JOIN products p ON oi.order_product_id = p.product_id
            JOIN farmer f ON p.product_farmer_id = f.farmer_id
            WHERE o.order_date BETWEEN %s AND %s
                AND f.farmer_user_id = %s
        """, (start_date - timedelta(days=365), start_date, start_date, end_date, current_user.id))
        
        customer_metrics = cur.fetchone()
        writer.writerow(["Unique Customers", customer_metrics['unique_customers']])
        writer.writerow(["Recent Customers (Last 30 Days)", customer_metrics['recent_customers']])
        writer.writerow(["Repeat Customers", customer_metrics['repeat_customers']])
        writer.writerow([])

        # Write order status breakdown
        writer.writerow(["ORDER STATUS BREAKDOWN"])
        writer.writerow(["Status", "Count", "Total Value"])
        
        cur.execute("""
            SELECT 
                oi.order_item_status,
                COUNT(*) as status_count,
                SUM(oi.order_quantity * oi.order_unit_price) as status_value
            FROM order_items oi
            JOIN orders o ON oi.order_item_order_id = o.order_id
            JOIN products p ON oi.order_product_id = p.product_id
            JOIN farmer f ON p.product_farmer_id = f.farmer_id
            WHERE o.order_date BETWEEN %s AND %s
                AND f.farmer_user_id = %s
            GROUP BY oi.order_item_status
        """, (start_date, end_date, current_user.id))
        
        for status in cur.fetchall():
            writer.writerow([
                status['order_item_status'].title(),
                status['status_count'],
                f"Ksh {status['status_value']:,.2f}"
            ])

        # Create response
        output.seek(0)
        response = make_response(output.getvalue())
        filename = f"farmer_performance_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.csv"
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-type"] = "text/csv"
        
        return response

    except Exception as e:
        print(f"Error generating CSV: {str(e)}")
        return jsonify({"error": str(e)}), 500

    finally:
        cur.close()
        release_db_connection(conn)

