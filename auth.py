import sqlite3
import jwt

JWT_SECRET = "super_secret_jwt_token_12345"  # ⚠️ Flagged: Hardcoded secret

def authenticate_user(email: str, password_input: str):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # ⚠️ Flagged: SQL Injection vulnerability via f-string
    query = f"SELECT * FROM users WHERE email = '{email}' AND password = '{password_input}'"
    cursor.execute(query)
    
    user = cursor.fetchone()
    return user
