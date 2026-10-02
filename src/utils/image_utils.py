
"""Gelen kareyi doğrulanmış JPEG/PNG baytlarına çevirir."""

import base64
import binascii
import io

from components.UploadDataset.src.utils.api_client import InvalidImageError

_KEYS = ("image", "data", "value", "frame")
_JPEG = b"\xff\xd8\xff"
_PNG = b"\x89PNG\r\n\x1a\n"


def _extract_raw(value):
    if value is None:
        raise InvalidImageError("Görüntü boş.")

    if isinstance(value, dict):
        for key in _KEYS:
            if key in value and value[key] is not None:
                return _extract_raw(value[key])

        raise InvalidImageError(
            f"inputImage içinde görüntü verisi bulunamadı. "
            f"Mevcut anahtarlar: {list(value.keys())}"
        )

    for key in _KEYS:
        if hasattr(value, key):
            candidate = getattr(value, key)
            if candidate is not None and candidate is not value:
                return _extract_raw(candidate)

    return value


def detect_content_type(data: bytes):
    if data.startswith(_JPEG):
        return "image/jpeg"

    if data.startswith(_PNG):
        return "image/png"

    return None


def _encode_numpy(raw):
    try:
        import numpy as np

        array = np.asarray(raw)

        if array.size == 0:
            raise InvalidImageError("NumPy görüntüsü boş.")

        if array.dtype != np.uint8:
            array = np.clip(array, 0, 255).astype(np.uint8)

        try:
            import cv2

            ok, buffer = cv2.imencode(".jpg", array)
            if not ok:
                raise InvalidImageError(
                    "Görüntü JPEG'e kodlanamadı."
                )

            return buffer.tobytes()

        except ImportError:
            from PIL import Image

            output = io.BytesIO()
            Image.fromarray(array).save(output, format="JPEG")
            return output.getvalue()

    except InvalidImageError:
        raise
    except ImportError as exc:
        raise InvalidImageError(
            "NumPy görüntüsünü kodlamak için OpenCV veya Pillow gerekli."
        ) from exc
    except Exception as exc:
        raise InvalidImageError(
            f"Görüntü kodlanamadı: {exc}"
        ) from exc


def image_to_upload_bytes(input_image):
    """(bytes, content_type) döndürür."""
    raw = _extract_raw(input_image)

    if isinstance(raw, (bytearray, memoryview)):
        raw = bytes(raw)

    elif isinstance(raw, str):
        text = raw.strip()

        if text.startswith("data:"):
            if "," not in text:
                raise InvalidImageError("Geçersiz data URI.")

            header, text = text.split(",", 1)

            if not (
                header.lower().startswith("data:image/jpeg")
                or header.lower().startswith("data:image/jpg")
                or header.lower().startswith("data:image/png")
            ):
                raise InvalidImageError(
                    "Data URI JPEG veya PNG olmalı."
                )

        text = "".join(text.split())

        try:
            raw = base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise InvalidImageError(
                "Görüntü geçerli bir Base64 değil."
            ) from exc

    elif hasattr(raw, "shape") and hasattr(raw, "dtype"):
        raw = _encode_numpy(raw)

    else:
        try:
            from PIL import Image

            if isinstance(raw, Image.Image):
                output = io.BytesIO()
                raw.save(output, format="JPEG")
                raw = output.getvalue()

        except ImportError:
            pass
        except Exception as exc:
            raise InvalidImageError(
                f"Pillow görüntüsü dönüştürülemedi: {exc}"
            ) from exc

    if not isinstance(raw, bytes) or not raw:
        raise InvalidImageError(
            "Desteklenmeyen görüntü tipi. "
            f"Gelen veri türü: {type(raw).__name__}"
        )

    content_type = detect_content_type(raw)

    if content_type is None:
        raise InvalidImageError(
            "Yalnızca JPEG ve PNG desteklenir. "
            f"İlk 16 bayt: {raw[:16].hex()}"
        )

    return raw, content_type
