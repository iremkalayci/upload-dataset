"""Redis tabanlı kare örnekleyici ve batch durumu.

Yaşam döngüsü: SDK her kare için yeni executor örneği üretir; bu yüzden sayaç ve
batch adı Redis'te tutulur. Anahtar: UploadDataset:{flowUID}:{matchedID}:...

Sayaç INCR ile (atomik) artar. İndeks 0 tabanlıdır: n. kare (1'den başlayarak)
için index = n-1; `index % interval == 0` ise seçilir. Yani ilk kare HER ZAMAN
seçilir, ardından interval=5 için 1., 6., 11., ... kareler (50 kare -> 10 seçim).

TTL: sabit kısa TTL yok; her karede yenilenen 24 saatlik "boşta kalma" TTL'i
kullanılır (yalnızca terk edilmiş anahtarları temizlemek için).
"""
DEFAULT_INTERVAL = 5
IDLE_TTL_SECONDS = 24 * 3600


def parse_interval(value, default=DEFAULT_INTERVAL):
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return default
    return iv if iv >= 1 else default


def state_prefix(flow_uid, matched_id):
    return f"UploadDataset:{flow_uid}:{matched_id}"


class FrameState:
    def __init__(self, redis_client, flow_uid, matched_id, ttl=IDLE_TTL_SECONDS):
        self.r = redis_client
        self.prefix = state_prefix(flow_uid, matched_id)
        self.ttl = ttl

    def should_select(self, interval):
        key = f"{self.prefix}:counter"
        n = int(self.r.incr(key))
        self.r.expire(key, self.ttl)
        return (n - 1) % interval == 0

    def _batch_key(self, dataset_id):
        return f"{self.prefix}:dataset:{dataset_id}:batch"

    def get_batch(self, dataset_id):
        v = self.r.get(self._batch_key(dataset_id))
        if isinstance(v, bytes):
            v = v.decode("utf-8")
        return v or None

    def set_batch(self, dataset_id, name):
        self.r.set(self._batch_key(dataset_id), name, ex=self.ttl)