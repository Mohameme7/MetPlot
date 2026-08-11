import os
from itertools import product
from bs4 import BeautifulSoup
from MetPlot.Downloader.FileHandler import crop_coords
from MetPlot.Downloader.Parsers.BaseParse import ModelParse
from MetPlot.Downloader.RequestHandler import RequestClient
from MetPlot.Downloader.size_fetch import fetch_sizes
from MetPlot.Exceptions.parser_errors import InvalidRun
from datetime import datetime, timezone
from MetPlot.utils.coordinates import bbox_percent
from MetPlot.Downloader.Parsers.ModelAbstract import WeatherModel, Selection


def is_run(run) -> bool:
    return run.endswith('/') and run.strip('/').isdigit()


class GEM(ModelParse):
    BASEURL = 'https://dd.weather.gc.ca/today/model_gdps/15km'

    def __init__(self):
        self.requestclient = RequestClient()
        self.html = self.requestclient.SendRequest('get', url=GEM.BASEURL,
                                                   follow_redirects=True).response_text


    def get_available_runs(self) -> dict:
        """
       Parses all available runs available on the GEM Server
       :return: List of GEM Runs available, eg : [00, 12, 18]
       """
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        runs_and_dates = {}

        soup = BeautifulSoup(self.html, 'html.parser')
        runs = [a.get('href').strip('/') for a in soup.find_all('a') if is_run(a.get('href'))]
        runs_and_dates[date_str] = runs
        print(runs_and_dates)
        return runs_and_dates

    def get_forecast_hours(self, run) -> list:
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

    #def get_runs_hours(self) -> dict:
    #    """
    #    :return: Returns a dict of available runs and their corresponding hours, eg : {"00" : [0,3,6]}
    #    """
#
 #       run_hours = {}
  #      runs = self.get_available_runs()
#
 #       for run in runs:
  #          run_hours[run] = self.get_forecast_hours(run)
   #     return run_hours


    @staticmethod
    def create_url(hour: str, run: str, variable: str, level: str, date_str: str = None) -> str:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

        f_hour = f"{int(hour):03d}"
        f_run = f"{int(run):02d}"

        return (
            f"https://dd.weather.gc.ca/today/model_gdps/15km/{f_run}/{f_hour}/"
            f"{date_str}T{f_run}Z_MSC_GDPS_{variable}_{level}_LatLon0.15_PT{f_hour}H.grib2"
        )

class GEMUSE(GEM, WeatherModel):
    def build_urls(self, sel: Selection) -> list[str]:
        urls = []
        for hour, level, variable in product(sel.hours, sel.levels, sel.variables):
            urls.append(self.create_url(hour=hour, run=sel.run, variable=variable, level=level))
        return urls

    def estimate_size(self, urls, sel: Selection) -> int:
        size = fetch_sizes(urls)
        return size * bbox_percent(*sel.subregion) if sel.subregion else size

    def finalize(self, filename: str, sel: Selection) -> None:
        if not sel.subregion:
            return
        cropped = filename.replace('.grib', '_Cropped.grib')
        crop_coords(filename, cropped,
                    sel.subregion[2], sel.subregion[3],
                    sel.subregion[1], sel.subregion[0])
        if os.path.exists(filename):
            os.remove(filename)

    def run_options(self) -> dict:
        return self.get_available_runs()

    def forecast_hours(self, run_date, run) -> list:
        return self.get_forecast_hours(run)