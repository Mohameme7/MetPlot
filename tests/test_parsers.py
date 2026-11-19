import bz2
import json
import sys
import types
from unittest import mock

import pytest

# pygrib is a heavy native dependency; stub it if it isn't installed so the pure-logic tests still run.
try:
    import pygrib  # noqa: F401
except ImportError:
    sys.modules["pygrib"] = types.ModuleType("pygrib")

from conftest import FakeInfo, GEM_INDEX_HTML, RUNS_HTML, HOURS_HTML
from MetPlot.Downloader.Parsers.ModelAbstract import Selection, WeatherModel
from MetPlot.Downloader.Parsers.BaseParse import ModelParse
from MetPlot.Downloader.Parsers import GEM as gem_mod
from MetPlot.Downloader.Parsers.GEM import GEM, GEMUSE, is_run
from MetPlot.Downloader.Parsers.icon import IconParse, ICONUSE
from MetPlot.Downloader.Parsers.NomadsUtils import NomadsParse, GFSUSE
from MetPlot.Exceptions.downloader_exceptions import InvalidCoordinates
from MetPlot.Exceptions.parser_errors import InvalidRun


# ---------------- BaseParse ----------------
def test_levelformat():
    assert ModelParse.levelformat(500) == "lev_500_mb"
    assert ModelParse.levelformat("Surface") == "lev_surface"


def test_formatdate():
    assert ModelParse.formatdate("2024-10-05") == "20241005"
    with pytest.raises(ValueError):
        ModelParse.formatdate("05/10/2024")


def test_modelparse_is_abstract():
    with pytest.raises(TypeError):
        ModelParse()


def test_weathermodel_defaults():
    class M(WeatherModel):
        def build_urls(self, sel): return ["a", "b"]
        def run_options(self): return {}
        def forecast_hours(self, run_date, run): return []

    m = M()
    sel = Selection(hours=[0], variables=[], levels=[], run="00")
    assert m.postprocess([b"x"]) == [b"x"]
    assert m.estimate_size([], sel) == 0
    assert m.finalize("f", sel) is None
    assert m.expected_count(sel) == 2
    assert sel.subregion is None and sel.run_date is None
    with pytest.raises(TypeError):
        WeatherModel()


# ---------------- Nomads / GFS ----------------
GFS_HTML = """
<div class="col_1"><span class="selectable"><span>gfs.20250102</span></span>
<span class="selectable"><span>gfs.20250101</span></span></div>
<div class="col_2"><span class="selectable"><span>00</span></span>
<span class="selectable"><span>06</span></span></div>
<select id="file_selector">
<option value="gfs.t06z.pgrb2.0p25.f000">a</option>
<option value="gfs.t06z.pgrb2.0p25.f003">b</option>
<option value="gfs.t06z.pgrb2.0p25.fanl">c</option>
<option value="gfs.t06z.pgrb2.1p00.f006">d</option>
</select>"""


def test_nomads_check_content():
    p = NomadsParse("<html><body>Data file not present</body></html>")
    assert p.CheckContent("not present")
    assert not p.CheckContent("hello")


def test_nomads_available_runs():
    runs = NomadsParse(GFS_HTML).get_available_runs()
    assert list(runs) == ["20250102", "20250101"]
    assert runs["20250102"] == ["00", "06"]
    assert runs["20250101"] == ["00", "06", "12", "18"]


def test_nomads_forecast_hours_latest_run():
    assert NomadsParse(GFS_HTML).get_forecast_hours("00", "20250102") == [0, 3]


def test_nomads_forecast_hours_old_run():
    hours = NomadsParse(GFS_HTML).get_forecast_hours("00", "20250101")
    assert hours == list(range(1, 121)) + list(range(123, 385, 3))


def test_nomads_create_url_basic():
    url = NomadsParse.create_url(6, "20250101", "12", ["TMP", "APCP"], ["lev_2_m_above_ground"], None)
    assert url.startswith(NomadsParse.BASEURL + "?")
    assert "gfs.t12z.pgrb2.0p25.f006" in url
    assert "var_TMP=on" in url and "var_APCP=on" in url
    assert "lev_2_m_above_ground=on" in url
    assert "subregion" not in url


def test_nomads_create_url_subregion():
    url = NomadsParse.create_url(0, "20250101", "00", ["TMP"], [], [30, 10, 60, 40])
    assert "toplat=30" in url and "bottomlat=10" in url
    assert "leftlon=60" in url and "rightlon=40" in url or "rightlon" in url
    assert "subregion=" in url


def test_nomads_create_url_bad_subregion():
    with pytest.raises(InvalidCoordinates):
        NomadsParse.create_url(0, "20250101", "00", ["TMP"], [], [95, 10, 60, 40])


def test_nomads_create_url_no_plus():
    url = NomadsParse.create_url(0, "20250101", "00", ["TMP"], ["lev 500 mb"], None)
    assert "+" not in url


