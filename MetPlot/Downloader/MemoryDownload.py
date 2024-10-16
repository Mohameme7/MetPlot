import time

from RequestHandler import RequestClient
import concurrent.futures


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
            raise Exception(
                'Request failed')  # There will be error handling very soon for each possible error returned.
        time.sleep(0.5)  # Delay to not get rate limited quick
        return req.response_text

    def submitdownloads(self) -> list:
        """Submits all the links given to download data from them
        :returns DownloadedData list
        """
        with concurrent.futures.ThreadPoolExecutor() as executor:
            DownloadedData = []
            features = executor.map(self.retrievedata, self.links)
            for response in features:
                DownloadedData.append(response)
            return DownloadedData


r = Downloader(['https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?var_UGRD=on&var_VGRD=on&lev_15090_mb=on'
                '&lev_200_mb=on&lev_250_mb=on&lev_300_mb=on&lev_700_mb=on&lev_750_mb=on&lev_850_mb=on&lev_925_mb=on'
                '&dir=%2Fgfs.20241011%2F06%2Fatmos&file=gfs.t06z.pgrb2.0p25.f020'])
r.submitdownloads() #Tests
