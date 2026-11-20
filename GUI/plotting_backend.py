"""Backend data loader (xarray/cfgrib), CPT parser, and video/GIF exporter for MetPlot."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
from PIL import Image

logger = logging.getLogger(__name__)

# Built-in colormaps (pure RGB stops in 0..255, zero matplotlib dependency)
BUILTIN_COLORMAPS: dict[str, list[list[float]]] = {
    "Turbo": [
        [0.00, 48, 18, 59], [0.10, 69, 91, 205], [0.20, 62, 155, 254],
        [0.30, 24, 215, 203], [0.40, 72, 248, 130], [0.50, 164, 252, 60],
        [0.60, 226, 220, 56], [0.70, 254, 163, 49], [0.80, 239, 89, 17],
        [0.90, 194, 36, 3], [1.00, 122, 4, 3],
    ],
    "Viridis": [
        [0.00, 68, 1, 84], [0.13, 72, 40, 120], [0.25, 62, 74, 137],
        [0.38, 49, 104, 142], [0.50, 38, 130, 142], [0.63, 31, 158, 137],
        [0.75, 53, 183, 121], [0.88, 109, 205, 89], [1.00, 253, 231, 37],
    ],
    "Plasma": [
        [0.00, 13, 8, 135], [0.14, 75, 3, 161], [0.29, 125, 3, 168],
        [0.43, 168, 34, 150], [0.57, 203, 70, 121], [0.71, 229, 107, 93],
        [0.86, 248, 148, 65], [1.00, 240, 249, 33],
    ],
    "Inferno": [
        [0.00, 0, 0, 4], [0.14, 40, 11, 84], [0.29, 101, 21, 110],
        [0.43, 159, 42, 99], [0.57, 212, 72, 66], [0.71, 245, 125, 21],
        [0.86, 250, 193, 39], [1.00, 252, 255, 164],
    ],
    "Coolwarm": [
        [0.00, 59, 76, 192], [0.17, 103, 136, 238], [0.33, 154, 186, 254],
        [0.50, 221, 221, 221], [0.67, 246, 183, 156], [0.83, 226, 105, 82],
        [1.00, 180, 4, 38],
    ],
    "RdBu_r (Temp)": [
        [0.00, 5, 48, 97], [0.125, 33, 102, 172], [0.25, 67, 147, 195],
        [0.375, 146, 197, 222], [0.50, 247, 247, 247], [0.625, 244, 165, 130],
        [0.75, 214, 96, 77], [0.875, 178, 24, 43], [1.00, 103, 0, 31],
    ],
    "Rainbow / Jet": [
        [0.00, 0, 0, 128], [0.15, 0, 0, 255], [0.35, 0, 255, 255],
        [0.50, 0, 255, 0], [0.65, 255, 255, 0], [0.85, 255, 0, 0],
        [1.00, 128, 0, 0],
    ],
    "Blues (Precip)": [
        [0.00, 247, 251, 255], [0.20, 198, 219, 239], [0.40, 107, 174, 214],
        [0.60, 33, 113, 181], [0.80, 8, 69, 148], [1.00, 8, 30, 85],
    ],
    "YlGnBu": [
        [0.00, 255, 255, 217], [0.20, 199, 233, 180], [0.40, 65, 182, 196],
        [0.60, 29, 145, 192], [0.80, 34, 94, 168], [1.00, 8, 29, 88],
    ],
    "Spectral_r": [
        [0.00, 94, 79, 162], [0.14, 50, 136, 189], [0.29, 102, 194, 165],
        [0.43, 171, 221, 164], [0.57, 254, 224, 139], [0.71, 253, 174, 97],
        [0.86, 244, 109, 67], [1.00, 158, 1, 66],
    ],
    "NWS Reflectivity": [
        [0.00, 4, 233, 231], [0.12, 1, 159, 244], [0.24, 3, 0, 244],
        [0.36, 2, 253, 2], [0.48, 1, 197, 1], [0.58, 0, 142, 0],
        [0.68, 253, 248, 2], [0.76, 229, 188, 0], [0.84, 253, 149, 0],
        [0.90, 253, 0, 0], [0.95, 212, 0, 0], [1.00, 248, 0, 253],
    ],
}


def _parse_rgb_token(tokens: list[str]) -> tuple[float, float, float] | None:
    """Parse either 'r/g/b' or three separate 'r', 'g', 'b' tokens."""
    if len(tokens) == 1 and "/" in tokens[0]:
        parts = tokens[0].split("/")
        if len(parts) == 3:
            return float(parts[0]), float(parts[1]), float(parts[2])
    elif len(tokens) == 3:
        return float(tokens[0]), float(tokens[1]), float(tokens[2])
    return None


def parse_cpt_text(cpt_text: str, name: str = "Custom CPT") -> dict[str, Any]:
    """Parse a GMT/GRASS .cpt file into normalized stops + native z-bounds (no matplotlib)."""
    raw_points: list[tuple[float, float, float, float]] = []

    for raw_line in cpt_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line[0] in ("B", "F", "N", "b", "f", "n") and (len(line) == 1 or line[1].isspace()):
            continue

        parts = re.split(r"\s+", line)
        # Format A: z0 r0 g0 b0 z1 r1 g1 b1 (8 tokens)
        if len(parts) >= 8:
            try:
                z0 = float(parts[0])
                r0, g0, b0 = float(parts[1]), float(parts[2]), float(parts[3])
                z1 = float(parts[4])
                r1, g1, b1 = float(parts[5]), float(parts[6]), float(parts[7])
                raw_points.append((z0, r0, g0, b0))
                raw_points.append((z1, r1, g1, b1))
                continue
            except ValueError:
                pass

        # Format B: z0 r0/g0/b0 z1 r1/g1/b1 (4 tokens)
        if len(parts) >= 4:
            try:
                z0 = float(parts[0])
                rgb0 = _parse_rgb_token([parts[1]])
                z1 = float(parts[2])
                rgb1 = _parse_rgb_token([parts[3]])
                if rgb0 and rgb1:
                    raw_points.append((z0, *rgb0))
                    raw_points.append((z1, *rgb1))
                    continue
            except ValueError:
                pass

    if len(raw_points) < 2:
        raise ValueError("No valid color stops found in CPT file.")

    # Deduplicate consecutive identical points while preserving sharp step transitions
    z_vals = [p[0] for p in raw_points]
    zmin, zmax = min(z_vals), max(z_vals)
    span = (zmax - zmin) if zmax > zmin else 1.0

    # If RGB values are in 0..1 scale, upscale to 0..255
    max_c = max(max(p[1], p[2], p[3]) for p in raw_points)
    scale = 255.0 if max_c <= 1.0 else 1.0

    stops: list[list[float]] = []
    for z, r, g, b in sorted(raw_points, key=lambda x: x[0]):
        t = max(0.0, min(1.0, (z - zmin) / span))
        entry = [round(t, 6), round(r * scale, 2), round(g * scale, 2), round(b * scale, 2)]
        if not stops or stops[-1] != entry:
            stops.append(entry)

    return {
        "name": name,
        "stops": stops,
        "vmin": zmin,
        "vmax": zmax,
    }


def _find_coord_name(da: xr.DataArray, candidates: tuple[str, ...]) -> str | None:
    for c in candidates:
        if c in da.dims:
            return c
    for dim in da.dims:
        dl = str(dim).lower()
        for c in candidates:
            if dl == c or dl.startswith(c):
                return str(dim)
    return None


def _format_time_label(val: Any) -> str:
    if isinstance(val, np.datetime64):
        return np.datetime_as_string(val, unit="m").replace("T", " ") + " UTC"
    if isinstance(val, np.timedelta64):
        hours = val / np.timedelta64(1, "h")
        return f"+{hours:g}h"
    return str(val)


@dataclass
class VariableEntry:
    key: str
    var_name: str
    ds_index: int
    group_name: str
    label: str
    units: str
    lat_dim: str
    lon_dim: str
    time_dim: str | None
    level_dim: str | None
    times: list[str]
    levels: list[str]
    level_units: str


class DatasetManager:
    """Manages loaded xarray datasets (NetCDF or GRIB via cfgrib) for WebGL plotting."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.file_path: str | None = None
        self.datasets: list[xr.Dataset] = []
        self.variables: dict[str, VariableEntry] = {}
        self._global_minmax_cache: dict[tuple[str, int], tuple[float, float]] = {}

    def close(self) -> None:
        with self._lock:
            for ds in self.datasets:
                try:
                    ds.close()
                except Exception:
                    pass
            self.datasets = []
            self.variables = {}
            self._global_minmax_cache = {}
            self.file_path = None

    def load_file(self, path: str | Path, append: bool = False) -> dict[str, Any]:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not append:
            self.close()

        ext = path.suffix.lower()
        loaded: list[tuple[str, xr.Dataset]] = []

        if ext in (".grib", ".grib2", ".grb", ".grb2"):
            import cfgrib
            from MetPlot.Interpolation import consolidate_grib_datasets

            dsets = consolidate_grib_datasets(
                cfgrib.open_datasets(
                    str(path),
                    backend_kwargs={"indexpath": ""},
                )
            )
            for i, ds in enumerate(dsets):
                gname = self._infer_group_name(ds, i)
                loaded.append((gname, ds))
        else:
            # NetCDF (supports both flat and grouped NetCDF4 files)
            root_ds = xr.open_dataset(str(path))
            if len(root_ds.data_vars) > 0:
                loaded.append(("root", root_ds))
            else:
                root_ds.close()
                try:
                    import netCDF4

                    with netCDF4.Dataset(str(path), "r") as nc:
                        groups = list(nc.groups.keys())
                    for g in groups:
                        gds = xr.open_dataset(str(path), group=g)
                        if len(gds.data_vars) > 0:
                            loaded.append((g, gds))
                        else:
                            gds.close()
                except Exception as exc:
                    raise RuntimeError(f"Could not read NetCDF groups from {path}: {exc}") from exc

        if not loaded:
            raise ValueError(f"No gridded variables found in {path.name}")

        with self._lock:
            base_idx = len(self.datasets) if append else 0
            if not append or not self.file_path:
                self.file_path = str(path)
            else:
                self.file_path = f"{self.file_path} + {path.name}"
            self.datasets.extend([ds for _, ds in loaded])
            if not append:
                self.variables = {}
                self._global_minmax_cache = {}

            for local_idx, (gname, ds) in enumerate(loaded):
                ds_idx = base_idx + local_idx
                for vname, da in ds.data_vars.items():
                    lat_dim = _find_coord_name(da, ("latitude", "lat", "y"))
                    lon_dim = _find_coord_name(da, ("longitude", "lon", "x"))
                    if not lat_dim or not lon_dim:
                        continue
                    if da.sizes[lat_dim] < 2 or da.sizes[lon_dim] < 2:
                        continue

                    time_dim = _find_coord_name(da, ("valid_time", "time", "step", "forecast_time"))
                    other_dims = [
                        d for d in da.dims if d not in (lat_dim, lon_dim, time_dim)
                    ]
                    level_dim = other_dims[0] if other_dims else None

                    times: list[str] = []
                    if time_dim:
                        coord = da.coords[time_dim].values if time_dim in da.coords else np.arange(da.sizes[time_dim])
                        times = [_format_time_label(t) for t in coord]
                    else:
                        if "valid_time" in da.coords:
                            times = [_format_time_label(da.coords["valid_time"].values)]
                        elif "time" in da.coords:
                            times = [_format_time_label(da.coords["time"].values)]
                        else:
                            times = ["Single Frame"]

                    levels: list[str] = []
                    level_units = ""
                    if level_dim:
                        lcoord = da.coords[level_dim] if level_dim in da.coords else None
                        if lcoord is not None:
                            level_units = str(lcoord.attrs.get("units", ""))
                            levels = [f"{v:g}" if isinstance(v, (float, np.floating)) else str(v) for v in lcoord.values]
                        else:
                            levels = [str(i) for i in range(da.sizes[level_dim])]

                    long_name = str(da.attrs.get("long_name") or da.attrs.get("GRIB_name") or vname)
                    units = str(da.attrs.get("units") or da.attrs.get("GRIB_units") or "")
                    level_type = str(da.attrs.get("GRIB_typeOfLevel") or gname)
                    key = f"{ds_idx}:{vname}"
                    label = f"{vname} — {long_name}"
                    if units:
                        label += f" [{units}]"
                    if (len(loaded) > 1 or append) and level_type and level_type != "root":
                        label += f" ({level_type})"
                    if append:
                        label += f" · {path.name}"

                    self.variables[key] = VariableEntry(
                        key=key,
                        var_name=str(vname),
                        ds_index=ds_idx,
                        group_name=gname,
                        label=label,
                        units=units,
                        lat_dim=lat_dim,
                        lon_dim=lon_dim,
                        time_dim=time_dim,
                        level_dim=level_dim,
                        times=times,
                        levels=levels,
                        level_units=level_units,
                    )

            if not self.variables:
                raise ValueError(f"No 2D lat/lon variables found in {path.name}")

            return self.get_metadata()

    @staticmethod
    def _infer_group_name(ds: xr.Dataset, fallback: int) -> str:
        for v in ds.data_vars.values():
            t = v.attrs.get("GRIB_typeOfLevel")
            if t:
                return str(t)
        return f"group_{fallback}"

    def get_metadata(self) -> dict[str, Any]:
        with self._lock:
            return {
                "file_path": self.file_path,
                "file_name": Path(self.file_path).name if self.file_path else "",
                "variables": [
                    {
                        "key": e.key,
                        "var_name": e.var_name,
                        "label": e.label,
                        "units": e.units,
                        "times": e.times,
                        "levels": e.levels,
                        "level_dim": e.level_dim,
                        "level_units": e.level_units,
                    }
                    for e in self.variables.values()
                ],
            }

    def get_frame(
        self,
        var_key: str,
        time_idx: int = 0,
        level_idx: int = 0,
    ) -> tuple[bytes, dict[str, Any]]:
        """Extract a 2D float32 grid (North-to-South, West-to-East) + metadata."""
        with self._lock:
            if var_key not in self.variables:
                raise KeyError(f"Unknown variable: {var_key}")
            entry = self.variables[var_key]
            ds = self.datasets[entry.ds_index]
            da = ds[entry.var_name]

            isel_dict: dict[str, int] = {}
            if entry.time_dim:
                t_idx = max(0, min(time_idx, da.sizes[entry.time_dim] - 1))
                isel_dict[entry.time_dim] = t_idx
            else:
                t_idx = 0

            if entry.level_dim:
                l_idx = max(0, min(level_idx, da.sizes[entry.level_dim] - 1))
                isel_dict[entry.level_dim] = l_idx
            else:
                l_idx = 0

            # Collapse any extra unexpected dims to index 0
            for d in da.dims:
                if d not in (entry.lat_dim, entry.lon_dim) and d not in isel_dict:
                    isel_dict[d] = 0

            slice_da = da.isel(isel_dict).transpose(entry.lat_dim, entry.lon_dim)

            lats = np.asarray(slice_da.coords[entry.lat_dim].values, dtype=np.float64)
            lons = np.asarray(slice_da.coords[entry.lon_dim].values, dtype=np.float64)
            data = np.asarray(slice_da.values, dtype=np.float32)

            # Normalize 0..360 longitudes to -180..180 for seamless OSM alignment
            if lons.size > 0 and float(np.nanmax(lons)) > 180.0:
                lons_shifted = ((lons + 180.0) % 360.0) - 180.0
                # If global / wraps around dateline, sort columns by shifted lon
                order = np.argsort(lons_shifted)
                lons = lons_shifted[order]
                data = data[:, order]
            elif lons.size > 1 and lons[0] > lons[-1]:
                lons = lons[::-1]
                data = data[:, ::-1]

            # Ensure North-to-South row ordering (row 0 = lat_max, row H-1 = lat_min)
            if lats.size > 1 and lats[0] < lats[-1]:
                lats = lats[::-1]
                data = data[::-1, :]

            finite_mask = np.isfinite(data)
            if np.any(finite_mask):
                frame_min = float(np.min(data[finite_mask]))
                frame_max = float(np.max(data[finite_mask]))
            else:
                frame_min, frame_max = 0.0, 1.0

            # Replace NaN/Inf with sentinel -9.99e30 for reliable WebGL detection
            clean = np.where(finite_mask, data, np.float32(-9.99e30))
            clean = np.ascontiguousarray(clean, dtype="<f4")

            height, width = clean.shape
            time_label = entry.times[t_idx] if t_idx < len(entry.times) else ""
            level_label = (
                f"{entry.levels[l_idx]} {entry.level_units}".strip()
                if entry.levels and l_idx < len(entry.levels)
                else ""
            )

            meta = {
                "width": int(width),
                "height": int(height),
                "latMin": float(np.min(lats)),
                "latMax": float(np.max(lats)),
                "lonMin": float(np.min(lons)),
                "lonMax": float(np.max(lons)),
                "frameMin": frame_min,
                "frameMax": frame_max,
                "varName": entry.var_name,
                "label": entry.label,
                "units": entry.units,
                "timeIdx": t_idx,
                "timeLabel": time_label,
                "levelLabel": level_label,
            }
            return clean.tobytes(), meta

    def get_global_minmax(self, var_key: str, level_idx: int = 0) -> tuple[float, float]:
        """Compute min/max across all timesteps for a variable+level."""
        with self._lock:
            cache_key = (var_key, level_idx)
            if cache_key in self._global_minmax_cache:
                return self._global_minmax_cache[cache_key]

            entry = self.variables[var_key]
            ds = self.datasets[entry.ds_index]
            da = ds[entry.var_name]
            if entry.level_dim:
                l_idx = max(0, min(level_idx, da.sizes[entry.level_dim] - 1))
                da = da.isel({entry.level_dim: l_idx})

            vals = np.asarray(da.values, dtype=np.float32)
            finite = vals[np.isfinite(vals)]
            if finite.size == 0:
                res = (0.0, 1.0)
            else:
                res = (float(np.min(finite)), float(np.max(finite)))
            self._global_minmax_cache[cache_key] = res
            return res


