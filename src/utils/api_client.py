"""NovaVision Data API: POST /data/image/upload"""
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
    """Dataset upload akışında beklenen (raporlanabilir) hata."""


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
        raise ConfigError(f"Batch adı {MAX_BATCH_LEN} karakteri aşamaz.")
    return name


def parse_dataset_id(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ConfigError(f"Geçersiz dataset id: {value!r}")


def upload_image(*, base_url, token, workspace_id, dataset_id, image_bytes,
                 content_type, batch_name=None, timeout=TIMEOUT):
    if not token:
        raise ConfigError("Erişim token'ı bulunamadı.")
    headers = {"Authorization": f"Bearer {token}"}  # token asla loglanmaz
    if workspace_id:
        headers["X-Workspace-Id"] = str(workspace_id)
    ext = "png" if content_type == "image/png" else "jpg"
    data = {"id_dataset": str(dataset_id)}
    if batch_name:
        data["batch_name"] = batch_name
    try:
        resp = requests.post(
            base_url.rstrip("/") + UPLOAD_PATH, headers=headers, data=data,
            files={"file": (f"frame.{ext}", image_bytes, content_type)},
            timeout=timeout,
        )
    except requests.Timeout:
        raise ApiError("API isteği zaman aşımına uğradı.")
    except requests.ConnectionError:
        raise ApiError("API'ye bağlanılamadı.")
    except requests.RequestException as e:
        raise ApiError(f"İstek hatası: {type(e).__name__}")

    sc = resp.status_code
    if sc == 401:
        raise ApiError("Kimlik doğrulama hatası (401).")
    if sc == 403:
        raise ApiError("Yetki hatası (403).")
    if sc in (400, 404, 422):
        raise ApiError(f"Geçersiz istek/dataset/görüntü ({sc}).")
    if sc >= 400:
        raise ApiError(f"API hatası ({sc}).")

    try:
        body = resp.json()
    except ValueError:
        raise ApiError("API yanıtı JSON değil.")
    if not isinstance(body, dict):
        raise ApiError("Beklenmeyen API yanıtı.")
    bn = body.get("batch_name")
    return UploadResult(
        batch_name=bn.strip() if isinstance(bn, str) and bn.strip() else None,
        batch_created=bool(body.get("batch_created", False)),
        skipped=bool(body.get("skipped", False)),
    )


def get_credentials(environment=None):
    """Kimlik bilgileri. VARSAYIM: SDK'da token/workspace için belgelenmiş bir alan
    doğrulanamadı; ortam değişkenlerinden okunur: NOVAVISION_ACCESS_TOKEN,
    NOVAVISION_WORKSPACE_ID, NOVAVISION_API_BASE_URL. Base URL yoksa
    environment 'production' ise prod, değilse test URL'i kullanılır."""
    base = os.environ.get("NOVAVISION_API_BASE_URL")
    if not base:
        base = PROD_BASE_URL if str(environment).lower() in ("production", "prod") else TEST_BASE_URL
    return (os.environ.get("NOVAVISION_ACCESS_TOKEN"),
            os.environ.get("NOVAVISION_WORKSPACE_ID"), base)