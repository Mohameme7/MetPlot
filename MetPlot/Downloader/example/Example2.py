from MetPlot.Downloader.example.FinaD import download; from MetPlot.Interpolation import GribInterpolator
import time

start_time = time.time()

download(list(range(1, 121)) + list(range(120,385,3)), '2024-10-24', '12', ['SPFH'],
         [1000], 'Forecast.grib', [42, 12, 25, 60])

with GribInterpolator('Forecast.grib', 'InterpolatedForecast.grib') as inter:
    interpolated_values = inter.run_interpolation()
    inter.merge_to_grib(interpolated_values)

print(f"{time.time() - start_time} seconds")