@dataclass
class _ExportSession:
    session_id: str
    temp_dir: str
    output_path: str
    fmt: str  # "mp4" or "gif"
    fps: int
    frames: list[str] = field(default_factory=list)


class ExportSessionManager:
    """Collects composited WebGL+OSM PNG frames and encodes them into MP4 or GIF."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, _ExportSession] = {}

    def start(self, output_path: str, fmt: str = "mp4", fps: int = 6) -> str:
        sid = uuid.uuid4().hex
        temp_dir = tempfile.mkdtemp(prefix=f"metplot_exp_{sid[:8]}_")
        fmt_clean = "gif" if fmt.lower() == "gif" else "mp4"
        with self._lock:
            self._sessions[sid] = _ExportSession(
                session_id=sid,
                temp_dir=temp_dir,
                output_path=output_path,
                fmt=fmt_clean,
                fps=max(1, min(60, int(fps))),
            )
        return sid

    def add_frame(self, sid: str, index: int, png_bytes: bytes) -> int:
        with self._lock:
            sess = self._sessions.get(sid)
            if not sess:
                raise KeyError("Export session not found")
            frame_path = os.path.join(sess.temp_dir, f"frame_{index:05d}.png")
            with open(frame_path, "wb") as f:
                f.write(png_bytes)
            sess.frames.append(frame_path)
            return len(sess.frames)

    def finish(self, sid: str) -> str:
        with self._lock:
            sess = self._sessions.pop(sid, None)
        if not sess:
            raise KeyError("Export session not found")

        try:
            frames = sorted(sess.frames)
            if not frames:
                raise ValueError("No frames were captured for export.")

            out_path = sess.output_path
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

            if sess.fmt == "gif":
                self._encode_gif(frames, out_path, sess.fps)
            else:
                self._encode_mp4(frames, out_path, sess.fps)
            return out_path
        finally:
            shutil.rmtree(sess.temp_dir, ignore_errors=True)

    def abort(self, sid: str) -> None:
        with self._lock:
            sess = self._sessions.pop(sid, None)
        if sess:
            shutil.rmtree(sess.temp_dir, ignore_errors=True)

    @staticmethod
    def _encode_gif(frame_paths: list[str], out_path: str, fps: int) -> None:
        images = []
        for fp in frame_paths:
            img = Image.open(fp).convert("RGB")
            images.append(img.quantize(colors=256, method=Image.Quantize.MEDIANCUT))
        duration_ms = max(20, int(round(1000.0 / fps)))
        images[0].save(
            out_path,
            save_all=True,
            append_images=images[1:],
            duration=duration_ms,
            loop=0,
            optimize=True,
        )

    @staticmethod
    def _encode_mp4(frame_paths: list[str], out_path: str, fps: int) -> None:
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            # Ensure even dimensions for yuv420p compatibility via pad filter
            pattern = os.path.join(os.path.dirname(frame_paths[0]), "frame_%05d.png")
            cmd = [
                ffmpeg_bin,
                "-y",
                "-framerate", str(fps),
                "-i", pattern,
                "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "18",
                "-movflags", "+faststart",
                out_path,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and os.path.exists(out_path):
                return
            logger.warning("ffmpeg failed (%s), falling back to OpenCV", res.stderr)

        # Fallback to OpenCV VideoWriter
        import cv2

        first = cv2.imread(frame_paths[0])
        h, w = first.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_path, fourcc, float(fps), (w, h))
        try:
            for fp in frame_paths:
                img = cv2.imread(fp)
                if img.shape[:2] != (h, w):
                    img = cv2.resize(img, (w, h))
                writer.write(img)
        finally:
            writer.release()
