import numpy as np
from scipy.ndimage import gaussian_filter
from dataclasses import dataclass
from MetPlot.Exceptions.downloader_exceptions import InvalidCoordinates

@dataclass
class MapInfo:
    smoothness: int = 5
    botlat: int = -90
    toplat: int = 90
    rightlon: int = 180
    leftlon: int = -180

# Most of the things here are going to be turned into more abstract versions due to possible overuse of these in the future
class MapDataGenerator(MapInfo):
    def __init__(self, smoothness: int = 5, botlat: int = -90, toplat: int = 90, rightlat: int = 180, leftlat: int = -180):
        super().__init__(smoothness=smoothness, botlat=botlat, toplat=toplat, rightlat=rightlat, leftlat=leftlat)

        self.data = None
        self.griddedCoords = self._generate_grid()

        self._validate_coords()

        self._generate_random_data()

    def _validate_coords(self):
        if not (-90 <= self.botlat <= 90 and -90 <= self.toplat <= 90 and -180 <= self.leftlon <= 180 and -180 <=
                self.rightlon <= 180):
            raise InvalidCoordinates("Coordinates are out of bounds")
        if not (self.toplat > self.botlat or self.rightlon > self.leftlon):
            raise InvalidCoordinates("Invalid coordinate ordering")

    def _generate_grid(self):
        lat = np.linspace(self.botlat, self.toplat, 100)
        lon = np.linspace(self.leftlon, self.rightlon, 100)
        lon, lat = np.meshgrid(lon, lat)

        return lon, lat

    def _generate_random_data(self):
        data = np.random.rand(100, 100)
        self.data = gaussian_filter(data, sigma=self.smoothness)
        return self.data



