"""NovaVision Data API istemcisi: POST /data/image/upload."""

import json
import os

import requests

TEST_URL = "https://alfa.suite.novavision.ai/api"
PROD_URL = "https://suite.novavision.ai/api"
TIMEOUT = (5, 30)  # (bağlantı, okuma) saniye
JPEG_QUALITY = 95


def get_credentials(environment=None):
    base = os.environ.get("WEB_API")
    if not base:
        base = (
            PROD_URL
            if str(environment).lower() in ("production", "prod")
            else TEST_URL
        )

    return (
        os.environ.get("DEVICE_ACCESS_TOKEN"),
        os.environ.get("NOVAVISION_WORKSPACE_ID"),
        base,
    )


def parse_dataset_id(value):
    """DatasetPicker değerinden id_dataset'i çıkarır.

    Kabul edilenler:
    '{"id_dataset":6,"name":"abc",...}' (JSON metni),
    dict, sayı veya sayı metni.
    """
    if isinstance(value, str) and value.strip().startswith("{"):
        value = json.loads(value)

    if isinstance(value, dict):
        value = value["id_dataset"]

    dataset_id = int(value)

    if dataset_id <= 0:
        raise ValueError("dataset id pozitif olmalı")

    return dataset_id


def frame_to_jpeg(frame):
    """SDK'nın get_frame ile verdiği kareyi JPEG baytlarına çevirir."""
    from io import BytesIO

    import numpy as np
    from PIL import Image as PILImage

    arr = np.asarray(frame).astype(np.uint8)

    if arr.ndim == 3:
        if arr.shape[2] == 1:
            arr = arr[..., 0]
        else:
            arr = arr[..., 2::-1]  # BGR(A) -> RGB

    buf = BytesIO()
    PILImage.fromarray(arr).save(
        buf,
        format="JPEG",
        quality=JPEG_QUALITY,
    )

    return buf.getvalue()


def upload_image(
    base_url,
    token,
    workspace_id,
    dataset_id,
    image_bytes,
    batch_name=None,
):
    """Görseli yükler; (http_status, cevap_json_veya_metin) döner."""

    headers = {
        "Authorization": f"Bearer {token}",
    }

    if workspace_id:
        headers["X-Workspace-Id"] = str(workspace_id)

    data = {
        "id_dataset": str(dataset_id),
    }

    if batch_name:
        data["batch_name"] = batch_name

    resp = requests.post(
        base_url.rstrip("/") + "/data/image/upload",
        headers=headers,
        data=data,
        files={
            "file": (
                "frame.jpg",
                image_bytes,
                "image/jpeg",
            )
        },
        timeout=TIMEOUT,
    )

    try:
        body = resp.json()
    except ValueError:
        body = resp.text

    return resp.status_code, body