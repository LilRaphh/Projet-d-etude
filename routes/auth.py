from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

from flask import Blueprint, flash, redirect, render_template, request, session

from extensions import db, limiter
from models import EmailVerificationToken, PasswordResetToken, User
from utils.auth import current_user, get_ctx
from utils.mail import send_reset_email, send_verification_email

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
            row = EmailVerificationToken.create_for(user)
            send_verification_email(user, row.token, request.host_url)
            flash(f'Bienvenue, {user.username} ! Un email de confirmation a été envoyé.', 'success')
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
            remember = request.form.get('remember') == '1'
            session.permanent = remember  # True = 30 j, False = expire à la fermeture du navigateur
            session['user_id'] = user.id
            user.last_login_at = datetime.utcnow()
            user.last_login_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
            db.session.commit()
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


@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    row = EmailVerificationToken.query.filter_by(token=token).first()
    if not row or not row.is_valid():
        flash('Ce lien est invalide ou a expiré.', 'error')
        return redirect('/')
    row.user.email_verified = True
    row.used = True
    db.session.commit()
    flash('Email confirmé ! Votre compte est activé.', 'success')
    return redirect('/')


@auth_bp.route('/resend-verification')
def resend_verification():
    user = current_user()
    if not user:
        return redirect('/login')
    if user.email_verified:
        flash('Votre email est déjà confirmé.', 'info')
        return redirect('/')
    row = EmailVerificationToken.create_for(user)
    send_verification_email(user, row.token, request.host_url)
    flash('Email de confirmation renvoyé.', 'info')
    return redirect('/')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def forgot_password():
    if current_user():
        return redirect('/')

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            row = PasswordResetToken.create_for(user)
            base_url = request.host_url
            send_reset_email(user, row.token, base_url)
        # Message identique que l'email existe ou non (anti-énumération)
        flash('Si cet email existe, un lien de réinitialisation a été envoyé.', 'info')
        return redirect('/login')

    return render_template('forgot_password.html', **get_ctx())


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user():
        return redirect('/')

    row = PasswordResetToken.query.filter_by(token=token).first()
    if not row or not row.is_valid():
        flash('Ce lien est invalide ou a expiré.', 'error')
        return redirect('/forgot-password')

    if request.method == 'POST':
        new_pw = request.form.get('password', '')
        new_pw2 = request.form.get('password2', '')

        if len(new_pw) < 6:
            flash('Mot de passe trop court (6 car. min.).', 'error')
        elif new_pw != new_pw2:
            flash('Les mots de passe ne correspondent pas.', 'error')
        else:
            row.user.set_password(new_pw)
            row.used = True
            db.session.commit()
            flash('Mot de passe réinitialisé. Vous pouvez vous connecter.', 'success')
            return redirect('/login')

    return render_template('reset_password.html', token=token, **get_ctx())
