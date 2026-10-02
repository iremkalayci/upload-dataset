"""
NovaVision Data API istemcisi: POST /data/image/upload
"""

import json
import os
import requests

# python-dotenv ortamda varsa .env dosyasını otomatik yükler, yoksa çökmez
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TEST_BASE_URL = "https://alfa.suite.novavision.ai/api"
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class ApiClientError(Exception):
    """API ve doğrulama süreçlerinde oluşan kontrollü hata."""


def parse_dataset_id(val):
    """Dataset Picker'dan gelen int, string veya JSON dict değerinden pozitif int ID çıkarır."""
    if val is None:
        raise ApiClientError("Dataset ID boş olamaz.")

    if isinstance(val, dict):
        val = val.get("id_dataset")
    elif isinstance(val, str):
        val = val.strip()
        if val.startswith("{"):
            try:
                val = json.loads(val).get("id_dataset")
            except Exception as e:
                raise ApiClientError(f"Dataset JSON parse edilemedi: {e}") from e

    try:
        dataset_id = int(val)
        if dataset_id <= 0:
            raise ValueError
        return dataset_id
    except (TypeError, ValueError) as exc:
        raise ApiClientError(f"Geçersiz Dataset ID: {val!r}") from exc


def inspect_image(image_bytes):
    """Görüntü baytlarının geçerli JPEG veya PNG olduğunu doğrular, uzantı ve MIME türü belirler."""
    if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
        raise ApiClientError("Görüntü verisi boş veya bayt formatında değil.")

    raw = bytes(image_bytes)
    if raw.startswith(JPEG_MAGIC):
        return raw, "image/jpeg", "jpg"
    if raw.startswith(PNG_MAGIC):
        return raw, "image/png", "png"

    raise ApiClientError(
        "Desteklenmeyen görüntü formatı. Yalnızca JPEG veya PNG kabul edilir."
    )


def upload_image(dataset_id, image_bytes, batch_name=None):
    """Görüntüyü Data API'ye multipart/form-data olarak yükler."""
    token = os.getenv("NOVAVISION_ACCESS_TOKEN")
    if not token:
        raise ApiClientError("NOVAVISION_ACCESS_TOKEN ortam değişkeni eksik.")

    base_url = os.getenv("NOVAVISION_API_BASE_URL", TEST_BASE_URL).rstrip("/")
    workspace_id = os.getenv("NOVAVISION_WORKSPACE_ID")

    raw_bytes, mime_type, ext = inspect_image(image_bytes)

    headers = {"Authorization": f"Bearer {token.strip()}"}
    if workspace_id:
        headers["X-Workspace-Id"] = str(workspace_id).strip()

    data = {"id_dataset": str(dataset_id)}
    if batch_name and str(batch_name).strip():
        data["batch_name"] = str(batch_name).strip()

    files = {"file": (f"frame.{ext}", raw_bytes, mime_type)}
    url = f"{base_url}/data/image/upload"

    try:
        resp = requests.post(url, headers=headers, data=data, files=files, timeout=30)
    except requests.RequestException as e:
        raise ApiClientError(f"Ağ veya bağlantı hatası: {e}") from e

    try:
        body = resp.json()
    except Exception:
        body = {}

    if not resp.ok:
        err_msg = body.get("message") or resp.text
        raise ApiClientError(f"API Hatası (HTTP {resp.status_code}): {err_msg}")

    return body