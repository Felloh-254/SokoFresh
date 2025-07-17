import time
import random
import string
import os
import pytz
from flask_mail import Message
from flask import Blueprint, render_template, url_for, request, redirect, session, jsonify, flash, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
from app.db.db import get_db_connection, release_db_connection
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from app.__init__ import User
from app import mail


# Get the time as per the timezone
nairobi = pytz.timezone("Africa/Nairobi")
now = datetime.now(nairobi)

# Creating the blueprint
auth = Blueprint('auth', __name__, url_prefix='/')


def verified_required(view_func):
	@wraps(view_func)
	def decorated_view(*args, **kwargs):
		if not current_user.is_authenticated:
			return current_app.login_manager.unauthorized()
		return view_func(*args, **kwargs)
	return decorated_view


@auth.route('/login', methods=['GET', 'POST'])
def login():
	if request.is_json:
		data = request.get_json()
		email = data.get("user_email")
		password = data.get("user_password")

		conn = get_db_connection()
		if not conn:
			return jsonify({"message": "Database connection failed!"}), 400

		try:
			cur = conn.cursor()
			cur.execute(
			'''SELECT user_id, user_password, user_email, user_full_name, user_profile_picture
			FROM users
			WHERE user_email = %s''',
			(email,))

			user_data = cur.fetchone()


			if not user_data[1]:
				return jsonify({"message": "Error during Login! Please Try Again Later"}), 400

			cur.execute("SELECT user_role_role_id FROM user_roles WHERE user_role_user_id = %s", (user_data[0],))
			user_roles = [role[0] for role in cur.fetchall()]

			if not user_roles:
				return jsonify({"message": "Error fetching your role. Please contact support team!"}), 400

			if user_data and user_roles and check_password_hash(user_data[1], password):
				# Convert tuple to User object
				user = User(user_data[0], user_data[2], user_data[3], user_data[4])
				login_user(user, remember=True)

				if 2 in user_roles:
				    return jsonify({"redirect_url": "/"})
				elif 1 in user_roles:
				    return jsonify({"redirect_url": "/marketplace"})
				else:
					return jsonify({"message": "An error occurred. Please contact support team"})

			return jsonify({"message": "Invalid email or password!"}), 400

		finally:
			cur.close()
			release_db_connection(conn)
	return render_template('/shared/login.html', user = current_user)


# Signup function
@auth.route('/signup', methods=['GET', 'POST'])
def signup():
	if request.is_json:
		# Get data from the json
		user_info = request.get_json()
		user_email = user_info.get("user_email")
		user_name = user_info.get('user_name')
		user_date_of_birth = user_info.get('user_dob')
		user_contact = [user_info.get('user_contact')]
		user_password = user_info.get('user_password')
		user_confirmation_password = user_info.get('user_confirm_password')

		# Check password length
		if len(user_password) < 8:
			return jsonify({"message": "Password length should not be less than 8"})

		# Check if the passwords match
		if user_password != user_confirmation_password:
			return jsonify({"message": "Passwords do not match!!"}), 400

		if not user_email or not user_password or not user_name:
			return jsonify({"message": "All fields are required"}), 400

		# Generate a password hash for our users
		hashed_password = generate_password_hash(user_password)

		# Generate a verification code and set the expiration time
		verification_code = generate_verification_code()
		verification_code_expires = now + timedelta(hours=1)

		# Establish a connection
		conn = get_db_connection()
		if not conn:
			return jsonify({"message": "Database connection failed!!"}), 400
		
		try:
			cur = conn.cursor()

			# Check if the user already exists
			cur.execute("SELECT user_id FROM users WHERE user_email = %s", (user_email,))
			if cur.fetchone():
				return jsonify({"message": "The email provided is already registered to an account"}), 400

			# Insert into users table
			cur.execute(
				'''INSERT INTO users
				(user_email, user_password, user_full_name, user_contacts, user_date_of_birth)
				VALUES (%s, %s, %s, %s, %s)
				RETURNING user_id''',
				(user_email, hashed_password, user_name, user_contact, user_date_of_birth))

			user_id = cur.fetchone()[0]

			# Insert into account details
			cur.execute(
				'''INSERT INTO account_details
				(account_user_id)
				VALUES (%s)''',
				(user_id,))

			# Check if role exists
			cur.execute("SELECT role_id FROM roles WHERE role_id = 1")
			if not cur.fetchone():
				return jsonify({"message": "Default role not found in roles table!"}), 500

			# Get the default role
			cur.execute("SELECT role_id FROM roles WHERE role_name = 'buyer';")
			role_id = cur.fetchone()[0]

			# Insert into user_roles table
			cur.execute(
				'''INSERT INTO user_roles
				(user_role_user_id, user_role_role_id)
				VALUES (%s, %s)''',
				(user_id, role_id))

			# Insert into account_verification table
			cur.execute(
				'''INSERT INTO account_verification
				(account_verification_user_id, account_verification_code, account_verification_code_expires)
				VALUES(%s, %s, %s)''',
				(user_id, verification_code, verification_code_expires))

			# Set session and commit
			session["user_id"] = user_id
			conn.commit()

			# Send the verification code
			send_verification_code_email(user_email, verification_code)
			return jsonify({
		        "redirect_url": url_for('auth.verify_email'),
		        "user_email": user_email,
		        "message": "Account created successfully. Proceed to email verification."
		    }), 200
		except Exception as e:
			print(f"Error during signup: {e}")

		finally:
			cur.close()
			release_db_connection(conn)	
	return render_template('/shared/signup.html')


