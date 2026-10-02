"""Gelen kareyi doğrulanmış JPEG/PNG baytlarına çevirir.

VARSAYIM (repo'dan doğrulanamadı): `inputImage` değeri bir dict'tir ve görüntü
şu anahtarlardan birinde bulunur: image / data / value / frame. Görüntü; bytes,
base64 str (data-URI olabilir) veya numpy dizisi olabilir. SDK'nın gerçek formatı
farklıysa yalnızca `_extract_raw` değiştirilmelidir.
"""
import base64
import binascii

from components.UploadDataset.src.utils.api_client import InvalidImageError

_KEYS = ("image", "data", "value", "frame")
_JPEG = b"\xff\xd8\xff"
_PNG = b"\x89PNG\r\n\x1a\n"


def _extract_raw(value):
    if isinstance(value, dict):
        for k in _KEYS:
            if value.get(k) is not None:
                return value[k]
        raise InvalidImageError("inputImage içinde görüntü verisi bulunamadı.")
    return value


def detect_content_type(data: bytes):
    if data.startswith(_JPEG):
        return "image/jpeg"
    if data.startswith(_PNG):
        return "image/png"
    return None


def image_to_upload_bytes(input_image):
    """(bytes, content_type) döndürür; geçersizse InvalidImageError fırlatır."""
    raw = _extract_raw(input_image)
    if raw is None:
        raise InvalidImageError("Görüntü boş.")

    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("data:") and "," in text:
            text = text.split(",", 1)[1]
        try:
            raw = base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError):
            raise InvalidImageError("Görüntü geçerli bir base64 değil.")
    elif hasattr(raw, "shape") and hasattr(raw, "dtype"):  # numpy dizisi
        try:
            import cv2
            ok, buf = cv2.imencode(".jpg", raw)
        except Exception as e:
            raise InvalidImageError(f"Görüntü kodlanamadı: {e}")
        if not ok:
            raise InvalidImageError("Görüntü JPEG'e kodlanamadı.")
        raw = buf.tobytes()
    elif isinstance(raw, (bytearray, memoryview)):
        raw = bytes(raw)

    if not isinstance(raw, bytes) or not raw:
        raise InvalidImageError("Desteklenmeyen görüntü tipi.")
    ctype = detect_content_type(raw)
    if ctype is None:
        raise InvalidImageError("Yalnızca JPEG ve PNG desteklenir.")
    return raw, ctype