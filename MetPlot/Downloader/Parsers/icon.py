import re
import random
from MetPlot.Downloader.Parsers.BaseParse import ModelParse
from bs4 import BeautifulSoup
import requests
from datetime import datetime, timezone
from typing import Literal


class IconParse(ModelParse):
    BASE_URL = "https://opendata.dwd.de/weather/nwp/icon/grib/"
    RANDOM_VARS = ['alb_rad',
                   'h_ice','cape_con']  # specific single-level vars in case one does not exist,
                                        # good for extracting hours
    @staticmethod
    def find_text_between_element(label, html) -> str:
        """Finds text inbetween elements
        Example: <a>label<a>
                 World
                 <a>People<a>
        this function would return World
        :param label: Content inside the element that comes before the text we want to get
        :param html: Raw content of the page
        :return: Text inbetween elements
        """
        soup = BeautifulSoup(html, "html.parser")
        return soup.find("a", string=re.compile(label)).next_sibling

    def get_available_runs(self):
        today_runs  = []
        yesterday_runs = []
        current_utc_time = datetime.now(timezone.utc).strftime("%Y%m%d")
        for run in ['00', '06', '12', '18']:
            req = requests.get(f"{self.BASE_URL}/{run}")


            date = self.find_text_between_element(random.choice(IconParse.RANDOM_VARS), req.content).replace("-", " ").strip()
            formatted_date = datetime.strptime(date, "%d %b %Y %X").strftime("%Y%m%d")
            if formatted_date == current_utc_time:
                today_runs.append(run)
            else:
                yesterday_runs.append(run)
        return today_runs, yesterday_runs


    def get_forecast_hours(self, run : Literal['00', '06', '12', '18']):
        random_var = random.choice(IconParse.RANDOM_VARS)
        request = requests.get(f"{self.BASE_URL}/{run}/{random_var}")
        request.raise_for_status()
        parser = BeautifulSoup(request.content, "html.parser")

        yes = parser.find_all('a')
        for thing in yes:
          match = re.search(r'_\d{10}_(\d+)_', thing['href'])
          if match:
            yield match.group(1)

    """https://opendata.dwd.de/weather/nwp/icon/grib/18/alb_rad/
    icon_global_icosahedral_single-level_2025081218_052_ALB_RAD.grib2.bz2"""


    """https://opendata.dwd.de/weather/nwp/icon/grib/18/t/
    icon_global_icosahedral_pressure-level_2025081218_014_800_T.grib2.bz2"""
    @staticmethod
    def create_url(hour, run_time, run_date, typeoflevel, variable, level=None) -> str:
        if level:
          return (f"{IconParse.BASE_URL}/{run_time}/{variable}/"
                f"icon_global_icosahedral_{typeoflevel}_{run_date}{run_time}_{hour:03d}_{level}_{variable.upper()}"
                f".grib2.bz2")

        return (f"{IconParse.BASE_URL}/{run_time}/{variable}/"
                f"icon_global_icosahedral_{typeoflevel}_{run_date}{run_time}_{hour:03d}_{variable.upper()}"
                f".grib2.bz2")





