import time
import concurrent.futures
from MetPlot.Downloader.RequestHandler import RequestClient
from multiprocessing import Queue


class Downloader(RequestClient):
    def __init__(self, links: list, queue: Queue = None):
        super().__init__()
        self.links = links
        self.queue = queue

    def retrievedata(self, url) -> bytes:
        """Sends a request to get file data and returns it
         :param url: url to retrieve data from
         :param queue : Queue to track progress from if needed
         :returns : received data from the request
         """
        req = self.SendRequest('get', url=url)
        if self.queue:
            self.queue.put_nowait('.')
        if req.success:
            return req.response_text
        else:

            return b""

    def submitdownloads(self):
        """Submit all links to download the data."""
        with concurrent.futures.ThreadPoolExecutor() as executor:
            return list(executor.map(self.retrievedata, self.links))
