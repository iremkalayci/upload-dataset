"""
Upload Dataset: seçilen kareleri NovaVision dataset'ine yükler.
"""

import logging
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../"))

from sdks.novavision.src.base.component import Component
from sdks.novavision.src.helper.executor import Executor
from components.UploadDataset.src.utils.response import build_response
from components.UploadDataset.src.models.PackageModel import PackageModel
from components.UploadDataset.src.utils import api_client
from components.UploadDataset.src.utils.api_client import UploadError, get_credentials
from components.UploadDataset.src.utils.image_utils import image_to_upload_bytes
from components.UploadDataset.src.utils.sampler import FrameState, parse_interval

logger = logging.getLogger(__name__)


class UploadDataset(Component):
    def __init__(self, request, bootstrap):
        super().__init__(request, bootstrap)

        self.request.model = PackageModel(**self.request.data)

        self.input_image = self.request.get_param("inputImage")
        self.dataset = self.request.get_param("configDataset")
        self.frame_interval = parse_interval(self.request.get_param("FrameInterval"))
        self.batch_name_config = self.request.get_param("BatchName")

        self.result = self.input_image  # çıktı: görüntü aynen geçirilir
        self.upload_status = "not_run"  # not_run | skipped_frame | uploaded | duplicate | error

    @staticmethod
    def bootstrap(config: dict) -> dict:
        return {}

    def _process(self):
        dataset_id = api_client.parse_dataset_id(self.dataset)
        batch_cfg = api_client.normalize_batch_name(self.batch_name_config)

        state = FrameState(self.redis_db.r, self.flowUID, self.matchedID)
        if not state.should_select(self.frame_interval):
            self.upload_status = "skipped_frame"
            return

        data, ctype = image_to_upload_bytes(self.input_image)
        token, workspace, base_url = get_credentials(self.environment)
        batch = batch_cfg or state.get_batch(dataset_id)

        res = api_client.upload_image(
            base_url=base_url, token=token, workspace_id=workspace,
            dataset_id=dataset_id, image_bytes=data, content_type=ctype,
            batch_name=batch,
        )
        # Kullanıcı batch adı vermediyse dönen adı sakla (duplicate'te de dönebilir).
        if not batch_cfg and res.batch_name and res.batch_name != batch:
            state.set_batch(dataset_id, res.batch_name)
        self.upload_status = "duplicate" if res.skipped else "uploaded"

    def run(self):
        try:
            self._process()
        except UploadError as e:
            self.upload_status = "error"
            logger.error("UploadDataset: %s", e)
        except Exception:
            self.upload_status = "error"
            logger.exception("UploadDataset: beklenmeyen hata")
        return build_response(context=self)


if __name__ == "__main__":
    Executor(sys.argv[1]).run()