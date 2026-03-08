from models import Tag
from extensions import db


def get_tags(raw):
    names = [t.strip().lower() for t in raw.split(',') if t.strip()]
    result = []
    for name in names:
        tag = Tag.query.filter_by(name=name).first()
        if not tag:
            tag = Tag(name=name)
            db.session.add(tag)
        result.append(tag)
    return result
