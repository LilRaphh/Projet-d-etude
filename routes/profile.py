from flask import Blueprint, flash, redirect, render_template, request

from config import AESTHETICS, BODY_TYPES, BUDGETS, GENDERS
from extensions import db
from models import UserSetting
from utils.auth import current_user, get_ctx, login_required

profile_bp = Blueprint('profile', __name__)

_PROFILE_KEYS = ('display_name', 'bio', 'style_aesthetic', 'body_type', 'style_budget', 'style_notes')


@profile_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    ctx = get_ctx()
    me = ctx['me']

    if request.method == 'POST':
        action = request.form.get('action', 'profile')

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

        else:
            me.gender = request.form.get('gender', '').strip() or None
            db.session.commit()

            for key in _PROFILE_KEYS:
                UserSetting.set(me.id, key, request.form.get(key, '').strip())

            flash('Profil mis à jour !', 'success')

        return redirect('/profile')

    profile_data = {k: UserSetting.get(me.id, k, '') for k in _PROFILE_KEYS}

    return render_template(
        'profile.html',
        genders=GENDERS,
        aesthetics=AESTHETICS,
        body_types=BODY_TYPES,
        budgets=BUDGETS,
        profile=profile_data,
        **ctx,
    )
