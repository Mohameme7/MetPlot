from abc import ABC, abstractmethod
from datetime import datetime
from typing import Union


class ModelParse(ABC):

    @staticmethod
    def levelformat(level : Union[str,int]) -> str:
        """Formats the level to check if it's an isobaric level or something else, eg: troposphere
        :param level: The level to format
        :type level : str, int
        :returns formatted level
        """
        if isinstance(level, int):
            return f'lev_{level}_mb'
        else:
            return f'lev_{level.lower()}'

    @staticmethod
    def formatdate(date : str) -> str:
        """Formats date from Year-Month-Day to YearMonthDay
        :param date: Date of the run: eg: 2024-10-05
        :type date: str
        :returns formatted_data : eg: 20241005
        """

        date_obj = datetime.strptime(date,"%Y-%m-%d")

        formatted_date = date_obj.strftime("%Y%m%d")
        return formatted_date

    @abstractmethod
    def get_available_runs(self):
        pass

    @abstractmethod
    def get_forecast_hours(self):
        pass

    @staticmethod
    @abstractmethod
    def create_url() -> str:
        pass