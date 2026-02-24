import os
import psycopg2
from psycopg2 import pool
from flask_pymongo import PyMongo
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initializing the postgre connection pool
DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
)

try:
    postgres_pool = pool.SimpleConnectionPool(
        1,
        10,
        dsn=DATABASE_URL,
        sslmode="require"
    )
    print("PostgreSQL connection pool created")
except Exception as e:
    print("Error creating PostgreSQL connection pool:", e)
    postgres_pool = None

# Function to get a PostgreSQL connection
def get_db_connection():
    if postgres_pool:
        return postgres_pool.getconn()
    else:
        print("No database connection available!")
        return None

# Function to release the PostgreSQL connection
def release_db_connection(conn):
    if conn and postgres_pool:
        postgres_pool.putconn(conn)

# MongoDB Setup
DB_NAME = "sokofresh"
MONGO_URI = f"mongodb://localhost:27017/{DB_NAME}"
mongo = PyMongo()
