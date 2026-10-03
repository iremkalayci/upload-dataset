"""NovaVision Data API: POST /data/image/upload"""

import base64
import os

import requests

TEST_URL = "https://alfa.suite.novavision.ai/api"
PROD_URL = "https://suite.novavision.ai/api"
JPEG = b"\xff\xd8\xff"
PNG = b"\x89PNG\r\n\x1a\n"


def get_credentials(environment=None):
    """Env değişkenleri: NOVAVISION_ACCESS_TOKEN, NOVAVISION_WORKSPACE_ID (ops.),
    NOVAVISION_API_BASE_URL (ops.; yoksa environment=production ise canlı, değilse test)."""
    base = os.environ.get("NOVAVISION_API_BASE_URL")
    if not base:
        base = PROD_URL if str(environment).lower() in ("production", "prod") else TEST_URL
    return (os.environ.get("NOVAVISION_ACCESS_TOKEN"),
            os.environ.get("NOVAVISION_WORKSPACE_ID"), base)


def to_image_bytes(value):
    """inputImage -> JPEG/PNG bytes. JPEG/PNG ise aynen döner, numpy ise JPEG'e çevrilir."""
    if isinstance(value, dict):
        for key in ("image", "frame", "data", "value"):
            if value.get(key) is not None:
                value = value[key]
                break
        else:
            raise ValueError(f"inputImage içinde görüntü bulunamadı, anahtarlar: {list(value)}")

    if isinstance(value, str):  # base64 veya data URI
        value = base64.b64decode(value.split(",", 1)[-1])
    elif hasattr(value, "shape"):  # numpy dizisi
        import cv2
        ok, buf = cv2.imencode(".jpg", value)
        if not ok:
            raise ValueError("Kare JPEG'e çevrilemedi.")
        return buf.tobytes()

    if isinstance(value, (bytearray, memoryview)):
        value = bytes(value)
    if isinstance(value, bytes) and (value.startswith(JPEG) or value.startswith(PNG)):
        return value

    if isinstance(value, bytes):
        desc = f"bytes len={len(value)} ilk_baytlar={value[:8].hex()}"
    else:
        desc = type(value).__name__
    raise ValueError(f"Görüntü JPEG/PNG değil: {desc}")


def upload_image(base_url, token, workspace_id, dataset_id, image_bytes, batch_name=None):
    """Yükler; (http_status, cevap_json_veya_metin) döner. Ağ hatalarında requests istisnası fırlar."""
    headers = {"Authorization": f"Bearer {token}"}
    if workspace_id:
        headers["X-Workspace-Id"] = str(workspace_id)
    data = {"id_dataset": str(dataset_id)}
    if batch_name:
        data["batch_name"] = batch_name

    resp = requests.post(
        base_url.rstrip("/") + "/data/image/upload",
        headers=headers, data=data, files={"file": ("frame", image_bytes)},
        timeout=(5, 30),
    )
    try:
        body = resp.json()
    except ValueError:
        body = resp.text
    return resp.status_code, body