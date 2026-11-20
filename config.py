"""
Config module for Prosfora Gift Shop POS System.
Stores environment settings, database credentials, and security configurations.
"""

import os

# Base directory of the project
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Application configuration parameters."""
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get('SECRET_KEY', 'prosfora_gift_shop_super_secret_key_2026')
    
    # PostgreSQL Database connection parameters
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '5432')
    DB_NAME = os.environ.get('DB_NAME', 'prosfora_db')
    DB_USER = os.environ.get('DB_USER', 'postgres')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres')
    
    # File upload configurations
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 Megabytes max
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    # Session configuration
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
