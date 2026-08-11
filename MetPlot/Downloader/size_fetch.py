from concurrent.futures import ThreadPoolExecutor

import requests
def fetch_sizes(urls):
    sizes = []
    def fetch_size(url):
        req = requests.get(url, stream=True)
        sizes.append(int(req.headers.get('Content-Length') or 0))
    with ThreadPoolExecutor() as executor:
        executor.map(fetch_size, urls)
    return sum(sizes)