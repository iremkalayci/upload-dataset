"""
Redis tabanlı kare sayacı ve batch durumu.

Yaşam döngüsü: SDK her kare için yeni executor örneği üretir; sayaç ve batch bilgisi Redis'te tutulur.
İlk kare ve ardından her N. kare seçilir: (n - 1) % interval == 0.
"""

DEFAULT_INTERVAL = 5
TTL = 24 * 3600


def parse_interval(val, default=DEFAULT_INTERVAL):
    """Interval değerini tam sayıya çevirir. 1'den küçükse varsayılana döner."""
    try:
        iv = int(val)
        return iv if iv >= 1 else default
    except (TypeError, ValueError):
        return default


class FrameState:
    def __init__(self, redis_client, flow_uid, matched_id):
        self.r = redis_client
        self.prefix = f"UploadDataset:{flow_uid}:{matched_id}"

    def should_select(self, interval):
        """1, 6, 11... kareleri seçmek için Redis sayacını artırır ve kontrol eder."""
        key = f"{self.prefix}:counter"
        n = int(self.r.incr(key))
        self.r.expire(key, TTL)
        return (n - 1) % interval == 0

    def get_batch(self, dataset_id):
        """Dataset bazlı saklanan batch adını döner."""
        val = self.r.get(f"{self.prefix}:{dataset_id}:batch")
        return val.decode("utf-8") if isinstance(val, bytes) else val

    def set_batch(self, dataset_id, name):
        """Dataset bazlı batch adını 24 saatlik TTL ile Redis'e yazar."""
        self.r.set(f"{self.prefix}:{dataset_id}:batch", name, ex=TTL)