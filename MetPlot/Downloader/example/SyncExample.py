from MetPlot.Downloader.FileHandler import GribCreation
from MetPlot.Downloader.MemoryDownload import Downloader
from MetPlot.Downloader.URLGenerator import URLGen
from MetPlot.Interpolation import GribInterpolator


def download(hours, run_date, run_time, variables: list, levels: list, filename, subregion):
    urls = []
    for hour in hours:
     url = URLGen(hour, run_date, run_time, variables, levels, subregion=subregion)

     urls.append(str(url))
    dl = Downloader(urls)
    hm = dl.submitdownloads()
    print(hm)
    GribCreation(hm, filename).merge_grib_files()

import time

start_time = time.time()

# Change Run Date to latest or available ones if needed
download(list(range(1, 121)) + list(range(120,385,3)), '2024-10-24', '12', ['SPFH'],
         [1000], 'Forecast.grib', [42, 12, 25, 60])

with GribInterpolator('Forecast.grib', 'InterpolatedForecast.grib') as inter:
    interpolated_values = inter.run_interpolation()
    inter.merge_to_grib(interpolated_values)

print(f"{time.time() - start_time} seconds")