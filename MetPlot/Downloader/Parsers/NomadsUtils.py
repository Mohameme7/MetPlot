# The nomads NCEP Website has no real API,
# And it has the worst request error handling ever and thus this forces me to parse its html content to get what I need
import requests

from MetPlot.Downloader.Parsers.BaseParse import ModelParse
from bs4 import BeautifulSoup
import urllib.parse
from MetPlot.validators import validate_coords


class NomadsParse(ModelParse):
    FORECAST_FILE_ENDS_WITH = '.pgrb2.0p25'
    BASEURL = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
    """Parses info from NOMADS Website about available runs and so on, and allows you to optionally create 
    download links from the model
    """

    def __init__(self, html=None):
        self.parser = BeautifulSoup(html,'html.parser')





    def CheckContent(self, text) -> bool:
        # Will be mainly used to parse errors, since nomads is a bit stupid and returns wrong status codes
        """Checks if wanted text exists in the html
        :param text: text to check
        :type text: str
        :returns bool: True or False
        """
        return text in self.parser.get_text()

    def get_available_runs(self) -> dict:
        """Parses the website html to see the current available runs and the today's available runs, eg: 06z,00z
        :returns Tuple[List, List] : Dates, times
        """

        dates = [span.text for span in self.parser.select('div.col_1 span.selectable span')]
        times = [span.text for span in self.parser.select('div.col_2 span.selectable span')]
        runs = {}
        for date in dates:
            if date == dates[0]:
                runs[date] = times  # If the date is today only return runs that already happens
            else:
                runs[date] = ['00', '06', '12', '18']  # If the date is anything before today return all runs
        return runs

    def get_forecast_hours(self) -> list:
        """Gets the Current Forecast hours of a run, eg: 06z has 120 hours till now
        :returns list: Available Forecast hours
        """
        options = self.parser.select('#file_selector option')

        forecast_hours = []
        for option in options:
            base_value = '.'.join(option['value'].split('.')[:-1])

            if base_value.endswith(self.FORECAST_FILE_ENDS_WITH):
                fhour = option['value'].split('.')[-1][1:]
                forecast_hours.append(fhour)
        return forecast_hours

    @staticmethod
    def create_url(hour, run_date, run_time, variables: list , levels: list ,
                 subregion: list) -> str:
        """
        Creates GFS Download URL.

        :param hour : Forecast hour
        :param run_date : Date of the run needed, eg: 2024-9-12
        :param run_time : The run number, eg: 18z, 06z
        :param variables : Needed variables, eg: [VVEL, APCP]
        :param levels: Atmospheric layers needed, eg: [100, 200, surface]
        :param subregion : Choose a specific subregion, eg: [toplat, bottomlat, rightlon, leftlon]
        :returns: Download URL
        """

        urlparams = {
            'dir': f"/gfs.{run_date}/{run_time}/atmos",
            'file': f"gfs.t{run_time}z.pgrb2.0p25.f{hour:03d}",
        }
        for var in variables:
            urlparams[f'var_{var.strip()}'] = 'on'

        for level in levels:
            #formattedlevel = self.__levelformat(level) # Not really compatible, disabled until further notice for now
            urlparams[level] = 'on'

        if subregion and len(subregion) == 4:
            validate_coords(subregion[1], subregion[0], subregion[3], subregion[2])
            urlparams['subregion'] = ''
            urlparams['toplat'] = subregion[0]
            urlparams['leftlon'] = subregion[2]
            urlparams['rightlon'] = subregion[3]
            urlparams['bottomlat'] = subregion[1]
        query_string = urllib.parse.urlencode(urlparams)
        url = f"{NomadsParse.BASEURL}?{query_string}".replace('+', '_')

        return url




