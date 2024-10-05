import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from typing import Union
import os
from parsecpt import parse_cpt_string, create_colormap, read_file
import matplotlib.colors as mcolors
from RandDataGenerator import MapDataGenerator
from dataclasses import dataclass
import io


@dataclass
class PlotInfo:
    cmap: Union[str, io.TextIOWrapper, mcolors.LinearSegmentedColormap, mcolors.Colormap, mcolors.ListedColormap]
    toplat: int = 90
    rightlat: int = 180
    leftlat: int = -180
    botlat: int = -90
    dots_per_inch: int = 300
    save_pic: tuple = (False,)
    smoothness: int = 5


class PlotData(PlotInfo, MapDataGenerator):
    def __init__(self, cmap: Union[str, io.TextIOWrapper, mcolors.LinearSegmentedColormap, mcolors.Colormap,
    mcolors.ListedColormap],
                 toplat: int = 90,
                 rightlat: int = 180,
                 leftlat: int = -180, botlat: int = -90,
                 dots_per_inch: int = 300,
                 save_pic: tuple = (False,),
                 smoothness: int = 5,

                 ):
        super().__init__(cmap=cmap, toplat=toplat, rightlat=rightlat, leftlat=leftlat,
                         botlat=botlat, dots_per_inch=dots_per_inch, save_pic=save_pic, smoothness=smoothness)
        MapDataGenerator.__init__(self, toplat=toplat, rightlat=rightlat, leftlat=leftlat,
                                  botlat=botlat, smoothness=smoothness)
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
                    FileContent = read_file(self.cmap)
                    self.cmap = create_colormap(parse_cpt_string(FileContent))
                else:
                    self.cmap = create_colormap(parse_cpt_string(self.cmap))
        elif isinstance(self.cmap, io.TextIOWrapper):
            self.cmap = create_colormap(parse_cpt_string(self.cmap.read()))

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

        (plt.savefig(self.save_pic[1] if len(self.save_pic) > 1 else "plot.png", bbox_inches='tight')
         if self.save_pic[0] else None)
        plt.show(bbox_inches='tight')


