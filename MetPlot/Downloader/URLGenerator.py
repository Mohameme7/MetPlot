import urllib.parse
import datetime
from typing import Union

from MetPlot.Exceptions.downloader_exceptions import InvalidCoordinates
from MetPlot.validators import validate_coords

BASEURL = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"


class URLGen:
    """Creates a GFS URL Download

    Parameters:
        hour : Forecast hour
        run_date : Date of the run needed, eg: 2024-9-12
        run_time : The run number, eg: 18z, 06z
        variables : Needed variables, eg: [VVEL, APCP]
        levels: Atmospheric layers needed, eg: [100, 200, surface]
        subregion : Choose a specific subregion, eg: [toplat, bottomlat, rightlon, leftlon]
    """

    def __init__(self, hour: int, run_date, run_time, variables: list, levels: list, subregion: list = None):
        self.hour = hour
        self.levels = levels
        self.run_date = self.__formatdate(run_date)
        self.run_time = run_time
        self.variables = variables
        self.subregion = subregion

    def __repr__(self):
        return self.__createurl()



    def __levelformat(self, level : Union[str,int]) -> str:
        """Formats the level to check if it's an isobaric level or something else, eg: troposphere
        :param level: The level to format
        :type level : str, int
        :returns formatted level
        """
        if isinstance(level, int):
            return f'lev_{level}_mb'
        else:
            return f'lev_{level.lower()}'

    def __formatdate(self, date : str) -> str:
        """Formats date from Year-Month-Day to YearMonthDay
        :param date: Date of the run: eg: 2024-10-05
        :type date: str
        :returns formatted_data : eg: 20241005
        """

        date_obj = datetime.datetime.strptime(date,"%Y-%m-%d")

        formatted_date = date_obj.strftime("%Y%m%d")
        return formatted_date

    def __createurl(self) -> str:
        """Creates GFS Download URL From given data in the class
        :returns Download URL
        """

        urlparams = {}
        for var in self.variables:
            urlparams[f'var_{var.strip()}'] = 'on'
        for level in self.levels:
            formattedlevel = self.__levelformat(level)
            urlparams[formattedlevel] = 'on'
        if self.subregion and len(self.subregion) == 4:
            validate_coords(self.subregion[1], self.subregion[0], self.subregion[3], self.subregion[2])
            urlparams['subregion'] = ''
            urlparams['toplat'] = self.subregion[0]
            urlparams['bottomlat'] = self.subregion[1]
            urlparams['rightlon'] = self.subregion[2]
            urlparams['leftlon'] = self.subregion[3]
        urlparams['dir'] = f"/gfs.{self.run_date}/{self.run_time}/atmos"
        urlparams['file'] = f"gfs.t{self.run_time}z.pgrb2.0p25.f{self.hour:03d}"
        query_string = urllib.parse.urlencode(urlparams)
        url = f"{BASEURL}?{query_string}".replace('+', '_')
        return url
