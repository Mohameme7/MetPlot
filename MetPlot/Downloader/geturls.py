# Supposed to be a test to find current hour steps for a forecast and it's working but has to be optimized,
# Going to be only used for latest forecasts
import requests
from bs4 import BeautifulSoup

url = 'https://nomads.ncep.noaa.gov/find_subdirs_files.php?ds=gfs_0p25&path=/gfs.20241009&subdir_num=1&subdir_name=12'
response = requests.get(url)

soup = BeautifulSoup(response.text, 'html.parser')

options = soup.select('#file_selector option')

forecast_hours = []
for option in options:
    if option['value'].startswith('gfs.t12z.pgrb2.0p25.f'):
        fhour = option['value'].split('.')[-1][1:]
        forecast_hours.append(fhour)

print(forecast_hours)
