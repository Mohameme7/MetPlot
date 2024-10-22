from MetPlot.Downloader.FileHandler import GribCreation
from MetPlot.Downloader.MemoryDownload import Downloader
from MetPlot.Downloader.URLGenerator import URLGen


def download(hours, run_date, run_time, variables: list, levels: list, filename, subregion):
    urls = []
    for hour in hours:
     url = URLGen(hour, run_date, run_time, variables, levels, subregion=subregion)

     urls.append(str(url))
    dl = Downloader(urls)
    hm = dl.submitdownloads()
    print(hm)
    GribCreation(hm, filename).merge_grib_files()
