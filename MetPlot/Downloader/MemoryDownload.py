from RequestHandler import RequestClient
import concurrent.futures


class Downloader(RequestClient):
    def __init__(self, links: list):
        super().__init__()
        self.links = links

    def retrievedata(self, url):
        """Sends a request to get file data and returns it
        :param url: url to retrieve data from
        """

        req = self.SendRequest('get', url=url)
        if not req.success:
            raise Exception('Request failed')
        return req.response_text

    def submitdownloads(self):
        # Unfinished, supposed to retrieve data for all links given
        with concurrent.futures.ThreadPoolExecutor() as executor:
            features = executor.map(self.retrievedata, self.links)

