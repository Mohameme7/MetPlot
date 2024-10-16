# The nomads NCEP Website has no real API,
# And it has the worst request error handling ever and thus this forces me to parse its html content to get what I need
from typing import Tuple, List

from bs4 import BeautifulSoup


class NomadsParse:
    """Parses Contents in the Nomads website"""

    def __init__(self, rawhtml):
        self.parser = BeautifulSoup(rawhtml, 'html.parser')

    def CheckContent(self, text) -> bool:
        # Will be mainly used to parse errors, since nomads is a bit stupid and returns wrong status codes

        """Checks if wanted text exists in the html
        :param text: text to check
        :type text: str
        :returns bool: True or False
        """
        return text in self.parser.get_text()

    def GetAvailableRuns(self) -> Tuple[List, List]:
        """Parses the website html to see the current available runs and the today's available runs, eg: 06z,00z
        :returns Tuple[List, List] : Dates, times
        """

        dates = [span.text for span in self.parser.select('div.col_1 span.selectable span')]
        times = [span.text for span in self.parser.select('div.col_2 span.selectable span')]
        return dates, times

    def GetForecastHours(self) -> list:
        """Gets the Current Forecast hours of a run, eg: 06z has 120 hours till now
        :returns list: Available Forecast hours
        """
        options = self.parser.select('#file_selector option')

        forecast_hours = []
        for option in options:
            base_value = '.'.join(option['value'].split('.')[:-1])

            if base_value.endswith('.pgrb2.0p25'):
                fhour = option['value'].split('.')[-1][1:]
                forecast_hours.append(fhour)
        return forecast_hours



