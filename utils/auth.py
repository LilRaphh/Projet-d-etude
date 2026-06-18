import functools
import os
from typing import Optional

from flask import flash, redirect, request, session, url_for

from extensions import db
from models import User, UserSetting


def current_user() -> Optional[User]:
    uid = session.get('user_id')
    return db.session.get(User, uid) if uid else None


def get_uid() -> Optional[int]:
    return session.get('user_id')


def get_api_key(uid: Optional[int] = None) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    if uid is None:
        uid = get_uid()
    return UserSetting.get(uid, "anthropic_key", "") if uid else ""


def login_required(view_func):
    @functools.wraps(view_func)
    def decorated(*args, **kwargs):
        if not current_user():
            flash('Connectez-vous pour continuer.', 'info')
            return redirect(url_for('auth.login', next=request.path))
        return view_func(*args, **kwargs)
    return decorated


def admin_required(view_func):
    @functools.wraps(view_func)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user:
            flash('Connectez-vous pour continuer.', 'info')
            return redirect(url_for('auth.login', next=request.path))
        if not user.is_admin:
            flash('Accès refusé.', 'error')
            return redirect('/')
        return view_func(*args, **kwargs)
    return decorated


def get_ctx():
    user = current_user()
    uid = user.id if user else 0
    loading_gif_file = UserSetting.get(uid, 'loading_gif', '') if uid else ''
    return {
        'app_name': UserSetting.get(uid, 'app_name', 'Wardrobe'),
        'accent': UserSetting.get(uid, 'accent', '#C8956C'),
        'currency': UserSetting.get(uid, 'currency', '€'),
        'me': user,
        'loading_gif': loading_gif_file,
    }
