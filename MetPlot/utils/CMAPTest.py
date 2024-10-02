import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import io
from typing import Union
import os
from parsecpt import CPTTools
import matplotlib.colors as mcolors
from abc import ABC


class MapDataGenerator(ABC):
    def __init__(self, toplat: int = 90, rightlat: int = 180, leftlat: int = -180, botlat: int = -90):
        self.botlat = botlat
        self.toplat = toplat
        self.rightlat = rightlat
        self.leftlat = leftlat
        self.spatialres = 100
        self.data = None

        self.griddedCoords = self._generate_grid()

        self._validate_coords()

        self._generate_random_data()

    def _validate_coords(self):

        if not (-90 <= self.botlat <= 90 and -90 <= self.toplat <= 90 and -180 <= self.leftlat <= 180 and -180 <=
                self.rightlat <= 180):
            raise ValueError("Coordinates are out of bounds")
        if not (self.toplat > self.botlat and self.rightlat > self.leftlat):
            raise ValueError("Invalid coordinate ordering")

    def _generate_grid(self):
        lat = np.linspace(self.botlat, self.toplat, self.spatialres)
        lon = np.linspace(self.leftlat, self.rightlat, self.spatialres)
        lon, lat = np.meshgrid(lon, lat)

        return lon, lat

    def _generate_random_data(self):
        data = np.random.rand(100, 100)
        self.data = gaussian_filter(data, sigma=5)
        return self.data


class PlotData(MapDataGenerator, CPTTools):
    def __init__(self, cmap: Union[str, io.TextIOWrapper, mcolors.LinearSegmentedColormap, mcolors.Colormap,
    mcolors.ListedColormap],
                 toplat: int = 90,
                 rightlat: int = 180,
                 leftlat: int = -180, botlat: int = -90,
                 dots_per_inch: int = 300,
                 save_pic: bool = False
                 ):
        super().__init__(toplat, rightlat, leftlat, botlat)
        self.save_pic = save_pic
        self.fig, self.ax = plt.subplots(figsize=(12, 8), subplot_kw={'projection': ccrs.PlateCarree()},
                                         dpi=dots_per_inch)
        self.cmap = cmap
        self._handleCMAP()
        self._plot()

    def _handleCMAP(self):

        if isinstance(self.cmap, str):
            try:
                self.cmap = plt.get_cmap(self.cmap)
            except:
                if os.path.isfile(self.cmap):
                    FileContent = self.read_file(self.cmap)
                    self.cmap = self.create_colormap(self.parse_cpt_string(FileContent))
                else:
                    self.cmap = self.create_colormap(self.parse_cpt_string(self.cmap))
        elif isinstance(self.cmap, io.TextIOWrapper):
            self.cmap = self.create_colormap(self.parse_cpt_string(self.cmap.read()))

    def _plot(self):
        self.ax.add_feature(cfeature.COASTLINE)
        self.ax.add_feature(cfeature.BORDERS)
        self.ax.add_feature(cfeature.LAND, edgecolor='black')

        contour = self.ax.contourf(self.griddedCoords[0], self.griddedCoords[1], self.data, cmap=self.cmap,
                                   transform=ccrs.PlateCarree())
        plt.gca().set_axis_off()

        plt.margins(0, 0)
        plt.colorbar(contour, ax=self.ax, orientation='vertical')
        self.ax.set_title('Color Map Test')

        (plt.savefig('Plot.png', bbox_inches='tight') if self.save_pic else None)
        plt.show(bbox_inches='tight')
