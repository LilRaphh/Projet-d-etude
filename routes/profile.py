import secrets
from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, session

from config import AESTHETICS, BUDGETS, GENDERS, SIZES_BY_CATEGORY
from extensions import db
from models import User, UserSetting
from utils.auth import current_user, get_ctx, login_required
from utils.mail import send_email_change_email

profile_bp = Blueprint('profile', __name__)

_ACCOUNT_KEYS = ('display_name', 'bio')
_PREF_KEYS = ('style_aesthetic', 'height', 'weight', 'style_budget', 'style_notes',
              'default_size_top', 'default_size_bottom', 'default_size_shoes')
_PROFILE_KEYS = _ACCOUNT_KEYS + _PREF_KEYS
_PENDING_EMAIL = 'pending_email'
_PENDING_EMAIL_TOKEN = 'pending_email_token'
_PENDING_EMAIL_EXPIRES_AT = 'pending_email_expires_at'
_PENDING_EMAIL_KEYS = (_PENDING_EMAIL, _PENDING_EMAIL_TOKEN, _PENDING_EMAIL_EXPIRES_AT)


def _setting_row(user_id, key):
    return UserSetting.query.filter_by(user_id=user_id, key=key).first()


def _setting_value(user_id, key, default=''):
    row = _setting_row(user_id, key)
    return row.value if row and row.value is not None else default


def _upsert_setting(user_id, key, value):
    row = _setting_row(user_id, key)
    if row:
        row.value = value
    else:
        db.session.add(UserSetting(user_id=user_id, key=key, value=value))


def _clear_pending_email_change(user_id):
    UserSetting.query.filter(
        UserSetting.user_id == user_id,
        UserSetting.key.in_(_PENDING_EMAIL_KEYS),
    ).delete(synchronize_session=False)


def _get_pending_email_change(user_id, clear_expired=True):
    email = _setting_value(user_id, _PENDING_EMAIL, '')
    token = _setting_value(user_id, _PENDING_EMAIL_TOKEN, '')
    expires_raw = _setting_value(user_id, _PENDING_EMAIL_EXPIRES_AT, '')

    if not email or not token or not expires_raw:
        return None

    try:
        expires_at = datetime.fromisoformat(expires_raw)
    except ValueError:
        if clear_expired:
            _clear_pending_email_change(user_id)
            db.session.commit()
        return None

    if expires_at <= datetime.utcnow():
        if clear_expired:
            _clear_pending_email_change(user_id)
            db.session.commit()
        return None

    return {
        'email': email,
        'token': token,
        'expires_at': expires_at,
    }


