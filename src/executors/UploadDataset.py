"""
Upload Dataset: VideoFeed karelerini seçip API'ye yükler.
"""

import base64
import logging
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../"))

from sdks.novavision.src.base.component import Component
from sdks.novavision.src.helper.executor import Executor

from components.UploadDataset.src.utils.response import build_response
from components.UploadDataset.src.models.PackageModel import PackageModel
from components.UploadDataset.src.utils.api_client import (
    ApiClientError,
    parse_dataset_id,
    upload_image,
)
from components.UploadDataset.src.utils.sampler import (
    FrameState,
    parse_interval,
)

logger = logging.getLogger(__name__)


def extract_raw_bytes(payload):
    """inputImage içinden re-encode yapmadan doğrudan baytları ayıklar."""
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)

    if isinstance(payload, dict):
        for key in ("data", "bytes", "image", "frame", "buffer", "file"):
            val = payload.get(key)
            if isinstance(val, (bytes, bytearray)):
                return bytes(val)
            if isinstance(val, str) and val.strip():
                try:
                    raw_str = val.split(",", 1)[1] if "," in val else val
                    return base64.b64decode(raw_str)
                except Exception:
                    continue

    raise ApiClientError(
        f"inputImage içinden geçerli bayt verisi çıkarılamadı. Veri tipi: {type(payload)}"
    )


class UploadDataset(Component):
    def __init__(self, request, bootstrap):
        super().__init__(request, bootstrap)
        self.request.model = PackageModel(**self.request.data)

        # Girdi verisi
        self.input_image = self.request.get_param("inputImage")

        # ConfigDataset: Pydantic field 'dataset' veya config adı 'configDataset'
        self.dataset = (
            self.request.get_param("dataset")
            or self.request.get_param("configDataset")
        )

        # ConfigFrameInterval: Pydantic field 'frameInterval' veya config adı 'FrameInterval'
        self.frame_interval = parse_interval(
            self.request.get_param("frameInterval")
            or self.request.get_param("FrameInterval")
        )

        # ConfigBatchName: Pydantic field 'batchName' veya config adı 'BatchName'
        self.batch_name_config = (
            self.request.get_param("batchName")
            or self.request.get_param("BatchName")
            or ""
        ).strip()

        # Akışta giriş görüntüsü bozulmadan korunur (response.py ile tam uyum)
        self.result = self.input_image
        self.upload_status = "not_run"

    @staticmethod
    def bootstrap(config: dict) -> dict:
        return {}

   def run(self):
        try:
            state = FrameState(self.redis_db.r, self.flowUID, self.matchedID)

            # Kare örnekleme aralığında değilse API çağrısı yapmadan akışı devam ettir
            if not state.should_select(self.frame_interval):
                self.upload_status = "skipped_frame"
                return build_response(context=self)

            # Gelen dict'in yapısını loga dök
            if isinstance(self.input_image, dict):
                logger.error("DEBUG INPUT_IMAGE KEYS: %s", list(self.input_image.keys()))
                logger.error("DEBUG INPUT_IMAGE DATA: %s", str(self.input_image)[:300])

            dataset_id = parse_dataset_id(self.dataset)
            image_bytes = extract_raw_bytes(self.input_image)

            # Batch önceliği: Kullanıcı konfigürasyonu > Redis'teki mevcut batch > None (Yeni batch)
            batch_name = self.batch_name_config or state.get_batch(dataset_id)

            res = upload_image(
                dataset_id=dataset_id,
                image_bytes=image_bytes,
                batch_name=batch_name,
            )

            # Kullanıcı batch adı girmemişse API'nin ürettiği ilk batch adını Redis'e yaz
            api_batch = res.get("batch_name")
            if not self.batch_name_config and api_batch:
                state.set_batch(dataset_id, api_batch)

            self.upload_status = "duplicate" if res.get("skipped") else "uploaded"

        except ApiClientError as e:
            self.upload_status = "error"
            logger.error("UploadDataset Doğrulama/API Hatası: %s", e)
        except Exception as e:
            self.upload_status = "error"
            logger.exception("UploadDataset Beklenmeyen Sistem Hatası: %s", e)

        return build_response(context=self)


if __name__ == "__main__":
    Executor(sys.argv[1]).run()