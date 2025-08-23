import os
from flask import Flask, render_template, url_for, request, jsonify, Blueprint, current_app, redirect
from flask_login import login_user, logout_user, login_required, current_user
from app.db.db import get_db_connection, release_db_connection
from werkzeug.utils import secure_filename
from app import mail
from flask_mail import Message
from datetime import datetime

helpers = Blueprint('helpers', __name__, url_prefix='/')

@helpers.route('/settings/update-profile', methods=['POST'])
@login_required
def update_profile():
	conn = None
	cur = None

	try:
		# Get file and form data
		file = request.files.get('user_profile_pic')
		profile_pic_url = None

		if file and file.filename != '':
			filename = secure_filename(file.filename)
			upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
			file.save(upload_path)
			profile_pic_url = url_for('static', filename=f'uploads/{filename}')

		# Get other fields from the form
		full_name = request.form.get("user_full_name")
		contact = [request.form.get("user_contact")]
		dob = request.form.get("user_dob")

		# DB connection
		conn = get_db_connection()
		cur = conn.cursor()

		# Build query
		if profile_pic_url:
			cur.execute("""
				UPDATE users
				SET user_full_name = %s, user_contacts = %s, user_date_of_birth = %s, user_profile_picture = %s
				WHERE user_id = %s
			""", (full_name, contact, dob, profile_pic_url, current_user.id))
		else:
			cur.execute("""
				UPDATE users
				SET user_full_name = %s, user_contacts = %s, user_date_of_birth = %s
				WHERE user_id = %s
			""", (full_name, contact, dob, current_user.id))

		conn.commit()
		return jsonify({"message": "Profile updated successfully!!"}), 200

	except Exception as e:
		print(f"Error updating profile: {e}")
		return jsonify({"error": "Failed to update profile"}), 500

	finally:
		cur.close()
		release_db_connection(conn)


@helpers.route('/settings/delete-account', methods=['POST'])
def delete_account():
    data = request.get_json()
    deletion_reason = data.get('deletion_reason', 'No reason provided');
    user_id = current_user.id
    user_email = current_user.email
    user_name = current_user.name

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        send_deletion_message(user_email, user_name)

        cur.execute('DELETE FROM users WHERE user_id = %s', (user_id, ))
        conn.commit()

        return jsonify({
            "redirect_url": url_for("auth.login"), 
            "message": "Your account has been deleted"
        }), 200
    except Exception as e:
        print(f"Error deleting the account: {e}")
    finally:
        cur.close()
        release_db_connection()


def send_deletion_message(user_email, user_name):
    subject = "Your SokoFresh account has been deleted"
    html_content = render_template(
            'shared/deletion_email.html',
            user_name=user_name,
            current_year=datetime.strftime(datetime.now(), '%Y'))

    send_email(user_email, subject, html_content)


# Getting the product type based on their category
@helpers.route('/api/product-types', methods=['POST'])
def get_product_types():
    data = request.get_json()
    category_ids = data.get("category_ids", [])

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = """
            SELECT product_type_id, product_type_name_en
            FROM product_types
            WHERE product_type_category_id = ANY(%s)
        """
        cur.execute(query, (category_ids,))
        types = cur.fetchall()

        # Return as JSON
        result = [{"id": row[0], "name": row[1]} for row in types]
        return jsonify(result)

    except Exception as e:
        print("Error fetching product types:", e)
        return jsonify([]), 500

    finally:
        cur.close()
        release_db_connection(conn)


# Getting product type based on farmers registered categoory
@helpers.route('/api/my-product-types')
@login_required
def get_farmer_product_types():
	conn = get_db_connection()
	cur = conn.cursor()

	try:
		query = '''
			SELECT 
			    pt.product_type_id, 
			    pt.product_type_name_en,
			    pt.product_type_name_sw, 
			    pt.product_type_name_local,
			    f.farmer_id
			FROM product_types pt
			JOIN farmer f 
			    ON pt.product_type_id = ANY(f.farmer_produce_types)
		    JOIN users u
			    ON u.user_id = f.farmer_user_id
			WHERE f.farmer_user_id = %s
			'''

		cur.execute(query, (current_user.id,))
		types = cur.fetchall()

		# Return a JSON
		result = [{
			"product_id": row[0],
			"name_en": row[1],
			"name_sw": row[2],
			"name_local": row[3],
			"farmer_id": row[4]} for row in types]

		return jsonify(result)
	except Exception as e:
		print(f"Error fetching product types: {e}")
		return jsonify([]), 500
	finally:
		cur.close()
		release_db_connection(conn)


