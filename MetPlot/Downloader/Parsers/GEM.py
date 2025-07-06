from bs4 import BeautifulSoup
from MetPlot.Downloader.Parsers.BaseParse import ModelParse
from MetPlot.Downloader.RequestHandler import RequestClient
from MetPlot.Exceptions.parser_errors import InvalidRun
from datetime import datetime, timezone


def is_run(run) -> bool:
    return run.endswith('/') and run.strip('/').isdigit()


class GEM(ModelParse):
    BASEURL = 'https://dd.weather.gc.ca/model_gem_global/15km/grib2/lat_lon'

    def __init__(self):
        self.requestclient = RequestClient()
        self.html = self.requestclient.SendRequest('get', url=GEM.BASEURL,
                                                   follow_redirects=True).response_text



    def get_available_runs(self) -> list:
        """
       Parses all available runs available on the GEM Server
       :return: List of GEM Runs available, eg : [00, 12, 18]
       """

        soup = BeautifulSoup(self.html, 'html.parser')
        runs = [a.get('href').strip('/') for a in soup.find_all('a') if is_run(a.get('href'))]
        return runs

    def get_forecast_hours(self, run=None) -> list:
        """

        :param run: Desired run to get forecast hours for
        :return: List of forecast hours of that run
        :raises InvalidRun if run is invalid
        """
        request = self.requestclient.SendRequest('get', url= GEM.BASEURL + '/' + run, follow_redirects=True)
        if not request.success:
            raise InvalidRun("Run not found")


        soup = BeautifulSoup(request.response_text, 'html.parser')
        hour_attrs = soup.find_all('a')
        href = map(lambda a: a.get('href'), hour_attrs)
        hours = list(filter(is_run, href))
        hours = [r.strip('/') for r in hours]
        return hours

    def get_runs_hours(self) -> dict:
        """
        :return: Returns a dict of available runs and their corresponding hours, eg : {"00" : [0,3,6]}
        """

        run_hours = {}
        runs = self.get_available_runs()

        for run in runs:
            run_hours[run] = self.get_forecast_hours(run)
        return run_hours

    @staticmethod
    def create_url(hour, run, variable,typeoflevel, level) -> str:
         utctime = datetime.now(timezone.utc)
         utctime = utctime.strftime("%Y%m%d")
         return f"{GEM.BASEURL}/{run}/{hour}/CMC_glb_{variable}_{typeoflevel}_{level}_latlon.15x.15_{utctime}{run}_P{hour}.grib2"



