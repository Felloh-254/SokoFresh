import os, psycopg2
from flask import Flask, Blueprint, render_template
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from dotenv import load_dotenv
from app.db.db import MONGO_URI, mongo, get_db_connection, release_db_connection
from flask_login import LoginManager, UserMixin
from bson.objectid import ObjectId
from collections import namedtuple
from flask_mail import Mail, Message
from authlib.integrations.flask_client import OAuth


# Loading Environment variables
load_dotenv()

# Mail initializaiton
mail = Mail()

bcrypt = Bcrypt()


class User(UserMixin):
    def __init__(self, user_id, user_email, user_full_name, user_profile_picture=None, user_contacts=None, user_date_of_birth=None, roles=None):
        self.id = user_id
        self.email = user_email
        self.name = user_full_name
        self.profile_picture = user_profile_picture
        self.contact = user_contacts
        self.date_of_birth = user_date_of_birth
        self.roles = roles or []

    def get_id(self):
        return str(self.id)

    def has_role(self, role_name):
        return role_name in self.roles

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")

    # Mail configuration
    app.config['MAIL_SERVER'] = os.getenv("MAIL_SERVER")
    app.config['MAIL_PORT'] = os.getenv("MAIL_PORT")
    app.config['MAIL_USE_TLS'] = os.getenv("MAIL_USE_TLS")
    app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
    app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
    mail.init_app(app)

    # Google OAuth configuration
    app.config['GOOGLE_CLIENT_ID'] = os.getenv("GOOGLE_CLIENT_ID")
    app.config['GOOGLE_CLIENT_SECRET'] = os.getenv("GOOGLE_CLIENT_SECRET")

    # Initialize OAuth
    oauth = OAuth(app)
    google = oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

     # Create uploads folder if it doesn't exist
    UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

    # # MongoDB configuration
    # app.config['MONGO_URI'] = MONGO_URI

    # # Mongo db initialization
    # mongo.init_app(app)

    # # Mongo db indexing
    # with app.app_context():
    #     mongo.db.posts.create_index([("timestamp", -1)])


    # Register blueprints
    from .routes.buyers import buyers
    from .routes.auth import auth
    from .routes.farmers import farmers
    from .routes.helpers import helpers

    app.register_blueprint(buyers)
    app.register_blueprint(auth)
    app.register_blueprint(farmers)
    app.register_blueprint(helpers)


    bcrypt.init_app(app)

    # Seting up Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = "buyers.home"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        conn = get_db_connection()
        if not conn:
            print("Database connection failed!")
            return None

        try:
            cur = conn.cursor()

            # Get user details
            cur.execute('''
                SELECT user_id, user_email, user_full_name, user_profile_picture, user_contacts, user_date_of_birth
                FROM users WHERE user_id = %s;
            ''', (user_id,))
            user_data = cur.fetchone()

            if not user_data:
                return None

            # Get user roles
            cur.execute('''
                SELECT r.role_name FROM user_roles ur
                JOIN roles r ON ur.user_role_role_id = r.role_id
                WHERE ur.user_role_user_id = %s;
            ''', (user_id,))
            roles = [row[0] for row in cur.fetchall()]

            return User(*user_data, roles=roles)

        finally:
            cur.close()
            release_db_connection(conn)
    # Expose google outh globally
    app.oauth = oauth
    app.google = google

    @app.errorhandler(Exception)
    def handle_all_errors(e):
        code = getattr(e, 'code', 500)

        error_titles = {
            400: "Oops — That request was bad",
            403: "Access denied — No sneaking in",
            404: "Oops — The page won't be found",
            500: "Uh-oh — Server’s having a meltdown",
        }

        error_messages = {
            400: "Your browser sent something my server couldn’t digest.",
            403: "Even the database says you’re not allowed here.",
            404: "Looks like the thing you were after took a detour into the void.",
            500: "I promise I didn’t trip over the cable… probably.",
        }

        fun_quotes = {
            400: "Don’t blame me — you clicked it.",
            403: "No entry — velvet ropes and all.",
            404: "Will you never leave me in peace? — 404's dramatic cry.",
            500: "Smoke is coming out of the server… metaphorically.",
        }

        return render_template(
            "/shared/error.html",
            code=code,
            title=error_titles.get(code, "An unexpected error occurred"),
            message=error_messages.get(code, "Something went wrong."),
            fun_quote=fun_quotes.get(code, "Drama intensifies.")
        ), code

    return app
