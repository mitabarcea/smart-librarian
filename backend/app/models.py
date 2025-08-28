from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional, Literal
from sqlmodel import SQLModel, Field, Session, create_engine, select
from pathlib import Path
import os
from typing import Optional
from enum import Enum as PyEnum

APP_DIR   = Path(__file__).resolve().parent
DATA_DIR  = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_URL    = f"sqlite:///{(DATA_DIR / 'auth.db').as_posix()}"

engine = create_engine(DB_URL, echo=False)

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    is_active: bool = True
    is_verified: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class CodePurpose(str, PyEnum):
    VERIFY = "VERIFY_EMAIL"
    RESET  = "RESET_PASSWORD"
    CHPASS = "CHANGE_PASSWORD"

class VerificationCode(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    purpose: CodePurpose = Field(index=True)   # <-- was Literal[...] (remove that)
    code_hash: str
    expires_at: datetime
    attempts: int = 0
    consumed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
class ShelfStatus(str, PyEnum):
    WANT = "WANT"
    READING = "READING"
    READ = "READ"

class BookShelf(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    title: str
    author: Optional[str] = ""
    status: ShelfStatus = Field(default=ShelfStatus.WANT)
    added_at: datetime = Field(default_factory=datetime.utcnow)

class SearchEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    query: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class UserBadge(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    code: str = Field(index=True)
    name: str
    description: str
    awarded_at: datetime = Field(default_factory=datetime.utcnow)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as s:
        yield s