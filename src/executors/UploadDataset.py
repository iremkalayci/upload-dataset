"""
Upload Dataset: seçilen kareleri NovaVision dataset'ine yükler.
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../"))

from sdks.novavision.src.base.component import Component
from sdks.novavision.src.helper.executor import Executor
from components.UploadDataset.src.utils.response import build_response
from components.UploadDataset.src.models.PackageModel import PackageModel
from components.UploadDataset.src.utils import api_client

TTL = 24 * 3600


def log(msg):
    print(f"[UploadDataset] {msg}", flush=True)


class UploadDataset(Component):
    def __init__(self, request, bootstrap):
        super().__init__(request, bootstrap)

        self.request.model = PackageModel(**self.request.data)

        self.input_image = self.request.get_param("inputImage")
        self.dataset = self.request.get_param("configDataset")
        self.batch_name = str(self.request.get_param("BatchName") or "").strip()
        try:
            self.frame_interval = max(1, int(self.request.get_param("FrameInterval") or 5))
        except (TypeError, ValueError):
            self.frame_interval = 5

        self.result = self.input_image

    @staticmethod
    def bootstrap(config: dict) -> dict:
        return {}

    def _upload_if_selected(self):
        r = self.redis_db.r
        key = f"UploadDataset:{self.flowUID}:{self.matchedID}"

        # Sayaç Redis'te: SDK her kare için yeni örnek oluşturur.
        # İlk kare seçilir, sonra her N. kare (1., 6., 11. ... N=5 için).
        n = r.incr(key)
        r.expire(key, TTL)
        if (n - 1) % self.frame_interval:
            return

        try:
            dataset_id = int(self.dataset)
        except (TypeError, ValueError):
            log(f"kare={n} YEREL HATA: dataset id sayı değil: {self.dataset!r}")
            return

        try:
            image = api_client.to_image_bytes(self.input_image)
        except Exception as e:
            log(f"kare={n} YEREL HATA (görüntü): {e}")
            return

        token, workspace_id, base_url = api_client.get_credentials(self.environment)
        if not token:
            log(f"kare={n} YEREL HATA: NOVAVISION_ACCESS_TOKEN tanımlı değil.")
            return

        batch = self.batch_name or r.get(key + ":batch")
        if isinstance(batch, bytes):
            batch = batch.decode()

        status, body = api_client.upload_image(
            base_url, token, workspace_id, dataset_id, image, batch
        )

        if status in (200, 201) and isinstance(body, dict):
            skipped = bool(body.get("skipped"))
            name = body.get("batch_name")
            log(f"kare={n} HTTP {status} {'ATLANDI (zaten var)' if skipped else 'EKLENDI'} "
                f"batch={name!r} yeni_batch={body.get('batch_created')}")
            # Atlanan görselin batch'i eski bir batch olabilir; yalnızca yeni eklemede sakla.
            if not skipped and name and not self.batch_name:
                r.set(key + ":batch", name, ex=TTL)
        else:
            log(f"kare={n} HTTP {status} HATA: {str(body)[:300]}")

    def run(self):
        try:
            self._upload_if_selected()
        except Exception as e:  # tek karedeki hata akışı durdurmasın
            log(f"HATA ({type(e).__name__}): {e}")
        return build_response(context=self)


if __name__ == "__main__":
    Executor(sys.argv[1]).run()