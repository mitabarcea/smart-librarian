import os
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext

PWD_CTX = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret")
JWT_ALG    = os.getenv("JWT_ALG", "HS256")
ACCESS_MIN = int(os.getenv("JWT_ACCESS_MIN", "60"))
REFRESH_D  = int(os.getenv("JWT_REFRESH_DAYS", "7"))

def hash_password(pw: str) -> str:
    return PWD_CTX.hash(pw)

def verify_password(pw: str, pw_hash: str) -> bool:
    return PWD_CTX.verify(pw, pw_hash)

def create_access_token(sub: str) -> str:
    exp = datetime.utcnow() + timedelta(minutes=ACCESS_MIN)
    return jwt.encode({"sub": sub, "exp": exp}, JWT_SECRET, algorithm=JWT_ALG)

def create_refresh_token(sub: str) -> str:
    exp = datetime.utcnow() + timedelta(days=REFRESH_D)
    return jwt.encode({"sub": sub, "exp": exp, "typ":"refresh"}, JWT_SECRET, algorithm=JWT_ALG)

def decode_token(token: str):
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
