from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request

from extensions import db
from models import ClothingItem, Outfit, User, WishlistItem
from utils.auth import admin_required, get_ctx

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/')
@admin_required
def dashboard():
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    stats = {
        'users': User.query.count(),
        'items': ClothingItem.query.count(),
        'outfits': Outfit.query.count(),
        'admins': User.query.filter_by(is_admin=True).count(),
        'verified': User.query.filter_by(email_verified=True).count(),
        'active_30d': User.query.filter(User.last_login_at >= thirty_days_ago).count(),
        'wishlist': WishlistItem.query.count(),
    }
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    return render_template('admin/dashboard.html', stats=stats, recent_users=recent_users, **get_ctx())


@admin_bp.route('/users')
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', all_users=all_users, **get_ctx())


@admin_bp.route('/users/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    me = get_ctx()['me']
    if me.id == user_id:
        flash("Vous ne pouvez pas modifier votre propre rôle.", 'error')
        return redirect('/admin/users')
    user = db.session.get(User, user_id)
    if not user:
        flash('Utilisateur introuvable.', 'error')
        return redirect('/admin/users')
    user.is_admin = not user.is_admin
    db.session.commit()
    status = 'administrateur' if user.is_admin else 'utilisateur'
    flash(f'{user.username} est maintenant {status}.', 'success')
    return redirect('/admin/users')


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('Utilisateur introuvable.', 'error')
        return redirect('/admin/users')
    new_pw = request.form.get('password', '').strip()
    if len(new_pw) < 6:
        flash('Mot de passe trop court (6 car. min.).', 'error')
        return redirect('/admin/users')
    user.set_password(new_pw)
    db.session.commit()
    flash(f'Mot de passe de {user.username} mis à jour.', 'success')
    return redirect('/admin/users')


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    me = get_ctx()['me']
    if me.id == user_id:
        flash("Vous ne pouvez pas supprimer votre propre compte.", 'error')
        return redirect('/admin/users')
    user = db.session.get(User, user_id)
    if not user:
        flash('Utilisateur introuvable.', 'error')
        return redirect('/admin/users')
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'Compte de {username} supprimé.', 'success')
    return redirect('/admin/users')
