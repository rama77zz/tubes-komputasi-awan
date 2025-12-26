from flask import session
from app import db  # kalau kamu punya db di app/__init__.py; kalau tidak, hapus baris ini
from app.models import User  # sesuaikan lokasi model kamu

def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return User.query.get(uid)

def require_admin_user():
    u = get_current_user()
    if not u or not getattr(u, "is_admin", False):
        return None
    return u
