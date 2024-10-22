from MetPlot.Downloader.example.FinaD import download
import time

start_time = time.time()

download(list(range(1, 91)), '2024-10-22', '06', ['APCP', 'SPFH'],
         ['surface', 1000, 925, 850], '../Forecast.grib', [42, 12, 25, 60])

print(f"{time.time() - start_time} seconds")
