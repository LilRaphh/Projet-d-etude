from urllib.parse import urljoin, urlparse

from flask import Blueprint, flash, redirect, render_template, request, session

from extensions import db, limiter
from models import User
from utils.auth import current_user, get_ctx

auth_bp = Blueprint('auth', __name__)


def _is_safe_redirect_target(target):
    if not target:
        return False
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ('http', 'https') and ref.netloc == test.netloc


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour")
def register():
    if current_user():
        return redirect('/')

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        if not all([username, email, password]):
            flash('Tous les champs sont obligatoires.', 'error')
        elif len(password) < 6:
            flash('Mot de passe trop court (6 car. min.).', 'error')
        elif password != password2:
            flash('Les mots de passe ne correspondent pas.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Email déjà utilisé.', 'error')
        elif User.query.filter_by(username=username).first():
            flash("Nom d'utilisateur déjà pris.", 'error')
        else:
            user = User(email=email, username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            session['user_id'] = user.id
            flash(f'Bienvenue, {user.username} !', 'success')
            return redirect('/')

        return render_template('register.html', prefill_u=username, prefill_e=email, **get_ctx())

    return render_template('register.html', prefill_u='', prefill_e='', **get_ctx())


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 30 per hour")
def login():
    if current_user():
        return redirect('/')

    if request.method == 'POST':
        login_value = request.form.get('login', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=login_value.lower()).first() or User.query.filter_by(username=login_value).first()

        if user and user.check_password(password):
            session.permanent = True
            session['user_id'] = user.id
            flash(f'Ravi de vous revoir, {user.username} !', 'success')
            next_url = request.args.get('next')
            return redirect(next_url if _is_safe_redirect_target(next_url) else '/')

        flash('Identifiants incorrects.', 'error')
        return render_template('login.html', prefill=login_value, **get_ctx())

    return render_template('login.html', prefill='', **get_ctx())


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Déconnecté.', 'info')
    return redirect('/')