def test_gfsuse_build_urls_and_options():
    m = GFSUSE(GFS_HTML)
    sel = Selection(hours=[0, 3], variables=["TMP"], levels=["lev_2_m_above_ground"],
                    run="00", run_date="20250101")
    urls = m.build_urls(sel)
    assert len(urls) == 2 and "f003" in urls[1]
    assert m.expected_count(sel) == 2
    assert m.run_options() == m.get_available_runs()
    assert m.forecast_hours("20250102", "00") == [0, 3]


def test_gfsuse_estimate_size():
    m = GFSUSE(GFS_HTML)
    sel = Selection([0], ["TMP"], [], "00", run_date="20250101")
    with mock.patch("MetPlot.Downloader.Parsers.NomadsUtils.fetch_sizes", return_value=1000):
        assert m.estimate_size(["u"], sel) == 1000
        sel.subregion = [90, 0, 0, 180]
        assert m.estimate_size(["u"], sel) == pytest.approx(1000 * 0.25)


# ---------------- GEM ----------------
def _fake_send(url_map=None):
    def send(self, method, **kw):
        url = kw["url"]
        if url_map:
            for key, info in url_map.items():
                if url.endswith(key):
                    return info
        return FakeInfo(GEM_INDEX_HTML)
    return send


@pytest.fixture
def gem_client():
    with mock.patch("MetPlot.Downloader.RequestHandler.RequestClient.SendRequest",
                    _fake_send()):
        yield


def test_is_run():
    assert is_run("00/") and is_run("20250101/")
    assert not is_run("00") and not is_run("abc/") and not is_run("../")


def test_gem_unsupported_model(gem_client):
    with pytest.raises(ValueError):
        GEM("ECMWF")


@pytest.mark.parametrize("name", ["gem", "GEM", "geps", "GEPS"])
def test_gem_supported_models(gem_client, name):
    assert GEM(name).model is GEM.MODELS[name.upper()]


def test_gem_create_url_gem(gem_client):
    url = GEM("GEM").create_url(hour="3", run="0", variable="TMP", level="Sfc", date_str="20250101")
    assert url.endswith("20250101T00Z_MSC_GDPS_TMP_Sfc_LatLon0.15_PT003H.grib2")
    assert "/20250101/WXO-DD/model_gdps/15km/00/003/" in url


def test_gem_create_url_geps(gem_client):
    url = GEM("GEPS").create_url(hour=12, run="12", variable="TMP", level="Sfc", date_str="20250101")
    assert "CMC_geps-raw_TMP_Sfc_latlon0p5x0p5_2025010112_P012_allmbrs.grib2" in url


def test_gem_create_url_default_date(gem_client):
    url = GEM("GEM").create_url(hour=0, run=0, variable="X", level="Y")
    from datetime import datetime, timezone
    assert datetime.now(timezone.utc).strftime("%Y%m%d") in url


def test_gem_forecast_hours(gem_client):
    g = GEM("GEM")
    with mock.patch.object(g.requestclient, "SendRequest", return_value=FakeInfo(HOURS_HTML)):
        assert g.get_forecast_hours("20250101", "00") == ["000", "003"]


def test_gem_forecast_hours_invalid_run(gem_client):
    g = GEM("GEM")
    with mock.patch.object(g.requestclient, "SendRequest", return_value=FakeInfo("", success=False)):
        with pytest.raises(InvalidRun):
            g.get_forecast_hours("20250101", "99")


def test_gem_available_runs(gem_client):
    g = GEM("GEM")
    with mock.patch.object(g.requestclient, "SendRequest", return_value=FakeInfo(RUNS_HTML)):
        runs = g.get_available_runs()
    assert runs["20250101"] == ["00", "12"]  # old dates default
    assert runs["20250102"] == ["00", "12"]
    assert runs["20250103"] == ["00", "12"]


@pytest.fixture
def gemuse(gem_client):
    return GEMUSE("GEM")


def test_gemuse_loads_catalog(gemuse):
    assert "CAPE" in gemuse.info


def test_gemuse_build_urls_filters(gemuse):
    gemuse.info = {"V": {"levels": ["Sfc", "L2"], "only_3h": ["Sfc"], "only_0h": ["L2"]}}
    sel = Selection(hours=[0, 1, 3, 6], variables=["V"], levels=["Sfc", "L2", "bad"],
                    run="00", run_date="20250101")
    urls = gemuse.build_urls(sel)
    sfc = [u for u in urls if "_Sfc_" in u]
    l2 = [u for u in urls if "_L2_" in u]
    assert len(sfc) == 3  # 0, 3, 6
    assert len(l2) == 1 and "PT000H" in l2[0]
    assert not any("bad" in u for u in urls)


def test_gemuse_run_options_and_hours(gemuse):
    with mock.patch.object(GEM, "get_available_runs", return_value={"a": []}), \
         mock.patch.object(GEM, "get_forecast_hours", return_value=["000"]):
        assert gemuse.run_options() == {"a": []}
        assert gemuse.forecast_hours("d", "00") == ["000"]


