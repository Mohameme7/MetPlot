import bz2
import os
import re
import random
from collections import defaultdict
from itertools import product

from MetPlot.Downloader.FileHandler import crop_coords
from MetPlot.Downloader.Parsers.BaseParse import ModelParse
from bs4 import BeautifulSoup
import requests
from datetime import datetime, timezone
from typing import Literal
from MetPlot.Downloader.Parsers.ModelAbstract import WeatherModel, Selection
from MetPlot.Downloader.size_fetch import fetch_sizes
from MetPlot.utils.coordinates import bbox_percent
from MetPlot.validators import validate_coords


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

    def get_available_runs(self) -> dict:
        dates_and_runs = defaultdict(list)
        for run in ['00', '06', '12', '18']:
            req = requests.get(f"{self.BASE_URL}/{run}")
            date = self.find_text_between_element(random.choice(IconParse.RANDOM_VARS), req.content).replace("-", " ").strip()
            formatted_date = datetime.strptime(date, "%d %b %Y %X").strftime("%Y%m%d")
            dates_and_runs[formatted_date].append(run)
        return dates_and_runs

    def get_forecast_hours(self, run : Literal['00', '06', '12', '18'],):
        random_var = random.choice(IconParse.RANDOM_VARS)
        request = requests.get(f"{self.BASE_URL}/{run}/{random_var}")
        request.raise_for_status()
        parser = BeautifulSoup(request.content, "html.parser")

        parsed_a = parser.find_all('a')
        for element in parsed_a:
          match = re.search(r'_\d{10}_(\d+)_', element['href'])
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


class ICONUSE(IconParse, WeatherModel):
    def __init__(self, var_json: dict):
        super().__init__()
        self.content = var_json

    def _level_types_for(self, variables) -> list[str]:
        types = []
        for var in variables:
            for lvl in self.content[var]['levels']:
                m = re.findall(r"typeOfLevel\s*:\s*(\S+)", lvl)
                if m:
                    types.append(m[0])
        return types

    def build_urls(self, sel: Selection) -> list[str]:
        urls = []
        for variable in sel.variables:
            typeoflevel = None
            for lvl in self.content[variable]['levels']:
                m = re.findall(r"typeOfLevel\s*:\s*(\S+)", lvl)
                if m:
                    typeoflevel = m[0]
                    break
            if typeoflevel is None:
                continue
            for hour in sel.hours:
                if typeoflevel == "single-level":
                    urls.append(
                        self.create_url(int(hour), sel.run, sel.run_date,
                                        typeoflevel, variable, None)
                    )
                else:
                    for level in sel.levels:
                        urls.append(
                            self.create_url(int(hour), sel.run, sel.run_date,
                                            typeoflevel, variable, level)
                        )
        return urls

    def postprocess(self, chunks):
        return [bz2.decompress(c) for c in chunks]

    def estimate_size(self, urls, sel):
        return fetch_sizes(urls)

    def run_options(self):
        return dict(self.get_available_runs())

    def forecast_hours(self,run_date, run):
        return self.get_forecast_hours(run)