from fastapi import APIRouter, Depends, HTTPException, Response, status, Header
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select
from datetime import datetime, timedelta
import hashlib, os, random

from .models import init_db, get_session, User, VerificationCode, CodePurpose
from .security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token
)
from .emailer import send_email

router = APIRouter(prefix="/auth", tags=["auth"])

CODE_EXP_MIN   = int(os.getenv("CODE_EXP_MIN", "15"))
MAX_ATTEMPTS   = int(os.getenv("MAX_CODE_ATTEMPTS", "6"))
DEBUG_CODES    = os.getenv("DEBUG_EMAIL_CODES", "0") == "1"   # <<< enable console codes in dev


# ---------- helpers ----------
def make_code() -> str:
    return f"{random.randint(0, 999999):06d}"

def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()

def email_code_html(app_action: str, code: str):
    return f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
      <h2>Smart Librarian</h2>
      <p>Use this code to {app_action}:</p>
      <p style="font-size:24px;font-weight:700;letter-spacing:4px">{code}</p>
      <p>This code expires in {CODE_EXP_MIN} minutes.</p>
    </div>"""

def issue_tokens(response: Response, email: str):
    access  = create_access_token(email)
    refresh = create_refresh_token(email)
    response.set_cookie("access_token", access,  httponly=True, samesite="lax", max_age=60*60)
    response.set_cookie("refresh_token", refresh, httponly=True, samesite="lax", max_age=60*60*24*7)
    return {"access_token": access, "token_type": "bearer"}

def get_user_by_email(sess: Session, email: str) -> User | None:
    return sess.exec(select(User).where(User.email == email)).first()

def create_code(sess: Session, user: User, purpose: CodePurpose) -> str:
    code = make_code()
    vc = VerificationCode(
        user_id=user.id,
        purpose=purpose,
        code_hash=hash_code(code),
        expires_at=datetime.utcnow() + timedelta(minutes=CODE_EXP_MIN),
    )
    sess.add(vc)
    sess.commit()
    return code

def send_code_mail(user: User, purpose: CodePurpose, code: str, subject: str, action_text: str) -> None:
    """Send the email, and optionally print the raw code to console in dev."""
    if DEBUG_CODES:
        print(f"[DEBUG] Email code for {user.email} [{purpose.value}] = {code}")
    send_email(user.email, subject, email_code_html(action_text, code))

def validate_code(sess: Session, user: User, purpose: CodePurpose, code: str):
    vc = sess.exec(
        select(VerificationCode)
        .where(VerificationCode.user_id == user.id)
        .where(VerificationCode.purpose == purpose)
        .where(VerificationCode.consumed == False)
        .order_by(VerificationCode.created_at.desc())
    ).first()
    if not vc:
        raise HTTPException(400, "No active code. Request a new one.")
    if vc.expires_at < datetime.utcnow():
        raise HTTPException(400, "Code expired.")
    if vc.attempts >= MAX_ATTEMPTS:
        raise HTTPException(429, "Too many attempts.")
    if vc.code_hash != hash_code(code):
        vc.attempts += 1
        sess.add(vc); sess.commit()
        raise HTTPException(400, "Invalid code.")
    vc.consumed = True
    sess.add(vc); sess.commit()


# ---------- schemas ----------
class RegisterReq(BaseModel):
    email: EmailStr
    password: str

class LoginReq(BaseModel):
    email: EmailStr
    password: str

class CodeReq(BaseModel):
    email: EmailStr
    code: str

class ResetReq(BaseModel):
    email: EmailStr

class ResetConfirmReq(BaseModel):
    email: EmailStr
    code: str
    new_password: str

class ChangePwStart(BaseModel):
    pass

class ChangePwConfirm(BaseModel):
    code: str
    current_password: str
    new_password: str


# ---------- routes ----------
@router.on_event("startup")
def _startup():
    init_db()

@router.post("/register")
def register(req: RegisterReq, sess: Session = Depends(get_session)):
    if len(req.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")

    existing = get_user_by_email(sess, req.email)
    if existing:
        if existing.is_verified:
            raise HTTPException(400, "Email already registered.")
        code = create_code(sess, existing, CodePurpose.VERIFY)
        send_code_mail(existing, CodePurpose.VERIFY, code, "Verify your email", "verify your email")
        return {"message": "Code re-sent.", "status": "pending_verification"}

    user = User(email=req.email, password_hash=hash_password(req.password))
    sess.add(user); sess.commit(); sess.refresh(user)

    code = create_code(sess, user, CodePurpose.VERIFY)
    send_code_mail(user, CodePurpose.VERIFY, code, "Verify your email", "verify your email")
    return {"message": "Registered. Check your email for the 6-digit code.", "status": "pending_verification"}

@router.post("/verify")
def verify(req: CodeReq, sess: Session = Depends(get_session)):
    user = get_user_by_email(sess, req.email)
    if not user:
        raise HTTPException(404, "User not found.")
    validate_code(sess, user, CodePurpose.VERIFY, req.code)
    user.is_verified = True
    sess.add(user); sess.commit()
    return {"message": "Email verified. You can log in now."}

@router.post("/login")
def login(req: LoginReq, response: Response, sess: Session = Depends(get_session)):
    user = get_user_by_email(sess, req.email)
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(400, "Invalid credentials.")
    if not user.is_verified:
        raise HTTPException(403, "Email not verified.")
    return issue_tokens(response, user.email)

@router.post("/refresh")
def refresh(response: Response):
    return {"message": "OK"}  # stub

@router.post("/forgot")
def forgot(req: ResetReq, sess: Session = Depends(get_session)):
    user = get_user_by_email(sess, req.email)
    if not user:
        return {"message": "If the email is registered, a code has been sent."}
    code = create_code(sess, user, CodePurpose.RESET)
    send_code_mail(user, CodePurpose.RESET, code, "Reset your password", "reset your password")
    return {"message": "If the email is registered, a code has been sent."}

@router.post("/reset")
def reset(req: ResetConfirmReq, sess: Session = Depends(get_session)):
    user = get_user_by_email(sess, req.email)
    if not user:
        raise HTTPException(404, "User not found.")
    validate_code(sess, user, CodePurpose.RESET, req.code)
    user.password_hash = hash_password(req.new_password)
    sess.add(user); sess.commit()
    return {"message": "Password updated. You can log in now."}

def get_current_user(
    sess: Session = Depends(get_session),
    authorization: str | None = Header(default=None)
):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(401, "Invalid token")
    email = payload.get("sub")
    user = get_user_by_email(sess, email)
    if not user:
        raise HTTPException(401, "User not found")
    return user

@router.post("/change-password/request")
def change_pw_request(user: User = Depends(get_current_user), sess: Session = Depends(get_session)):
    code = create_code(sess, user, CodePurpose.CHPASS)
    send_code_mail(user, CodePurpose.CHPASS, code, "Confirm password change", "confirm your password change")
    return {"message": "A confirmation code was sent to your email."}

@router.post("/change-password/confirm")
def change_pw_confirm(req: ChangePwConfirm, user: User = Depends(get_current_user), sess: Session = Depends(get_session)):
    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(400, "Current password incorrect.")
    validate_code(sess, user, CodePurpose.CHPASS, req.code)
    user.password_hash = hash_password(req.new_password)
    sess.add(user); sess.commit()
    return {"message": "Password changed successfully."}

@router.post("/resend-verify")
def resend_verify(req: ResetReq, sess: Session = Depends(get_session)):
    user = get_user_by_email(sess, req.email)
    if not user:
        return {"message": "If the email is registered, a code has been sent."}
    if user.is_verified:
        return {"message": "Email is already verified."}
    code = create_code(sess, user, CodePurpose.VERIFY)
    send_code_mail(user, CodePurpose.VERIFY, code, "Verify your email", "verify your email")
    return {"message": "Verification code re-sent if the email exists."}
