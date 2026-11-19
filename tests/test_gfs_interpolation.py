"""
Tests for the xarray/cfgrib based GribInterpolator.

* Offline tests use a synthetic xarray Dataset (always run).
* The integration test downloads a real GFS run from NOMADS and is opt-in:
      python -m pytest tests/test_gfs_interpolation.py -m integration
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

xr = pytest.importorskip("xarray")
cfgrib = pytest.importorskip("cfgrib")


from MetPlot.Interpolation import GribInterpolator


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
RUN_TIME = np.datetime64("2026-11-19T06:00")


def make_ds(steps_h=(0, 3, 6), name="t2m", level_type="heightAboveGround"):
    steps = pd.to_timedelta(list(steps_h), unit="h")
    # value == step in hours, so linear interpolation is trivially checkable
    data = np.broadcast_to(np.array(steps_h, float)[:, None, None], (len(steps_h), 2, 3)).copy()
    ds = xr.Dataset(
        {name: (("step", "latitude", "longitude"), data, {"GRIB_typeOfLevel": level_type})},
        coords={
            "step": steps,
            "latitude": [10.0, 11.0],
            "longitude": [20.0, 21.0, 22.0],
            "time": RUN_TIME,
            "valid_time": ("step", RUN_TIME + steps.values),
        },
    )
    return ds


def gi_with(*datasets, freq="1h"):
    gi = GribInterpolator("unused.grib", freq=freq)
    gi.datasets = list(datasets)
    return gi


# --------------------------------------------------------------------------------------
# offline tests
# --------------------------------------------------------------------------------------
def test_is_interpolatable():
    assert GribInterpolator._is_interpolatable(make_ds((0, 3)))
    assert not GribInterpolator._is_interpolatable(make_ds((0,)))
    assert not GribInterpolator._is_interpolatable(make_ds((0, 3)).isel(step=0, drop=True))


def test_interpolate_fills_hourly_steps_with_linear_values():
    out = gi_with(make_ds((0, 3, 6)))._interpolate(make_ds((0, 3, 6)))
    assert out.sizes["valid_time"] == 7
    np.testing.assert_allclose(out["t2m"].isel(latitude=0, longitude=0).values, np.arange(7))


def test_interpolate_preserves_dates():
    out = gi_with()._interpolate(make_ds((0, 3, 6)))
    assert "step" not in out.dims
    expected = pd.date_range("2026-11-19T06:00", "2026-11-19T12:00", freq="1h")
    np.testing.assert_array_equal(out.valid_time.values, expected.values)
    assert out.time.values == RUN_TIME


def test_interpolate_uneven_steps_like_gfs():
    # GFS: hourly then 3-hourly
    out = gi_with()._interpolate(make_ds((0, 1, 2, 3, 6, 9)))
    assert out.sizes["valid_time"] == 10
    np.testing.assert_allclose(out["t2m"].isel(latitude=0, longitude=0).values, np.arange(10))


def test_interpolate_custom_freq():
    out = gi_with(freq="30min")._interpolate(make_ds((0, 3)))
    assert out.sizes["valid_time"] == 7
    np.testing.assert_allclose(out["t2m"].isel(latitude=0, longitude=0).values[1], 0.5)


def test_single_step_dataset_untouched():
    ds = make_ds((0,))
    assert gi_with()._interpolate(ds) is ds


def test_run_handles_multiple_level_groups():
    a = make_ds((0, 3), "t2m", "heightAboveGround")
    b = make_ds((0, 3), "t", "isobaricInhPa")
    out = gi_with(a, b).run()
    assert len(out) == 2
    assert all(o.sizes["valid_time"] == 4 for o in out)


def test_level_name():
    assert GribInterpolator._level_name(make_ds(level_type="isobaricInhPa"), 0) == "isobaricInhPa"
    assert GribInterpolator._level_name(xr.Dataset({"x": ("a", [1])}), 5) == "group_5"


def test_to_netcdf_flat(tmp_path):
    pytest.importorskip("netCDF4")
    out = gi_with(make_ds((0, 3, 6))).to_netcdf(tmp_path / "o.nc")
    with xr.open_dataset(out) as ds:
        assert ds.sizes["valid_time"] == 7
        assert pd.Timestamp(ds.valid_time.values[0]) == pd.Timestamp("2026-11-19T06:00")


def test_to_netcdf_grouped(tmp_path):
    pytest.importorskip("netCDF4")
    gi = gi_with(make_ds((0, 3), "t2m", "heightAboveGround"), make_ds((0, 3), "t", "isobaricInhPa"))
    out = gi.to_netcdf(tmp_path / "g.nc", grouped=True)
    with xr.open_dataset(out, group="heightAboveGround") as a, xr.open_dataset(out, group="isobaricInhPa") as b:
        assert "t2m" in a and "t" in b


def test_context_manager_opens_and_closes_datasets(monkeypatch):
    ds = make_ds()
    calls = {}

    def fake_open(path, **kw):
        calls["path"], calls["kw"] = path, kw
        return [ds]

    monkeypatch.setattr(cfgrib, "open_datasets", fake_open)
    with GribInterpolator("some.grib") as gi:
        assert gi.datasets == [ds]
    assert gi.datasets == []
    assert calls["path"] == "some.grib"
    assert calls["kw"]["backend_kwargs"] == {"indexpath": ""}


# --------------------------------------------------------------------------------------
# integration test (network + eccodes)
# --------------------------------------------------------------------------------------
@pytest.mark.integration
def test_gfs_download_and_interpolate(tmp_path):
    from MetPlot.Downloader.FileHandler import GribCreation
    from MetPlot.Downloader.MemoryDownload import Downloader
    from MetPlot.Downloader.Parsers.ModelAbstract import Selection
    from MetPlot.Downloader.Parsers.NomadsUtils import GFSUSE
    from MetPlot.Downloader.RequestHandler import RequestClient

    pytest.importorskip("pygrib")
    pytest.importorskip("netCDF4")

    with RequestClient() as client:
        info = client.SendRequest("get", url="https://nomads.ncep.noaa.gov/gribfilter.php?ds=gfs_0p25")
    if not info.success:
        pytest.skip("NOMADS unreachable")
    gfs = GFSUSE(info.response_text)

    runs = gfs.run_options()
    assert runs
    # use the previous day's last run: always complete, so no partially-published files
    run_date = list(runs)[1]
    run = runs[run_date][-1]
    all_hours = gfs.forecast_hours(run_date, run)
    assert 0 in all_hours and 384 in all_hours

    # 120 -> 126 is the hourly/3-hourly boundary: 121,122,124,125 must be interpolated
    hours = [h for h in (120, 123, 126) if h in all_hours]
    assert len(hours) == 3

    sel = Selection(
        hours=hours,
        variables=["TMP"],
        levels=["lev_2_m_above_ground", "lev_500_mb"],
        run=run,
        run_date=run_date,
        subregion=[42, 12, 25, 60],
    )
    urls = gfs.build_urls(sel)
    assert len(urls) == len(hours)
    assert urls[0].count("?") == 1, "malformed URL: BASEURL already contains '?'"

    chunks = Downloader(urls).submit_downloads()
    chunks = [c for c in chunks if c[:4] == b"GRIB"]  # NOMADS returns HTML errors with status 200
    assert len(chunks) == len(urls), "some downloads failed or returned an error page"

    grib = tmp_path / "gfs.grib"
    GribCreation(chunks, str(grib))
    assert grib.stat().st_size > 0

    nc = tmp_path / "gfs_hourly.nc"
    with GribInterpolator(grib, freq="1h") as gi:
        gi.to_netcdf(nc, grouped=True)

    run_time = pd.Timestamp(f"{run_date} {run}:00")
    with xr.open_dataset(nc, group="isobaricInhPa") as ds:
        expected = pd.date_range(run_time + pd.Timedelta(hours=120), periods=7, freq="1h")
        np.testing.assert_array_equal(ds.valid_time.values, expected.values)
        assert np.isfinite(ds["t"]).all()
