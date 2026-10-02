
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
    """NovaVision Image nesnesindeki Base64 verisini bytes'a çözer."""

    if isinstance(payload, (bytes, bytearray)):
        image_bytes = bytes(payload)

    elif isinstance(payload, dict):
        current = payload
        image_bytes = None

        for _ in range(8):
            if not isinstance(current, dict):
                break

            value = current.get("value")

            if isinstance(value, (bytes, bytearray)):
                image_bytes = bytes(value)
                break

            if isinstance(value, str):
                encoded = value.strip()

                if encoded.startswith("data:") and "," in encoded:
                    encoded = encoded.split(",", 1)[1]

                try:
                    image_bytes = base64.b64decode(
                        encoded,
                        validate=True,
                    )
                except (ValueError, TypeError) as exc:
                    raise ApiClientError(
                        f"Base64 görüntü verisi çözülemedi: {exc}"
                    ) from exc

                break

            if isinstance(value, dict):
                current = value
                continue

            raise ApiClientError(
                "Görüntü verisi bulunamadı. "
                f"Mevcut alanlar: {list(current.keys())}"
            )

        if image_bytes is None:
            raise ApiClientError(
                "Görüntü verisi beklenen yapıda bulunamadı."
            )
    else:
        raise ApiClientError(
            f"Beklenmeyen inputImage tipi: {type(payload)}"
        )

    if not image_bytes:
        raise ApiClientError("Görüntü verisi boş.")

    if image_bytes.startswith(b"\xff\xd8\xff"):
        return image_bytes

    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return image_bytes

    raise ApiClientError(
        "Görüntü JPEG veya PNG biçiminde değil. "
        f"İlk baytlar: {image_bytes[:8].hex()}"
    )


class UploadDataset(Component):

    def __init__(self, request, bootstrap):
        super().__init__(request, bootstrap)
        self.request.model = PackageModel(**self.request.data)

        # Girdi verisi
        self.input_image = self.request.get_param("inputImage")

        # Dataset Picker
        self.dataset = (
            self.request.get_param("dataset")
            or self.request.get_param("configDataset")
        )

        # Kare örnekleme aralığı
        self.frame_interval = parse_interval(
            self.request.get_param("frameInterval")
            or self.request.get_param("FrameInterval")
        )

        # Batch adı
        self.batch_name_config = (
            self.request.get_param("batchName")
            or self.request.get_param("BatchName")
            or ""
        ).strip()

        # Orijinal görüntüyü çıkışta koru.
        self.result = self.input_image
        self.upload_status = "not_run"

    @staticmethod
    def bootstrap(config: dict) -> dict:
        return {}

    def run(self):
        try:
            state = FrameState(
                self.redis_db.r,
                self.flowUID,
                self.matchedID,
            )

            # Kare seçilmediyse API'ye istek gönderme.
            if not state.should_select(self.frame_interval):
                self.upload_status = "skipped_frame"
                return build_response(context=self)

            # Dataset ID'sini çöz.
            dataset_id = parse_dataset_id(self.dataset)

            # Görüntünün Base64 verisini çöz.
            image_bytes = extract_raw_bytes(self.input_image)

            # Batch önceliği:
            # Kullanıcı ayarı > Redis > Yeni batch
            batch_name = (
                self.batch_name_config
                or state.get_batch(dataset_id)
            )

            # Görüntüyü Data API'ye yükle.
            res = upload_image(
                dataset_id=dataset_id,
                image_bytes=image_bytes,
                batch_name=batch_name,
            )

            # Otomatik oluşturulan batch adını sakla.
            api_batch = res.get("batch_name")

            if not self.batch_name_config and api_batch:
                state.set_batch(dataset_id, api_batch)

            self.upload_status = (
                "duplicate" if res.get("skipped") else "uploaded"
            )

        except ApiClientError as e:
            self.upload_status = "error"
            logger.error(
                "UploadDataset Doğrulama/API Hatası: %s",
                e,
            )

        except Exception as e:
            self.upload_status = "error"
            logger.exception(
                "UploadDataset Beklenmeyen Sistem Hatası: %s",
                e,
            )

        return build_response(context=self)


if __name__ == "__main__":
    Executor(sys.argv[1]).run()
