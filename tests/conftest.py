import os
import sys

import matplotlib

matplotlib.use("Agg")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GEM_INDEX_HTML = """<html><body>
<a href="../">../</a><a href="20250101/">20250101/</a>
<a href="20250102/">20250102/</a><a href="20250103/">20250103/</a>
</body></html>"""

RUNS_HTML = '<a href="00/">00/</a><a href="12/">12/</a><a href="readme.txt">x</a>'
HOURS_HTML = '<a href="000/">000/</a><a href="003/">003/</a><a href="nope">n</a>'


class FakeInfo:
    def __init__(self, text="", success=True, status=200):
        self.response_text = text
        self.success = success
        self.status_code = status
