"""NovaVision Data API: POST /data/image/upload"""

import json
import os
from dataclasses import dataclass
from typing import Optional

import requests

TEST_BASE_URL = "https://alfa.suite.novavision.ai/api"
PROD_BASE_URL = "https://suite.novavision.ai/api"
UPLOAD_PATH = "/data/image/upload"
TIMEOUT = (5, 30)  # (bağlantı, okuma) saniye
MAX_BATCH_LEN = 255
MAX_ERROR_DETAIL_LEN = 300

_JPEG_SIGNATURE = b"\xff\xd8\xff"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class UploadError(Exception):
    """Dataset upload akışında beklenen hata."""


class ConfigError(UploadError):
    """Yapılandırma hatası (yerel)."""


class InvalidImageError(UploadError):
    """Görüntü verisi geçersiz (yerel; API'ye istek gönderilmeden önce)."""


class ApiError(UploadError):
    """API'den dönen veya API iletişimindeki hata."""


@dataclass
class UploadResult:
    batch_name: Optional[str]
    batch_created: bool
    skipped: bool


def normalize_batch_name(value):
    if value is None:
        return None

    name = str(value).strip()
    if not name:
        return None

    if len(name) > MAX_BATCH_LEN:
        raise ConfigError(f"Batch adı {MAX_BATCH_LEN} karakteri aşamaz.")

    return name


def parse_dataset_id(value):
    original_value = value

    try:
        if isinstance(value, str):
            value = value.strip()

            if not value:
                raise ValueError("Dataset ID boş.")

            if value.startswith("{"):
                value = json.loads(value)

        if isinstance(value, dict):
            value = value.get("id_dataset")

        if value is None or isinstance(value, bool):
            raise ValueError("Dataset ID bulunamadı.")

        if isinstance(value, float) and not value.is_integer():
            raise ValueError("Dataset ID tam sayı olmalı.")

        dataset_id = int(value)

        if dataset_id <= 0:
            raise ValueError("Dataset ID pozitif olmalı.")

        return dataset_id

    except (TypeError, ValueError, json.JSONDecodeError) as e:
        raise ConfigError(f"Geçersiz dataset id: {original_value!r}") from e


def detect_content_type(data):
    """Görüntü türünü dosya imzasından belirler; dışarıdan gelen etikete güvenmez."""
    if data.startswith(_JPEG_SIGNATURE):
        return "image/jpeg"
    if data.startswith(_PNG_SIGNATURE):
        return "image/png"
    raise InvalidImageError(
        "Görüntü verisi JPEG veya PNG değil (dosya imzası eşleşmiyor)."
    )


def _extract_error_detail(resp):
    """API hata yanıtından kısa bir açıklama çıkarır; bulunamazsa boş string."""
    try:
        body = resp.json()
    except ValueError:
        return ""

    if not isinstance(body, dict):
        return ""

    for key in ("message", "error", "detail"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:MAX_ERROR_DETAIL_LEN]
    return ""


def upload_image(
    *,
    base_url,
    token,
    workspace_id,
    dataset_id,
    image_bytes,
    content_type=None,  # geriye dönük uyumluluk için; yok sayılır, tür imzadan belirlenir
    batch_name=None,
    timeout=TIMEOUT,
):
    # --- Yerel doğrulamalar (API'ye istek gitmez) ---
    if not token:
        raise ConfigError("Erişim token'ı bulunamadı.")

    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise InvalidImageError("Görüntü verisi boş veya geçersiz.")

    detected_type = detect_content_type(image_bytes)

    if not isinstance(dataset_id, int) or isinstance(dataset_id, bool):
        dataset_id = parse_dataset_id(dataset_id)

    if dataset_id <= 0:
        raise ConfigError("Dataset ID pozitif olmalı.")

    batch_name = normalize_batch_name(batch_name)

    headers = {"Authorization": f"Bearer {token}"}  # token asla loglanmaz
    if workspace_id:
        headers["X-Workspace-Id"] = str(workspace_id)

    ext = "png" if detected_type == "image/png" else "jpg"
    data = {"id_dataset": str(dataset_id)}
    if batch_name:
        data["batch_name"] = batch_name

    # --- API isteği ---
    try:
        resp = requests.post(
            base_url.rstrip("/") + UPLOAD_PATH,
            headers=headers,
            data=data,
            files={"file": (f"frame.{ext}", image_bytes, detected_type)},
            timeout=timeout,
        )
    except requests.Timeout as e:
        raise ApiError("API isteği zaman aşımına uğradı.") from e
    except requests.ConnectionError as e:
        raise ApiError("API'ye bağlanılamadı.") from e
    except requests.RequestException as e:
        raise ApiError(f"İstek hatası: {type(e).__name__}") from e

    # --- HTTP durum kodları ---
    sc = resp.status_code

    if sc == 401:
        raise ApiError("Kimlik doğrulama hatası (HTTP 401).")
    if sc == 403:
        raise ApiError("Yetki hatası (HTTP 403).")
    if sc == 400:
        detail = _extract_error_detail(resp)
        raise ApiError(f"Geçersiz istek (HTTP 400){': ' + detail if detail else ''}")
    if sc == 404:
        detail = _extract_error_detail(resp)
        raise ApiError(
            f"Dataset veya kayıt bulunamadı (HTTP 404){': ' + detail if detail else ''}"
        )
    if sc == 422:
        detail = _extract_error_detail(resp)
        raise ApiError(
            f"Görüntü biçimi desteklenmiyor veya dosya kaydedilemedi (HTTP 422)"
            f"{': ' + detail if detail else ''}"
        )
    if sc >= 400:
        detail = _extract_error_detail(resp)
        raise ApiError(f"API hatası (HTTP {sc}){': ' + detail if detail else ''}")

    # --- Başarılı yanıt (200: zaten mevcut olabilir, 201: eklendi) ---
    try:
        body = resp.json()
    except ValueError as e:
        raise ApiError("API yanıtı JSON değil.") from e

    if not isinstance(body, dict):
        raise ApiError("Beklenmeyen API yanıtı.")

    if body.get("success") is False:
        detail = _extract_error_detail(resp)
        raise ApiError(f"API işlemi başarısız oldu{': ' + detail if detail else '.'}")

    bn = body.get("batch_name")

    return UploadResult(
        batch_name=bn.strip() if isinstance(bn, str) and bn.strip() else None,
        batch_created=bool(body.get("batch_created", False)),
        skipped=bool(body.get("skipped", False)),
    )


def get_credentials(environment=None):
    """
    Kimlik bilgilerini ortam değişkenlerinden okur.

    Beklenen değişkenler:
    NOVAVISION_ACCESS_TOKEN
    NOVAVISION_WORKSPACE_ID
    NOVAVISION_API_BASE_URL

    Base URL belirtilmezse environment değerine göre
    production veya test URL'i kullanılır.
    """
    base = os.environ.get("NOVAVISION_API_BASE_URL")

    if not base:
        base = (
            PROD_BASE_URL
            if str(environment).lower() in ("production", "prod")
            else TEST_BASE_URL
        )

    return (
        os.environ.get("NOVAVISION_ACCESS_TOKEN"),
        os.environ.get("NOVAVISION_WORKSPACE_ID"),
        base,
    )