def test_gemuse_estimate_size(gemuse):
    sel = Selection([0], ["V"], [], "00", subregion=[90, 0, 0, 180])
    with mock.patch.object(gem_mod, "fetch_sizes", return_value=400):
        assert gemuse.estimate_size(["u"], sel) == pytest.approx(400 * 0.25)
        sel.subregion = None
        assert gemuse.estimate_size(["u"], sel) == 400


def test_gemuse_finalize(gemuse, tmp_path):
    sel = Selection([0], ["V"], [], "00")
    with mock.patch.object(gem_mod, "crop_coords") as crop:
        gemuse.finalize("x.grib", sel)  # no subregion -> noop
        crop.assert_not_called()
        f = tmp_path / "a.grib"
        f.write_bytes(b"x")
        sel.subregion = [30, 10, 60, 40]
        gemuse.finalize(str(f), sel)
        crop.assert_called_once_with(str(f), str(f).replace(".grib", "_Cropped.grib"), 60, 40, 10, 30)
        assert not f.exists()


# ---------------- ICON ----------------
def test_icon_create_url_single_and_pressure():
    u = IconParse.create_url(5, "18", "20250812", "single-level", "alb_rad")
    assert u.endswith("icon_global_icosahedral_single-level_2025081218_005_ALB_RAD.grib2.bz2")
    u = IconParse.create_url(14, "18", "20250812", "pressure-level", "t", 800)
    assert u.endswith("icon_global_icosahedral_pressure-level_2025081218_014_800_T.grib2.bz2")


def test_icon_find_text_between_element():
    html = "<a>alb_rad</a> 12-Aug-2025 18:00:00 <a>other</a>"
    assert IconParse.find_text_between_element("alb_rad", html).strip() == "12-Aug-2025 18:00:00"


def test_icon_available_runs():
    html = b"<a href='x'>alb_rad</a> 12-Aug-2025 18:00:00 <a>z</a>"
    with mock.patch("MetPlot.Downloader.Parsers.icon.requests.get",
                    return_value=types.SimpleNamespace(content=html)), \
         mock.patch("MetPlot.Downloader.Parsers.icon.random.choice", return_value="alb_rad"):
        runs = IconParse().get_available_runs()
    assert runs == {"20250812": ["00", "06", "12", "18"]}


def test_icon_forecast_hours():
    html = (b"<a href='icon_global_icosahedral_single-level_2025081218_000_ALB_RAD.grib2.bz2'>a</a>"
            b"<a href='icon_global_icosahedral_single-level_2025081218_003_ALB_RAD.grib2.bz2'>b</a>"
            b"<a href='readme'>c</a>")
    resp = mock.Mock(content=html)
    with mock.patch("MetPlot.Downloader.Parsers.icon.requests.get", return_value=resp):
        assert list(IconParse().get_forecast_hours("18")) == ["000", "003"]
    resp.raise_for_status.assert_called_once()


@pytest.fixture
def icon():
    return ICONUSE({
        "t": {"levels": ["typeOfLevel : pressure-level"]},
        "alb_rad": {"levels": ["typeOfLevel : single-level"]},
        "weird": {"levels": ["nothing"]},
    })


def test_icon_level_types(icon):
    assert icon._level_types_for(["t", "alb_rad", "weird"]) == ["pressure-level", "single-level"]


def test_icon_build_urls(icon):
    sel = Selection(hours=[0, 3], variables=["t", "alb_rad", "weird"], levels=[500, 800],
                    run="00", run_date="20250101")
    urls = icon.build_urls(sel)
    assert len(urls) == 4 + 2  # t: 2h*2lvl, alb_rad: 2h, weird skipped
    assert sum("_500_T" in u for u in urls) == 2


def test_icon_postprocess(icon):
    assert icon.postprocess([bz2.compress(b"abc"), bz2.compress(b"")]) == [b"abc", b""]


def test_icon_estimate_size_and_options(icon):
    with mock.patch("MetPlot.Downloader.Parsers.icon.fetch_sizes", return_value=7):
        assert icon.estimate_size(["u"], None) == 7
    with mock.patch.object(IconParse, "get_available_runs", return_value={"d": ["00"]}):
        assert icon.run_options() == {"d": ["00"]}
    with mock.patch.object(IconParse, "get_forecast_hours", return_value=iter(["000"])) as g:
        assert list(icon.forecast_hours("d", "00")) == ["000"]
        g.assert_called_once_with("00")


def test_icon_catalog_is_consistent():
    from MetPlot.Variables import catalog_path
    data = json.load(open(catalog_path("ICON", "MERGED_PARAMS.json"), encoding="utf-8"))
    m = ICONUSE(data)
    sel = Selection([0], list(data), [500], "00", run_date="20250101")
    assert len(m.build_urls(sel)) >= 1