# Function to get the farmer details
@helpers.route('/api/get-farmer-details')
@login_required
def get_farmer_details():
    conn = get_db_connection()
    cur = conn.cursor()

    user_id = current_user.id
    result = {}

    try:
        query = """
            SELECT
                fm.farmer_farm_size_acres,
                fm.farmer_produce_category,
                fm.farmer_produce_types,
                fm.farmer_farming_methods,
                fm.farmer_produce_availability_schedule,
                fm.farmer_mpesa_number,
                fm.farmer_transport_available,
                fm.farmer_storage_available,

                -- Aggregate category names (handle null case)
                COALESCE(
                    (
                        SELECT array_agg(pc.product_category_name_en)
                        FROM product_categories pc
                        WHERE pc.product_category_id = ANY(fm.farmer_produce_category)
                    ), 
                    ARRAY[]::text[]
                ) AS product_category_names_en,

                COALESCE(
                    (
                        SELECT array_agg(pc.product_category_name_sw)
                        FROM product_categories pc
                        WHERE pc.product_category_id = ANY(fm.farmer_produce_category)
                    ),
                    ARRAY[]::text[]
                ) AS product_category_names_sw,

                -- Aggregate product type names (handle null case)
                COALESCE(
                    (
                        SELECT array_agg(pt.product_type_name_en)
                        FROM product_types pt
                        WHERE pt.product_type_id = ANY(fm.farmer_produce_types)
                    ),
                    ARRAY[]::text[]
                ) AS product_type_names_en,

                COALESCE(
                    (
                        SELECT array_agg(pt.product_type_name_sw)
                        FROM product_types pt
                        WHERE pt.product_type_id = ANY(fm.farmer_produce_types)
                    ),
                    ARRAY[]::text[]
                ) AS product_type_names_sw,

                COALESCE(
                    (
                        SELECT array_agg(pt.product_type_name_local)
                        FROM product_types pt
                        WHERE pt.product_type_id = ANY(fm.farmer_produce_types)
                    ),
                    ARRAY[]::text[]
                ) AS product_type_names_local

            FROM farmer fm
            JOIN users u ON u.user_id = fm.farmer_user_id
            WHERE fm.farmer_user_id = %s"""

        cur.execute(query, (user_id,))
        row = cur.fetchone()

        if row:
            result = {
                "farm_size": row[0],
                "produce_category": row[1],
                "produce_types": row[2],  # This contains the IDs
                "produce_farming_methods": row[3],
                "produce_availability": row[4],
                "mpesa_number": row[5],
                "transport": row[6],
                "storage": row[7],
                "category_name_en": row[8],
                "category_name_sw": row[9],
                "produce_name_en": row[10],
                "produce_name_sw": row[11],
                "produce_name_local": row[12]
            }
        
        return jsonify(result)  # Make sure to return JSON
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": "Failed to fetch farmer details"}), 500
    finally:
        cur.close()
        release_db_connection(conn)


@helpers.route('/support')
def support():
	return render_template('/shared/support.html', user=current_user)


@helpers.route('/about-us')
def about_us():
	return render_template('/shared/about.html', user=current_user)


def send_email(recipient, subject, html_content):
    msg = Message(subject=subject, sender=current_app.config['MAIL_USERNAME'], recipients=[recipient], html=html_content)
    mail.send(msg)


@helpers.route('/support/contact', methods=['POST'])
def contact_support():
    data = request.get_json()
    print(data)
    subject = f"Support Request: {data.get('subject')}"
    user_name = data.get('name')
    user_email = data.get('email')
    phone = data.get('phone')
    message = data.get('message')

    # Build email HTML using Jinja template
    html_content = render_template(
        'shared/support_email.html',
        user_name=user_name,
        user_email=user_email,
        phone=phone,
        message=message,
        current_year=datetime.strftime(datetime.now(), '%Y')
    )

    try:
        send_email("felixogweny@gmail.com", subject, html_content)
        return jsonify({"success": True})
    except Exception as e:
        print("Email error:", e)
        return jsonify({"success": False, "error": str(e)})