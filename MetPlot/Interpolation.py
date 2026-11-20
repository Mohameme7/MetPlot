from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import cfgrib
import numpy as np
import pandas as pd
import xarray as xr


def _promote_to_valid_time(ds: xr.Dataset) -> xr.Dataset:
    """Ensure a dataset has a 1D `valid_time` dimension"""
    if "valid_time" in ds.dims:
        return ds

    if "step" in ds.dims:
        if "valid_time" in ds.coords and "step" in ds.coords["valid_time"].dims:
            return ds.swap_dims({"step": "valid_time"})
        if "time" in ds.coords:
            vt = ds.coords["time"] + ds.coords["step"]
            return ds.assign_coords(valid_time=vt).swap_dims({"step": "valid_time"})
        return ds

    # Scalar valid_time or scalar time + step (common when cfgrib splits mixed-interval precip)
    vt_val = None
    if "valid_time" in ds.coords and ds.coords["valid_time"].ndim == 0:
        vt_val = ds.coords["valid_time"].values
    elif "time" in ds.coords and ds.coords["time"].ndim == 0:
        if "step" in ds.coords and ds.coords["step"].ndim == 0:
            vt_val = ds.coords["time"].values + ds.coords["step"].values
        else:
            vt_val = ds.coords["time"].values

    if vt_val is not None:
        ds = ds.drop_vars(["valid_time", "step"], errors="ignore")
        return ds.expand_dims(valid_time=[vt_val])
    return ds


def consolidate_grib_datasets(datasets: list[xr.Dataset]) -> list[xr.Dataset]:
    """Re-combine datasets that cfgrib split due to mixed accumulation intervals (e.g., tp/apcp).

    When a GRIB2 file has mixed stepTypes or accumulation intervals (like 0h instant + 3h/6h accum),
    cfgrib.open_datasets splits the same variable into multiple datasets (some with no time dim).
    This groups matching (vars, level_type) datasets, promotes scalar times to `valid_time`,
    concatenates, sorts, and deduplicates timestamps so the time dimension is never lost.
    """
    if len(datasets) <= 1:
        return list(datasets)

    groups: dict[tuple[tuple[str, ...], str], list[xr.Dataset]] = defaultdict(list)
    order: list[tuple[tuple[str, ...], str]] = []

    for i, ds in enumerate(datasets):
        var_key = tuple(sorted(str(k) for k in ds.data_vars))
        lvl_type = GribInterpolator._level_name(ds, i)
        gkey = (var_key, lvl_type)
        if gkey not in groups:
            order.append(gkey)
        groups[gkey].append(ds)

    consolidated: list[xr.Dataset] = []
    for gkey in order:
        parts = groups[gkey]
        if len(parts) == 1:
            consolidated.append(parts[0])
            continue

        promoted = [_promote_to_valid_time(p) for p in parts]
        with_vt = [p for p in promoted if "valid_time" in p.dims]
        if len(with_vt) != len(promoted):
            consolidated.extend(parts)
            continue

        # Drop scalar step/stepRange coords that clash across mixed intervals before concat
        cleaned = [p.drop_vars("step", errors="ignore") for p in with_vt]
        combined = xr.concat(cleaned, dim="valid_time", coords="minimal", compat="override")
        combined = combined.sortby("valid_time")
        _, unique_idx = np.unique(combined["valid_time"].values, return_index=True)
        combined = combined.isel(valid_time=np.sort(unique_idx))
        consolidated.append(combined)

    return consolidated


class GribInterpolator:
    """Fill missing forecast steps (default: hourly) by linear interpolation. Writes NetCDF."""

    def __init__(self, file_path: str | Path, freq: str = "1h"):
        self.file_path = Path(file_path)
        self.freq = freq
        self.datasets: list[xr.Dataset] = []

    def __enter__(self):
        # One dataset per incompatible group (surface / isobaric / heightAboveGround / ...)
        raw = cfgrib.open_datasets(
            str(self.file_path),
            backend_kwargs={"indexpath": ""},
        )
        self.datasets = consolidate_grib_datasets(raw)
        return self

    def __exit__(self, *exc):
        for ds in self.datasets:
            try:
                ds.close()
            except Exception:
                pass
        self.datasets = []

    @staticmethod
    def _is_interpolatable(ds: xr.Dataset) -> bool:
        if "step" in ds.dims and ds.sizes["step"] > 1:
            return True
        if "valid_time" in ds.dims and ds.sizes["valid_time"] > 1:
            return True
        return False

    def _interpolate(self, ds: xr.Dataset) -> xr.Dataset:
        if not self._is_interpolatable(ds):
            return ds
        if "step" in ds.dims:
            new_steps = pd.timedelta_range(ds.step.min().values, ds.step.max().values, freq=self.freq)
            ds = ds.drop_vars("valid_time", errors="ignore")  # stale coordinate, rebuilt below
            ds = ds.interp(step=new_steps, method="linear")
            ds = ds.assign_coords(valid_time=ds.time + ds.step)  # real timestamps
            return ds.swap_dims({"step": "valid_time"})  # index by date instead of step

        # Already indexed by valid_time (e.g., consolidated mixed-interval precip)
        new_times = pd.date_range(ds.valid_time.min().values, ds.valid_time.max().values, freq=self.freq)
        return ds.interp(valid_time=new_times, method="linear")

    def run(self) -> list[xr.Dataset]:
        consolidated = consolidate_grib_datasets(self.datasets)
        return [self._interpolate(ds) for ds in consolidated]

    def to_netcdf(self, output_file: str | Path, grouped: bool = False) -> Path:
        """
        grouped=False: merge everything into one flat file (may fail if coords clash).
        grouped=True : one NetCDF group per level type (always safe).
        """
        output_file = Path(output_file)
        results = self.run()

        if grouped:
            for i, ds in enumerate(results):
                level_type = self._level_name(ds, i)
                ds.to_netcdf(output_file, mode="w" if i == 0 else "a", group=level_type)
        else:
            merged = xr.merge(results, compat="override", join="outer")
            merged.to_netcdf(output_file)
        return output_file

    @staticmethod
    def _level_name(ds: xr.Dataset, fallback: int) -> str:
        for v in ds.data_vars.values():
            t = v.attrs.get("GRIB_typeOfLevel")
            if t:
                return t
        return f"group_{fallback}"
