import os
import psycopg2.extras
from flask import Flask, render_template, url_for, request, jsonify, Blueprint, current_app, redirect
from flask_login import login_user, logout_user, login_required, current_user
from app.db.db import get_db_connection, release_db_connection
from werkzeug.utils import secure_filename
from PIL import Image
from app.routes.buyers import safe_int_list


farmers = Blueprint('farmers', __name__, url_prefix='/')


@farmers.route('/farmer/dashboard')
@login_required
def farmers_dashboard():
    return render_template('/farmers/dashboard.html', user=current_user)


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

    print("DEBUG:", farm_size, produce_category, produce_type, farming_methods, availability_schedule, mpesa_number, transport, storage)

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
                product_updated_at = CURRENT_TIMESTAMP
            FROM farmer
            WHERE
                products.product_id = %s
                AND products.product_farmer_id = farmer.farmer_id
                AND farmer.farmer_user_id = %s;
        """

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




@farmers.route("/farmer/orders")
@login_required
def orders():
    return render_template('/farmers/orders.html', user=current_user)


@farmers.route("/farmer/sales-report")
@login_required
def report():
    return render_template('/farmers/sales_report.html', user=current_user)