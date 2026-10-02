
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


class UploadError(Exception):
    """Dataset upload akışında beklenen hata."""


class ConfigError(UploadError):
    pass


class InvalidImageError(UploadError):
    pass


class ApiError(UploadError):
    pass


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
        raise ConfigError(
            f"Batch adı {MAX_BATCH_LEN} karakteri aşamaz."
        )

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
        raise ConfigError(
            f"Geçersiz dataset id: {original_value!r}"
        ) from e


def normalize_content_type(content_type):
    if not isinstance(content_type, str):
        raise InvalidImageError(
            f"Geçersiz görüntü türü: {content_type!r}"
        )

    value = content_type.strip().lower().split(";")[0].strip()

    aliases = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "image/jpg": "image/jpeg",
        "image/pjpeg": "image/jpeg",
        "png": "image/png",
    }

    value = aliases.get(value, value)

    if value not in ("image/jpeg", "image/png"):
        raise InvalidImageError(
            f"Desteklenmeyen görüntü türü: {content_type!r}"
        )

    return value


def upload_image(
    *,
    base_url,
    token,
    workspace_id,
    dataset_id,
    image_bytes,
    content_type,
    batch_name=None,
    timeout=TIMEOUT,
):
    if not token:
        raise ConfigError("Erişim token'ı bulunamadı.")

    content_type = normalize_content_type(content_type)

    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise InvalidImageError("Görüntü verisi boş veya geçersiz.")

    if not isinstance(dataset_id, int) or isinstance(dataset_id, bool):
        dataset_id = parse_dataset_id(dataset_id)

    if dataset_id <= 0:
        raise ConfigError("Dataset ID pozitif olmalı.")

    batch_name = normalize_batch_name(batch_name)

    headers = {
        "Authorization": f"Bearer {token}"
    }

    if workspace_id:
        headers["X-Workspace-Id"] = str(workspace_id)

    ext = "png" if content_type == "image/png" else "jpg"

    data = {
        "id_dataset": str(dataset_id)
    }

    if batch_name:
        data["batch_name"] = batch_name

    try:
        resp = requests.post(
            base_url.rstrip("/") + UPLOAD_PATH,
            headers=headers,
            data=data,
            files={
                "file": (
                    f"frame.{ext}",
                    image_bytes,
                    content_type,
                )
            },
            timeout=timeout,
        )

    except requests.Timeout as e:
        raise ApiError(
            "API isteği zaman aşımına uğradı."
        ) from e

    except requests.ConnectionError as e:
        raise ApiError(
            "API'ye bağlanılamadı."
        ) from e

    except requests.RequestException as e:
        raise ApiError(
            f"İstek hatası: {type(e).__name__}"
        ) from e

    sc = resp.status_code

    if sc == 401:
        raise ApiError("Kimlik doğrulama hatası (401).")

    if sc == 403:
        raise ApiError("Yetki hatası (403).")

    if sc in (400, 404, 422):
        try:
            body = resp.json()
            message = body.get("message", "")
        except (ValueError, AttributeError):
            message = ""

        detail = f": {message}" if message else ""

        raise ApiError(
            f"Geçersiz istek/dataset/görüntü ({sc}){detail}"
        )

    if sc >= 400:
        raise ApiError(f"API hatası ({sc}).")

    try:
        body = resp.json()
    except ValueError as e:
        raise ApiError("API yanıtı JSON değil.") from e

    if not isinstance(body, dict):
        raise ApiError("Beklenmeyen API yanıtı.")

    if body.get("success") is False:
        raise ApiError("API işlemi başarısız oldu.")

    bn = body.get("batch_name")

    return UploadResult(
        batch_name=(
            bn.strip()
            if isinstance(bn, str) and bn.strip()
            else None
        ),
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
