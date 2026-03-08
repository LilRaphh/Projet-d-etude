import os
import uuid

from PIL import Image, ImageOps

from config import ALLOWED_EXT, BASE_DIR, THUMB_FOLDER, THUMB_SIZE, UPLOAD_FOLDER


def allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


def save_image(file_obj):
    if not file_obj or not file_obj.filename or not allowed(file_obj.filename):
        return None, None

    ext = file_obj.filename.rsplit('.', 1)[1].lower()
    name = f'{uuid.uuid4().hex}.{ext}'

    img = Image.open(file_obj.stream)
    img = ImageOps.exif_transpose(img)

    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(THUMB_FOLDER, exist_ok=True)

    img.save(os.path.join(UPLOAD_FOLDER, name), optimize=True, quality=88)

    thumb = ImageOps.fit(img.convert('RGB'), THUMB_SIZE, Image.LANCZOS)
    thumb.save(os.path.join(THUMB_FOLDER, name), optimize=True, quality=82)

    return f'uploads/{name}', f'uploads/thumbs/{name}'


def delete_images(item):
    for rel in (item.image_path, item.thumb_path):
        if rel:
            path = os.path.join(BASE_DIR, 'static', rel)
            if os.path.isfile(path):
                os.remove(path)
