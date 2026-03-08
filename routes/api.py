from flask import Blueprint, jsonify

from extensions import db
from models import ClothingItem, Outfit
from utils.auth import current_user, login_required

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/fav/<int:iid>', methods=['POST'])
@login_required
def api_fav(iid):
    me = current_user()
    item = me.items.filter_by(id=iid).first()
    if not item:
        return jsonify(error='not found'), 404
    item.is_favorite = not item.is_favorite
    db.session.commit()
    return jsonify(id=item.id, is_favorite=item.is_favorite)


@api_bp.route('/worn/<int:iid>', methods=['POST'])
@login_required
def api_worn(iid):
    me = current_user()
    item = me.items.filter_by(id=iid).first()
    if not item:
        return jsonify(error='not found'), 404
    item.times_worn += 1
    db.session.commit()
    return jsonify(id=item.id, times_worn=item.times_worn)


@api_bp.route('/outfit-worn/<int:oid>', methods=['POST'])
@login_required
def api_outfit_worn(oid):
    me = current_user()
    outfit = me.outfits.filter_by(id=oid).first()
    if not outfit:
        return jsonify(error='not found'), 404
    outfit.times_worn += 1
    db.session.commit()
    return jsonify(id=outfit.id, times_worn=outfit.times_worn)
