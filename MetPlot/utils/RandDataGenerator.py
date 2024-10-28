from typing import Tuple

import numpy as np
from scipy.ndimage import gaussian_filter
from dataclasses import dataclass
from MetPlot.Exceptions.downloader_exceptions import InvalidCoordinates
from MetPlot.validators import validate_coords

@dataclass
class MapInfo:
    smoothness: int = 5
    botlat: int = -90
    toplat: int = 90
    rightlon: int = 180
    leftlon: int = -180

# Most of the things here are going to be turned into more abstract versions due to possible overuse of these in the future
class MapDataGenerator(MapInfo):
    def __init__(self, smoothness: int = 5, botlat: int = -90, toplat: int = 90, rightlon: int = 180, leftlon: int = -180):
        super().__init__(smoothness=smoothness, botlat=botlat, toplat=toplat, rightlon=rightlon, leftlon=leftlon)

        self.data = None
        validate_coords(botlat=botlat, toplat=toplat, rightlon=rightlon, leftlon=leftlon)

        self.griddedCoords = self._generate_grid()


        self._generate_random_data()

    def _generate_grid(self) -> Tuple[np.ndarray, np.ndarray]:
        lat = np.linspace(self.botlat, self.toplat, 100)
        lon = np.linspace(self.leftlon, self.rightlon, 100)
        lon, lat = np.meshgrid(lon, lat)

        return lon, lat

    def _generate_random_data(self) -> np.ndarray:
        data = np.random.rand(100, 100)
        self.data = gaussian_filter(data, sigma=self.smoothness)
        return self.data



