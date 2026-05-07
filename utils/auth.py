import functools

from flask import flash, redirect, request, session, url_for

from extensions import db
from models import User, UserSetting


def current_user():
    uid = session.get('user_id')
    return db.session.get(User, uid) if uid else None


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
    return {
        'app_name': UserSetting.get(uid, 'app_name', 'Wardrobe'),
        'accent': UserSetting.get(uid, 'accent', '#C8956C'),
        'currency': UserSetting.get(uid, 'currency', '€'),
        'me': user,
    }
