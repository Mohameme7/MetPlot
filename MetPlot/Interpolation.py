from __future__ import annotations

from pathlib import Path

import cfgrib
import pandas as pd
import xarray as xr


class GribInterpolator:
    """Fill missing forecast steps (default: hourly) by linear interpolation. Writes NetCDF."""

    def __init__(self, file_path: str | Path, freq: str = "1h"):
        self.file_path = Path(file_path)
        self.freq = freq
        self.datasets: list[xr.Dataset] = []

    def __enter__(self):
        # One dataset per incompatible group (surface / isobaric / heightAboveGround / ...)
        self.datasets = cfgrib.open_datasets(
            str(self.file_path),
            backend_kwargs={"indexpath": ""},
        )
        return self

    def __exit__(self, *exc):
        for ds in self.datasets:
            ds.close()
        self.datasets = []

    @staticmethod
    def _is_interpolatable(ds: xr.Dataset) -> bool:
        return "step" in ds.dims and ds.sizes["step"] > 1

    def _interpolate(self, ds: xr.Dataset) -> xr.Dataset:
        if not self._is_interpolatable(ds):
            return ds
        new_steps = pd.timedelta_range(ds.step.min().values, ds.step.max().values, freq=self.freq)
        ds = ds.drop_vars("valid_time", errors="ignore")  # stale coordinate, rebuilt below
        ds = ds.interp(step=new_steps, method="linear")
        ds = ds.assign_coords(valid_time=ds.time + ds.step)  # real timestamps
        return ds.swap_dims({"step": "valid_time"})  # index by date instead of step

    def run(self) -> list[xr.Dataset]:
        return [self._interpolate(ds) for ds in self.datasets]

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
