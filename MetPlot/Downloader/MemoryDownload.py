import time
import concurrent.futures
from RequestHandler import RequestClient

class Downloader(RequestClient):
    def __init__(self, links: list):
        super().__init__()
        self.links = links

    def retrievedata(self, url):
        """Sends a request to get file data and returns it
         :param url: url to retrieve data from
         :returns received data from the request
         """
        req = self.SendRequest('get', url=url)

        if not req.success:
            raise Exception('Request failed') # More Error handling here later
        time.sleep(0.3)  # Avoid rate-limiting
        return req.response_text

    def submitdownloads(self):
        """Submit all links to download the data."""
        with concurrent.futures.ThreadPoolExecutor() as executor:
            return list(executor.map(self.retrievedata, self.links))
