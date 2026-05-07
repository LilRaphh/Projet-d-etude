from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db

item_tags = db.Table(
    'item_tags',
    db.Column('item_id', db.Integer, db.ForeignKey('clothing_items.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), primary_key=True),
)

outfit_items = db.Table(
    'outfit_items',
    db.Column('outfit_id', db.Integer, db.ForeignKey('outfits.id'), primary_key=True),
    db.Column('item_id', db.Integer, db.ForeignKey('clothing_items.id'), primary_key=True),
)


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(60), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    gender = db.Column(db.String(30), nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('ClothingItem', back_populates='owner', lazy='dynamic', cascade='all, delete-orphan')
    outfits = db.relationship('Outfit', back_populates='owner', lazy='dynamic', cascade='all, delete-orphan')
    user_settings = db.relationship('UserSetting', back_populates='owner', lazy='dynamic', cascade='all, delete-orphan')
    wishlist_items = db.relationship('WishlistItem', back_populates='owner', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class ClothingItem(db.Model):
    __tablename__ = 'clothing_items'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(60), nullable=False, index=True)
    brand = db.Column(db.String(80))
    size = db.Column(db.String(20))
    color = db.Column(db.String(40))
    season = db.Column(db.String(30), index=True)
    condition = db.Column(db.String(30))
    price = db.Column(db.Float)
    notes = db.Column(db.Text)
    is_favorite = db.Column(db.Boolean, default=False, index=True)
    times_worn = db.Column(db.Integer, default=0)
    image_path = db.Column(db.String(255))
    thumb_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Attributs extraits par l'IA locale (Qwen2.5-VL + FashionCLIP)
    ai_subcategory = db.Column(db.String(80))
    ai_style = db.Column(db.String(40))
    ai_formality = db.Column(db.Integer)
    ai_pattern = db.Column(db.String(40))
    ai_material = db.Column(db.String(40))
    ai_fit = db.Column(db.String(20))
    ai_secondary_color = db.Column(db.String(40))
    ai_thickness = db.Column(db.String(20))
    ai_length = db.Column(db.String(20))
    ai_description = db.Column(db.Text)
    ai_analyzed = db.Column(db.Boolean, default=False, index=True)

    __table_args__ = (
        db.Index('ix_clothing_user_category', 'user_id', 'category'),
        db.Index('ix_clothing_user_season', 'user_id', 'season'),
    )

    owner = db.relationship('User', back_populates='items')
    tags = db.relationship('Tag', secondary=item_tags, back_populates='items', lazy='dynamic')
    outfits_rel = db.relationship('Outfit', secondary=outfit_items, back_populates='items')


class Outfit(db.Model):
    __tablename__ = 'outfits'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    occasion = db.Column(db.String(40))
    season = db.Column(db.String(30))
    rating = db.Column(db.Integer)
    generated_image = db.Column(db.String(255))
    ai_prompt = db.Column(db.Text)
    is_favorite = db.Column(db.Boolean, default=False)
    times_worn = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship('User', back_populates='outfits')
    items = db.relationship('ClothingItem', secondary=outfit_items, back_populates='outfits_rel')


class Tag(db.Model):
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), unique=True, nullable=False)
    items = db.relationship('ClothingItem', secondary=item_tags, back_populates='tags', lazy='dynamic')


class ItemEmbedding(db.Model):
    """Stockage local des embeddings FashionCLIP — remplace ChromaDB."""
    __tablename__ = 'item_embeddings'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('clothing_items.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    embedding_json = db.Column(db.Text, nullable=False)   # JSON list[float]
    metadata_json = db.Column(db.Text, nullable=False, default='{}')
    description = db.Column(db.Text, default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('item_id', 'user_id', name='uq_embedding_item_user'),
    )


class WishlistItem(db.Model):
    __tablename__ = 'wishlist_items'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    product_url = db.Column(db.String(500), nullable=False)
    product_json = db.Column(db.Text, nullable=False)
    added_at    = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'product_url', name='uq_wishlist_user_product'),
    )

    owner = db.relationship('User', back_populates='wishlist_items')


class UserSetting(db.Model):
    __tablename__ = 'user_settings'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.Text)

    owner = db.relationship('User', back_populates='user_settings')

    # Clés dont la valeur est chiffrée en base
    ENCRYPTED_KEYS = {'anthropic_key', 'pollinations_key'}

    @classmethod
    def get(cls, user_id, key, default=''):
        row = cls.query.filter_by(user_id=user_id, key=key).first()
        if not row:
            return default
        value = row.value
        if key in cls.ENCRYPTED_KEYS and value:
            from utils.crypto import decrypt
            value = decrypt(value) or default
        return value

    @classmethod
    def set(cls, user_id, key, value):
        if key in cls.ENCRYPTED_KEYS and value:
            from utils.crypto import encrypt
            value = encrypt(value)
        row = cls.query.filter_by(user_id=user_id, key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(cls(user_id=user_id, key=key, value=value))
        db.session.commit()

    @classmethod
    def delete(cls, user_id, key):
        row = cls.query.filter_by(user_id=user_id, key=key).first()
        if row:
            db.session.delete(row)
            db.session.commit()
