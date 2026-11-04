from .utils import human_bytes

class _Stats:

    def __init__(self):
        self.connections_total = 0
        self.connections_active = 0
        self.connections_ws = 0
        self.connections_h2 = 0
        self.h2_tcp_connections = 0
        self.h2_requests = 0
        self.h2_errors = 0
        self.connections_tcp_fallback = 0
        self.connections_cfproxy = 0
        self.connections_fronting = 0
        self.connections_bad = 0
        self.connections_masked = 0
        self.ws_errors = 0
        self.bytes_up = 0
        self.bytes_down = 0
        self.pool_hits = 0
        self.pool_misses = 0
        self.cf_pool_hits = 0
        self.cf_pool_misses = 0

    def summary(self) -> str:
        pool_total = self.pool_hits + self.pool_misses
        pool_s = f'{self.pool_hits}/{pool_total}' if pool_total else 'n/a'
        cf_pool_total = self.cf_pool_hits + self.cf_pool_misses
        cf_pool_s = f'{self.cf_pool_hits}/{cf_pool_total}' if cf_pool_total else 'n/a'
        return f'total={self.connections_total} active={self.connections_active} ws={self.connections_ws} h2={self.connections_h2} h2_tcp={self.h2_tcp_connections} h2_req={self.h2_requests} h2_err={self.h2_errors} tcp_fb={self.connections_tcp_fallback} cf={self.connections_cfproxy} front={self.connections_fronting} bad={self.connections_bad} masked={self.connections_masked} err={self.ws_errors} pool={pool_s} cf_pool={cf_pool_s} up={human_bytes(self.bytes_up)} down={human_bytes(self.bytes_down)}'
stats = _Stats()