@auth.route('/login/google')
def google_login():
	google = current_app.google
	redirect_uri = url_for('auth.google_callback', _external=True)
	return google.authorize_redirect(redirect_uri)


@auth.route('/login/google/callback')
def google_callback():
	google = current_app.google

	try:
		token = google.authorize_access_token()
		resp = google.get('https://openidconnect.googleapis.com/v1/userinfo')
		user_info = resp.json()
	except Exception as e:
		print(f"OAuth error: {e}")
		return jsonify({"message": "Failed to authenticate with Google."}), 500

	email = user_info.get('email')
	name = user_info.get('name', 'Unknown')
	profile_picture = user_info.get('picture')
	google_oauth_id = user_info.get('sub')

	conn = get_db_connection()
	if not conn:
		return jsonify({"message": "Database connection failed!"}), 500

	try:
		cur = conn.cursor()

		# Check if user exists
		cur.execute('''SELECT user_id, user_email, user_full_name, user_profile_picture
			FROM users
			WHERE user_email = %s''',
			(email,))

		user_data = cur.fetchone()

		if not user_data:
			# Insert new Google user
			cur.execute('''
				INSERT INTO users (
					user_email, user_full_name, user_password,
					user_contacts, user_oauth_id, user_profile_picture
				) VALUES (%s, %s, %s, %s, %s, %s)
				RETURNING user_id
			''', (email, name, None, ['Google'], google_oauth_id, profile_picture))

			user_id = cur.fetchone()[0]

			# Insert into account_details
			cur.execute('''
				INSERT INTO account_details (
					account_user_id, account_oauth_provider, account_email_verified
				) VALUES (%s, %s, %s)
			''', (user_id, 'google', True))

			# Assign default role
			cur.execute('''
				INSERT INTO user_roles (
					user_role_user_id, user_role_role_id
				) VALUES (%s, %s)
			''', (user_id, 1))

			conn.commit()
			send_welcome_email(email, name)
		else:
			user_id = user_data[0]

		cur.execute("SELECT user_role_role_id FROM user_roles WHERE user_role_user_id = %s", (user_id,))
		user_roles = [role[0] for role in cur.fetchall()]

		# Log in the user
		user = User(user_id, email, name)
		login_user(user, remember=True)

		if 2 in user_roles:
		    return redirect(url_for("buyers.home"))
		elif 1 in user_roles:
		    return redirect(url_for("buyers.marketplace"))

		else:
			return jsonify({"message": "An error occurred. Please contact support team"})

	except Exception as e:
		print(f"Google login error: {e}")
		return jsonify({"message": "Login failed!"}), 500

	finally:
		cur.close()
		release_db_connection(conn)




@auth.route('/verify_email', methods=['GET', 'POST'])
def verify_email():
	if request.method == 'POST':
		email = request.form.get('email')
		verification_code = request.form.get('verification_code')
		
		conn = get_db_connection()
		if not conn:
			return jsonify({"message": "Database connection failed"})
		
		try:
			cur = conn.cursor()

			# Fetch user and verification info
			cur.execute(
				'''SELECT a.account_verification_id, a.account_verification_user_id, a.account_verification_code, u.user_full_name
				   FROM account_verification a
				   JOIN users u ON u.user_id = a.account_verification_user_id
				   WHERE u.user_email = %s
				   AND a.account_verification_code_expires > NOW()''',
				(email,)
			)

			result = cur.fetchone()

			if not result:
				return jsonify({"message": "No such user exists"})

			verification_id, user_id, stored_code, user_name = result

			if verification_code != stored_code:
				return jsonify({"message": "Invalid verification code"})

			# Mark as verified
			cur.execute(
				'''UPDATE account_verification
				   SET account_verification_code = NULL,
					   account_verification_complete = TRUE
				   WHERE account_verification_user_id = %s''',
				(user_id,)
			)

			cur.execute(
				'''UPDATE account_details
				   SET account_email_verified = TRUE
				   WHERE account_user_id = %s''',
				(user_id,)
			)

			conn.commit()
			send_welcome_email(email, user_name)

			return redirect(url_for('buyers.home'))

		except Exception as e:
			conn.rollback()
			return jsonify({"message": "An error occurred", "error": str(e)})

		finally:
			cur.close()
			release_db_connection(conn)

	# --------- GET method (initial page load with ?email=...) ----------
	elif request.method == 'GET':
		email = request.args.get('email')  # <-- get from URL like ?email=abc@x.com
		return render_template('/shared/verify_email.html', user_email=email)


def generate_verification_code(length=6):
	return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def send_verification_code_email(email, verification_code):
	subject = "One Click Away – Verify Your SokoFresh Account"
	html_content = render_template('shared/verification_code_email.html', verification_code=verification_code)
	send_email(email, subject, html_content)


def send_welcome_email(user_email, user_name):
	subject = "Fresh food, fresh start – Welcome to SokoFresh!"
	html_content = render_template('shared/welcome_email.html', user_name=user_name)
	send_email(user_email, subject, html_content)


def send_email(recipient, subject, html_content):
	msg = Message(subject=subject, sender=current_app.config['MAIL_USERNAME'], recipients=[recipient], html=html_content)
	mail.send(msg)




@auth.route('/logout')
@login_required
def logout():
	logout_user()
	return redirect(url_for('buyers.home'))
