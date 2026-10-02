
"""
Upload Dataset: prepares incoming frames for dataset upload.
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../"))

from sdks.novavision.src.base.component import Component
from sdks.novavision.src.helper.executor import Executor
from components.UploadDataset.src.utils.response import build_response
from components.UploadDataset.src.models.PackageModel import PackageModel


class UploadDataset(Component):
    def __init__(self, request, bootstrap):
        super().__init__(request, bootstrap)

        self.request.model = PackageModel(**self.request.data)

        self.input_image = self.request.get_param("inputImage")
        self.dataset = self.request.get_param("configDataset")
        self.frame_interval = int(
            self.request.get_param("FrameInterval") or 5
        )

        self.result = self.input_image

    @staticmethod
    def bootstrap(config: dict) -> dict:
        return {}

    def run(self):
        # API entegrasyonu henüz yapılmadı.
        # Bu aşamada gelen frame'i ve ayarları hazırlıyoruz.
        return build_response(context=self)


if __name__ == "__main__":
    Executor(sys.argv[1]).run()
