"""
Upload Dataset: VideoFeed'den gelen kareleri aralıkla seçip NovaVision dataset'ine yükler.
"""

import hashlib
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../"))

from sdks.novavision.src.base.component import Component
from sdks.novavision.src.helper.executor import Executor
from sdks.novavision.src.media.image import Image
from components.UploadDataset.src.utils.response import build_response
from components.UploadDataset.src.models.PackageModel import PackageModel
from components.UploadDataset.src.utils import api_client

VERSION = "v4"
TTL = 24 * 3600  # Redis durum anahtarlarının boşta kalma süresi
DIAG_FRAMES = 12  # tanı: ilk N gelen karenin özeti loglanır


def log(msg):
    print(f"[UploadDataset {VERSION}] {msg}", flush=True)


def first_image(value):
    """Girişten tek bir Image sözlüğü döndürür (liste gelirse ilk eleman)."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


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

        self.result = self.input_image  # çıktı: giriş görüntüsü aynen geçirilir

    @staticmethod
    def bootstrap(config: dict) -> dict:
        return {}

    def _frame_meta(self):
        """VideoFeed'in kareyle birlikte gönderdiği metadata (yoksa boş sözlük)."""
        image = first_image(self.input_image)
        return (image.get("metadata") if isinstance(image, dict) else None) or {}

    def _state_key(self):
        """Redis anahtarı: akış + bileşen + video oturumu (video_path/source ve loop).

        Video değişince ya da başa sarılınca sayaç ve batch sıfırlanır. Kaynak adresi
        kimlik bilgisi içerebileceğinden (rtsp://user:pass@...) özetlenerek yazılır.
        """
        meta = self._frame_meta()
        raw = f"{meta.get('video_path') or meta.get('source') or ''}|{meta.get('loop', 0)}"
        session = hashlib.md5(raw.encode()).hexdigest()[:12]
        return f"UploadDataset:{self.flowUID}:{self.matchedID}:{session}"

    def _upload_if_selected(self):
        redis = self.redis_db.r
        key = self._state_key()
        meta = self._frame_meta()

        # Sayaç Redis'te: SDK her kare için yeni örnek oluşturur.
        # İlk kare seçilir, sonra her N. kare (N=5 için 1., 6., 11. ...).
        n = redis.incr(key)
        redis.expire(key, TTL)
        if n <= DIAG_FRAMES:
            log(f"kare={n} geldi: seçilecek={(n - 1) % self.frame_interval == 0} "
                f"aralık={self.frame_interval} video_kare={meta.get('frame_index')} "
                f"debug={self.debug} anahtar={key}")
        if (n - 1) % self.frame_interval:
            return

        try:
            dataset_id = api_client.parse_dataset_id(self.dataset)
        except (TypeError, ValueError, KeyError) as e:
            log(f"kare={n} YEREL HATA: dataset id çözülemedi "
                f"({type(e).__name__}: {e}): {self.dataset!r}")
            return

        # Kare Redis'tedir (VideoFeed set_frame). get_frame verilen sözlüğü değiştirdiği için
        # kopya verilir; böylece çıktıya geçen self.input_image bozulmaz.
        source = first_image(self.input_image)
        frame = Image.get_frame(img=dict(source), redis_db=self.redis_db) if isinstance(source, dict) else None
        if frame is None:
            log(f"kare={n} YEREL HATA: kare Redis'ten okunamadı "
                f"(giriş tipi={type(source).__name__}, anahtarlar="
                f"{list(source) if isinstance(source, dict) else None})")
            return
        try:
            image = api_client.frame_to_jpeg(frame.value)
        except Exception as e:
            log(f"kare={n} YEREL HATA (JPEG): {type(e).__name__}: {e}")
            return

        token, workspace_id, base_url = api_client.get_credentials(self.environment)
        if not token:
            log(f"kare={n} YEREL HATA: DEVICE_ACCESS_TOKEN tanımlı değil.")
            return

        batch = self.batch_name or redis.get(key + ":batch")
        if isinstance(batch, bytes):
            batch = batch.decode()

        log(f"kare={n} yükleniyor: video_kare={meta.get('frame_index')} "
            f"md5={hashlib.md5(image).hexdigest()[:8]} dataset={dataset_id} adres={base_url} "
            f"workspace={workspace_id or 'YOK'} batch={batch!r} boyut={len(image)}B")
        status, body = api_client.upload_image(
            base_url, token, workspace_id, dataset_id, image, batch
        )

        if status in (200, 201) and isinstance(body, dict):
            skipped = bool(body.get("skipped"))
            name = body.get("batch_name")
            log(f"kare={n} HTTP {status} {'ATLANDI (zaten var)' if skipped else 'EKLENDI'} "
                f"batch={name!r} yeni_batch={body.get('batch_created')}")
            # Atlanan görselin batch'i eski bir batch olabilir; yalnızca yeni eklemede saklanır.
            if not skipped and name and not self.batch_name:
                redis.set(key + ":batch", name, ex=TTL)
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