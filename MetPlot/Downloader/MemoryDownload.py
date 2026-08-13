import concurrent.futures
import time
import httpx
from MetPlot.Downloader.RequestHandler import RequestClient
from multiprocessing import Queue


class Downloader(RequestClient):
    MAX_WORKERS = 8
    MAX_RETRIES = 3

    def __init__(self, links: list, queue: Queue = None):
        super().__init__()
        self.links = links
        self.queue = queue

    def retrieve_data(self, url) -> bytes:
        for attempt in range(self.MAX_RETRIES):
            try:
                req = self.SendRequest('get', url=url)
                if req.success:
                    if self.queue:
                        self.queue.put_nowait('.')
                    return req.response_text
                break
            except (httpx.RemoteProtocolError, httpx.ConnectError,
                    httpx.ReadTimeout, httpx.ReadError):
                if attempt + 1 == self.MAX_RETRIES:
                    break
                time.sleep(2 ** attempt)

        if self.queue:
            self.queue.put_nowait('.')
        return b""

    def submit_downloads(self):
        """Submit all links to download the data."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            return list(executor.map(self.retrieve_data, self.links))