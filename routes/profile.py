from flask import Blueprint, flash, redirect, render_template, request, session

from config import AESTHETICS, BUDGETS, GENDERS
from extensions import db
from models import UserSetting
from utils.auth import current_user, get_ctx, login_required

profile_bp = Blueprint('profile', __name__)

_ACCOUNT_KEYS = ('display_name', 'bio')
_PREF_KEYS = ('style_aesthetic', 'height', 'weight', 'style_budget', 'style_notes')
_PROFILE_KEYS = _ACCOUNT_KEYS + _PREF_KEYS


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

    return render_template(
        'profile.html',
        genders=GENDERS,
        aesthetics=AESTHETICS,
        budgets=BUDGETS,
        profile=profile_data,
        active_tab=active_tab,
        **ctx,
    )
