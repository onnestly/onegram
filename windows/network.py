from __future__ import annotations
import asyncio
import logging
import threading
import time

class Network:

    def __init__(self, port: int, secret: str):
        self.port, self.secret = (port, secret)
        self.ready = threading.Event()
        self.finished = threading.Event()
        self.error: BaseException | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.stop_event: asyncio.Event | None = None
        self.thread = threading.Thread(target=self._thread, name='OneGram Network', daemon=True)

    async def _run(self):
        from proxy.config import proxy_config
        from proxy import tg_ws_proxy
        proxy_config.host = '127.0.0.1'
        proxy_config.port = self.port
        proxy_config.secret = self.secret
        proxy_config.fallback_cfproxy = True
        proxy_config.cfproxy_h2_media = True
        proxy_config.prefer_h2_media = True
        proxy_config.dc_redirects = {4: '149.154.167.220'}
        proxy_config.pool_size = 2
        self.loop = asyncio.get_running_loop()
        self.stop_event = asyncio.Event()
        task = asyncio.create_task(tg_ws_proxy._run(self.stop_event))
        try:
            deadline = time.monotonic() + 20
            while tg_ws_proxy._server_instance is None:
                if task.done():
                    await task
                    raise RuntimeError('Proxy stopped before listening')
                if time.monotonic() > deadline:
                    raise TimeoutError('Local proxy startup timed out')
                await asyncio.sleep(0.05)
            self.port = tg_ws_proxy._server_instance.sockets[0].getsockname()[1]
            proxy_config.port = self.port
            self.ready.set()
            await task
        finally:
            if not task.done():
                self.stop_event.set()
                try:
                    await asyncio.wait_for(task, 8)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    def _thread(self):
        try:
            asyncio.run(self._run())
        except BaseException as exc:
            self.error = exc
            logging.exception('OneGram network stopped')
        finally:
            self.finished.set()

    def start(self, timeout: float=25):
        self.thread.start()
        deadline = time.monotonic() + timeout
        while not self.ready.wait(0.05):
            if self.finished.is_set():
                raise RuntimeError('Cannot start local proxy') from self.error
            if time.monotonic() > deadline:
                self.stop()
                raise TimeoutError('Cannot start local proxy')

    def stop(self):
        if self.loop and self.stop_event and (not self.finished.is_set()):
            try:
                self.loop.call_soon_threadsafe(self.stop_event.set)
            except RuntimeError:
                pass
        if self.thread.ident:
            self.thread.join(timeout=12)
