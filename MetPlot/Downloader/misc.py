import json
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

def file_read(file):
    with open(file) as file:
        if file.name.endswith('.json'):
            content = json.load(file)
        else:
            content = file.readlines()
            content = [i.strip('\n') for i in content]

        file.close()
    return content