@profile_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    ctx = get_ctx()
    me = ctx['me']

    if request.method == 'POST':
        action = request.form.get('action', 'account')

        if action == 'password':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            new_pw2 = request.form.get('new_password2', '')

            if not me.check_password(current_pw):
                flash('Mot de passe actuel incorrect.', 'error')
            elif len(new_pw) < 6:
                flash('Nouveau mot de passe trop court (6 car. min.).', 'error')
            elif new_pw != new_pw2:
                flash('Les mots de passe ne correspondent pas.', 'error')
            else:
                me.set_password(new_pw)
                db.session.commit()
                flash('Mot de passe mis à jour !', 'success')
            return redirect('/profile?tab=securite')

        elif action == 'email_change':
            current_pw = request.form.get('email_change_password', '')
            new_email = request.form.get('new_email', '').strip().lower()

            if not me.check_password(current_pw):
                flash('Mot de passe actuel incorrect.', 'error')
            elif not new_email:
                flash('Veuillez saisir une nouvelle adresse email.', 'error')
            elif '@' not in new_email or '.' not in new_email.rsplit('@', 1)[-1]:
                flash('Adresse email invalide.', 'error')
            elif new_email == me.email:
                flash('Cette adresse est déjà celle de votre compte.', 'info')
            elif User.query.filter(User.email == new_email, User.id != me.id).first():
                flash('Cette adresse email est déjà utilisée.', 'error')
            else:
                token = secrets.token_urlsafe(32)
                expires_at = datetime.utcnow() + timedelta(hours=24)
                _upsert_setting(me.id, _PENDING_EMAIL, new_email)
                _upsert_setting(me.id, _PENDING_EMAIL_TOKEN, token)
                _upsert_setting(me.id, _PENDING_EMAIL_EXPIRES_AT, expires_at.isoformat())
                db.session.commit()

                if send_email_change_email(me, new_email, token, request.host_url):
                    flash(f'Un email de confirmation a été envoyé à {new_email}.', 'success')
                else:
                    _clear_pending_email_change(me.id)
                    db.session.commit()
                    flash("Impossible d'envoyer l'email de confirmation. Vérifiez la configuration mail.", 'error')
            return redirect('/profile?tab=securite')

        elif action == 'cancel_email_change':
            if _get_pending_email_change(me.id):
                _clear_pending_email_change(me.id)
                db.session.commit()
                flash("La demande de changement d'email a été annulée.", 'info')
            else:
                flash("Aucun changement d'email en attente.", 'info')
            return redirect('/profile?tab=securite')

        elif action == 'resend_email_change':
            pending = _get_pending_email_change(me.id)
            if not pending:
                flash("Aucun changement d'email en attente.", 'info')
            elif send_email_change_email(me, pending['email'], pending['token'], request.host_url):
                flash(f"Un nouvel email de confirmation a été envoyé à {pending['email']}.", 'success')
            else:
                flash("Impossible de renvoyer l'email de confirmation.", 'error')
            return redirect('/profile?tab=securite')

        elif action == 'delete_account':
            confirm = request.form.get('confirm_delete', '')
            if confirm == me.username:
                db.session.delete(me)
                db.session.commit()
                session.clear()
                flash('Votre compte a été supprimé.', 'info')
                return redirect('/login')
            else:
                flash('Confirmation incorrecte — tapez exactement votre nom d\'utilisateur.', 'error')
            return redirect('/profile?tab=securite')

        elif action == 'preferences':
            me.gender = request.form.get('gender', '').strip() or None
            db.session.commit()
            for key in _PREF_KEYS:
                UserSetting.set(me.id, key, request.form.get(key, '').strip())
            flash('Préférences mises à jour !', 'success')
            return redirect('/profile?tab=preferences')

        else:  # account
            for key in _ACCOUNT_KEYS:
                UserSetting.set(me.id, key, request.form.get(key, '').strip())
            flash('Profil mis à jour !', 'success')
            return redirect('/profile?tab=compte')

    active_tab = request.args.get('tab', 'compte')
    if active_tab not in ('compte', 'preferences', 'securite'):
        active_tab = 'compte'

    profile_data = {k: UserSetting.get(me.id, k, '') for k in _PROFILE_KEYS}
    pending_email_change = _get_pending_email_change(me.id)

    return render_template(
        'profile.html',
        genders=GENDERS,
        aesthetics=AESTHETICS,
        budgets=BUDGETS,
        profile=profile_data,
        pending_email_change=pending_email_change,
        active_tab=active_tab,
        sizes_top=SIZES_BY_CATEGORY.get('Hauts', []),
        sizes_bottom=SIZES_BY_CATEGORY.get('Pantalons', []),
        sizes_shoes=SIZES_BY_CATEGORY.get('Chaussures', []),
        **ctx,
    )


@profile_bp.route('/confirm-email-change/<token>')
def confirm_email_change(token):
    token_row = UserSetting.query.filter_by(key=_PENDING_EMAIL_TOKEN, value=token).first()
    if not token_row:
        flash("Ce lien de changement d'email est invalide ou expiré.", 'error')
        return redirect('/login')

    user = db.session.get(User, token_row.user_id)
    if not user:
        flash("Le compte associé à cette demande n'existe plus.", 'error')
        return redirect('/login')

    pending = _get_pending_email_change(user.id)
    if not pending or pending['token'] != token:
        flash("Ce lien de changement d'email est invalide ou expiré.", 'error')
        return redirect('/login')

    if User.query.filter(User.email == pending['email'], User.id != user.id).first():
        _clear_pending_email_change(user.id)
        db.session.commit()
        flash("Cette adresse email est déjà utilisée par un autre compte.", 'error')
        return redirect('/profile?tab=securite' if current_user() and current_user().id == user.id else '/login')

    user.email = pending['email']
    user.email_verified = True
    _clear_pending_email_change(user.id)
    db.session.commit()
    flash('Votre adresse email a bien été mise à jour.', 'success')

    if current_user() and current_user().id == user.id:
        return redirect('/profile?tab=securite')
    return redirect('/login')
