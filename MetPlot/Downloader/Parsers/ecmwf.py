"""ECMWF Open Data parser (IFS 0.1°, IFS 0.25°, AIFS 0.25°) using pure httpx + .index byte ranges."""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
from collections import defaultdict

from bs4 import BeautifulSoup

from MetPlot.Downloader.FileHandler import crop_coords
from MetPlot.Downloader.Parsers.BaseParse import ModelParse
from MetPlot.Downloader.Parsers.ModelAbstract import Selection, WeatherModel
from MetPlot.Downloader.RequestHandler import RequestClient
from MetPlot.Exceptions.parser_errors import InvalidRun
from MetPlot.utils.coordinates import bbox_percent


class ECMWF(ModelParse):
    """Parser for ECMWF Open Data (https://data.ecmwf.int/forecasts/) via .index byte-range requests."""

    HOST = "https://data.ecmwf.int"
    BASEURL = "https://data.ecmwf.int/forecasts"

    MODELS = {
        "IFS_0P1": {"model": "ifs", "res": "0p1", "stream": "oper"},
        "IFS_0P25": {"model": "ifs", "res": "0p25", "stream": "oper"},
        "AIFS_0P25": {"model": "aifs-single", "res": "0p25", "stream": "oper"},
        # aliases
        "IFS": {"model": "ifs", "res": "0p25", "stream": "oper"},
        "AIFS": {"model": "aifs-single", "res": "0p25", "stream": "oper"},
    }

    def __init__(self, model: str = "IFS_0P25"):
        key = model.upper().replace("-", "_").replace(" ", "_")
        if key not in self.MODELS:
            raise ValueError(f"ECMWF model '{model}' not supported. Choose from {list(self.MODELS)}")
        self.model_key = key
        self.model_cfg = self.MODELS[key]
        self.requestclient = RequestClient()
        self._index_map_cache: dict[tuple[str, str], dict[str, list[str]]] = {}

    def _get_text(self, url: str) -> str | None:
        req = self.requestclient.SendRequest("get", url=url, follow_redirects=True)
        if not req.success:
            return None
        return req.response_text.decode("utf-8", errors="ignore") if isinstance(req.response_text, bytes) else req.response_text

    def get_available_runs(self) -> dict[str, list[str]]:
        """Returns {YYYYMMDD: ['00', '06', '12', '18']} ordered newest date first."""
        html = self._get_text(f"{self.BASEURL}/")
        if not html:
            return {}
        soup = BeautifulSoup(html, "html.parser")
        dates = sorted(
            {
                m.group(1)
                for a in soup.find_all("a", href=True)
                if (m := re.search(r"/(\d{8})/?$", a["href"]))
            },
            reverse=True,
        )

        runs_by_date: dict[str, list[str]] = {}
        for i, date_str in enumerate(dates):
            if i < 2:
                d_html = self._get_text(f"{self.BASEURL}/{date_str}/")
                if d_html:
                    d_soup = BeautifulSoup(d_html, "html.parser")
                    runs = sorted(
                        {
                            m.group(1)
                            for a in d_soup.find_all("a", href=True)
                            if (m := re.search(r"/(\d{2})z/?$", a["href"]))
                        }
                    )
                    if runs:
                        runs_by_date[date_str] = runs
            else:
                runs_by_date[date_str] = ["00", "06", "12", "18"]
        return runs_by_date

    def _fetch_hour_index_map(self, run_date: str, run: str) -> dict[str, list[str]]:
        """Maps forecast step string (e.g. '6') -> list of full .index URLs for that step."""
        f_run = f"{int(run):02d}"
        cache_key = (str(run_date), f_run)
        if cache_key in self._index_map_cache:
            return self._index_map_cache[cache_key]

        model = self.model_cfg["model"]
        res = self.model_cfg["res"]
        # Try primary stream ('oper'), with fallback to 'scda' for 06z/18z if ever needed
        streams_to_try = [self.model_cfg["stream"]]
        if f_run in ("06", "18") and "scda" not in streams_to_try:
            streams_to_try.append("scda")

        hour_map: dict[str, list[str]] = defaultdict(list)
        for stream in streams_to_try:
            dir_url = f"{self.BASEURL}/{run_date}/{f_run}z/{model}/{res}/{stream}/"
            html = self._get_text(dir_url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not href.endswith(".index"):
                    continue
                m = re.search(r"-(\d+)h-[^-]+-fc(?:-(?:sfc|pl))?\.index$", href)
                if not m:
                    continue
                step = m.group(1)
                full_url = href if href.startswith("http") else f"{self.HOST}{href}"
                if full_url not in hour_map[step]:
                    hour_map[step].append(full_url)
            if hour_map:
                break

        if not hour_map:
            raise InvalidRun(f"No ECMWF {self.model_key} forecast files found for {run_date} {f_run}z")

        result = dict(hour_map)
        self._index_map_cache[cache_key] = result
        return result

    def get_forecast_hours(self, run_date: str, run: str) -> list[str]:
        """Returns sorted available forecast hours as strings (e.g. ['0', '3', '6', ..., '360'])."""
        hour_map = self._fetch_hour_index_map(run_date, run)
        return sorted(hour_map.keys(), key=int)

    def create_url(self, *args, **kwargs):
        raise NotImplementedError("Use ECMWFUSE.build_urls(sel) for byte-range ECMWF URLs.")


class ECMWFUSE(ECMWF, WeatherModel):
    """WeatherModel implementation for ECMWF Open Data (IFS 0.1°, IFS 0.25°, AIFS 0.25°)."""

    def __init__(self, model: str = "IFS_0P25"):
        super().__init__(model=model)
        self._last_sel_key: tuple | None = None
        self._last_urls: list[tuple[str, dict[str, str]]] = []
        self._last_total_bytes: int = 0

    def run_options(self) -> dict[str, list[str]]:
        return self.get_available_runs()

    def forecast_hours(self, run_date: str, run: str) -> list[str]:
        return self.get_forecast_hours(run_date, run)

    @staticmethod
    def _normalize_level(lvl: str) -> str:
        s = str(lvl).strip().lower()
        s = s.replace("lev_", "").replace("_mb", "").replace("mb", "").replace("hpa", "").strip()
        return s

    def _parse_single_index(
        self,
        index_url: str,
        wanted_vars: set[str],
        wanted_levels: set[str],
    ) -> tuple[list[tuple[str, dict[str, str]]], int]:
        text = self._get_text(index_url)
        if not text:
            return [], 0

        grib_url = index_url[:-len(".index")] + ".grib2"
        matched: list[tuple[str, dict[str, str]]] = []
        total_bytes = 0

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            param = str(entry.get("param", ""))
            if param not in wanted_vars:
                continue

            levtype = str(entry.get("levtype", ""))
            if levtype == "pl":
                lvl = str(entry.get("levelist", ""))
                if not wanted_levels or lvl not in wanted_levels:
                    continue

            offset = entry.get("_offset")
            length = entry.get("_length")
            if offset is None or length is None or int(length) <= 0:
                continue

            start = int(offset)
            end = start + int(length) - 1
            matched.append((grib_url, {"Range": f"bytes={start}-{end}"}))
            total_bytes += int(length)

        return matched, total_bytes

    def build_urls(self, sel: Selection) -> list[tuple[str, dict[str, str]]]:
        """Resolves matching GRIB2 byte ranges from ECMWF .index files."""
        sel_key = (
            str(sel.run_date),
            str(sel.run),
            tuple(str(h) for h in sel.hours),
            tuple(sel.variables),
            tuple(sel.levels),
        )
        if sel_key == self._last_sel_key and self._last_urls:
            return self._last_urls

        hour_map = self._fetch_hour_index_map(sel.run_date, sel.run)
        wanted_vars = {str(v).strip() for v in sel.variables}
        wanted_levels = {self._normalize_level(lv) for lv in sel.levels if str(lv).strip()}

        index_urls: list[str] = []
        for h in sel.hours:
            step = str(int(h))
            for idx_url in hour_map.get(step, []):
                # Optimization for split 0.1° files: skip -pl.index if no pressure levels selected
                if idx_url.endswith("-pl.index") and not wanted_levels:
                    continue
                index_urls.append(idx_url)

        urls: list[tuple[str, dict[str, str]]] = []
        total_bytes = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(self._parse_single_index, u, wanted_vars, wanted_levels)
                for u in index_urls
            ]
            for fut in futures:
                part_urls, part_bytes = fut.result()
                urls.extend(part_urls)
                total_bytes += part_bytes

        self._last_sel_key = sel_key
        self._last_urls = urls
        self._last_total_bytes = total_bytes
        return urls

    def estimate_size(self, urls: list, sel: Selection) -> int:
        total = self._last_total_bytes
        if sel.subregion:
            return int(total * bbox_percent(*sel.subregion))
        return total

    def expected_count(self, sel: Selection) -> int:
        return len(self.build_urls(sel))

    def finalize(self, filename: str, sel: Selection) -> None:
        if not sel.subregion:
            return
        top, bottom, left, right = sel.subregion
        cropped = f"{filename}.cropped.tmp"
        crop_coords(filename, cropped, left, right, bottom, top)
        if os.path.exists(cropped):
            os.replace(cropped, filename)
