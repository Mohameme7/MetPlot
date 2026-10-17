import json
import os
from bs4 import BeautifulSoup
from MetPlot.Downloader.FileHandler import crop_coords
from MetPlot.Downloader.Parsers.BaseParse import ModelParse
from MetPlot.Downloader.RequestHandler import RequestClient
from MetPlot.Downloader.misc import fetch_sizes
from MetPlot.Exceptions.parser_errors import InvalidRun
from datetime import datetime, timezone
from MetPlot.utils.coordinates import bbox_percent
from MetPlot.Downloader.Parsers.ModelAbstract import WeatherModel, Selection
from MetPlot.Downloader.misc import file_read
from MetPlot.Variables import catalog_path


def is_run(run) -> bool:
    return run.endswith('/') and run.strip('/').isdigit()

class GEM(ModelParse):
    BASEURL = 'https://dd.weather.gc.ca/'

    MODELS = {
        'GEM': {
            "path": 'model_gdps/15km/',
            "url_template": f"{BASEURL}/"
                            "{date_str}/WXO-DD/"
                            "model_gdps/15km/"
                            "{run}/"
                            "{dir_hour}/"
                            "{date_str}T{run}Z_MSC_GDPS_{variable}_{level}_LatLon0.15_PT{file_hour}H.grib2",
        },
        'GEPS': {
            "path": 'ensemble/geps/grib2/raw/',
            "url_template": f"{BASEURL}/"
                            "{date_str}/WXO-DD/ensemble/geps/grib2/raw/{run}/{dir_hour}/CMC_geps-raw_"
                            "{variable}_{level}_latlon0p5x0p5_{date_str}{run}_P{file_hour}_allmbrs.grib2"
        }
    }

    def __init__(self, model : str):
        self.requestclient = RequestClient()
        if self.MODELS.get(model.upper()) is None:
            raise ValueError(f"Model {model} not supported")
        self.model = self.MODELS.get(model.upper())
        self.html = self.requestclient.SendRequest('get', url=GEM.BASEURL,
                                                   follow_redirects=True).response_text

    def get_available_runs(self) -> dict:
        """
       Parses all available runs available on the CMC Server
       :return: List of CMC Runs available, eg : [00, 12, 18]
       """
        runs_and_dates = {}
        soup = BeautifulSoup(self.html, 'html.parser')
        dates = [a.get('href').strip('/') for a in soup.find_all('a') if is_run(a.get('href'))]
        for date in dates:
            if date in [dates[-1], dates[-2]]:
                model_test = self.requestclient.SendRequest('get', url=f'https://dd.weather.gc.ca/{date}/WXO-DD/'
                                                                       f'{self.model['path']}'
                                                                       ,
                                                            follow_redirects=True)
                print(f'https://dd.weather.gc.ca/{date}/WXO-DD/'
                                                                       f'{self.model}')


                runs_req = self.requestclient.SendRequest('get', url=f"{GEM.BASEURL}/{date}/WXO-DD/{self.model['path']}",
                                                          follow_redirects=True)
                runs_soup = BeautifulSoup(runs_req.response_text, 'html.parser')
                runs = [
                    a["href"].rstrip("/")
                    for a in runs_soup.find_all("a", href=True)
                    if is_run(a["href"])
                ]
                runs_and_dates[date] = runs
            else:
                runs_and_dates[date] = ['00', '12']

        return runs_and_dates

    def get_forecast_hours(self, run_date, run) -> list:
        """

        :param run: Desired run to get forecast hours for
        :return: List of forecast hours of that run
        :raises InvalidRun if run is invalid
        """
        request = self.requestclient.SendRequest('get',
                                                 url=f"{GEM.BASEURL}/{run_date}/WXO-DD/{self.model['path']}/{run}",
                                                 follow_redirects=True)
        if not request.success:
            raise InvalidRun("Run not found")

        soup = BeautifulSoup(request.response_text, 'html.parser')
        hour_attrs = soup.find_all('a')
        href = map(lambda a: a.get('href'), hour_attrs)
        hours = list(filter(is_run, href))
        hours = [r.strip('/') for r in hours]
        return hours


    def create_url(self, hour: str, run: str, variable: str, level: str, date_str: str = None) -> str:
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

        f_run = f"{int(run):02d}"
        dir_hour = f"{int(hour):03d}"
        file_hour = f"{int(hour):03d}"

        return self.model["url_template"].format(
            date_str=date_str,
            run=f_run,
            dir_hour=dir_hour,
            file_hour=file_hour,
            variable=variable,
            level=level
        )



class GEMUSE(GEM, WeatherModel):
    def __init__(self, model : str):
        super().__init__(model=model)
        with open(catalog_path(f'CMC/{model}', 'MERGED_PARAMS.json'), encoding='utf-8') as f:
            self.info = json.load(f)

    def build_urls(self, sel: Selection) -> list[str]:
        urls = []
        for variable in sel.variables:
            info = self.info[variable]
            levels = info.get("levels", [])
            restrictions = {}
            for key, restricted_levels in info.items():
                if key.startswith("only_") and key.endswith("h"):
                    interval_str = key[5:-1]
                    if interval_str.isdigit():
                        restrictions[int(interval_str)] = set(restricted_levels)

            for level in sel.levels:
                if level not in levels:
                    continue

                for hour in sel.hours:
                    h_int = int(hour)
                    skip = False
                    for interval, restricted_levels in restrictions.items():
                        if level in restricted_levels:
                            if interval == 0:
                                if h_int != 0:
                                    skip = True
                                    break
                            else:
                                if h_int % interval != 0:
                                    skip = True
                                    break
                    if skip:
                        continue
                    urls.append(self.create_url(hour=hour, run=sel.run,
                                                variable=variable, level=level, date_str=sel.run_date))
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
        return self.get_forecast_hours(run_date, run)
