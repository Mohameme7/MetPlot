import asyncio
import json
import logging
import multiprocessing
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(__file__))

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _ecc_defs = os.path.join(sys._MEIPASS, "share", "eccodes", "definitions")
    if os.path.isdir(_ecc_defs):
        os.environ.setdefault("ECCODES_DEFINITION_PATH", _ecc_defs)

import requests
import webview
from fastapi import Request, Response
from fastapi.responses import HTMLResponse
from nicegui import app, run as run_nc, ui

from modeldownloads import load
from MetPlot.Downloader.Parsers.GEM import GEMUSE
from MetPlot.Downloader.Parsers.NomadsUtils import GFSUSE
from MetPlot.Downloader.Parsers.ecmwf import ECMWFUSE
from MetPlot.Downloader.Parsers.icon import ICONUSE
from MetPlot.Downloader.misc import file_read
from MetPlot.Variables import catalog_path
from MetPlot.utils.CMAPTest import PlotData
from plotting_backend import (
    BUILTIN_COLORMAPS,
    DatasetManager,
    ExportSessionManager,
    parse_cpt_text,
)

multiprocessing.set_start_method("spawn", force=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app.title = "MetPlot"
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
template_path = os.path.join(BASE_DIR, "templates", "CoordsMAP.html")
plot_template_path = os.path.join(BASE_DIR, "templates", "PlotMAP.html")
CoordsHTML = open(template_path, encoding="utf-8").read()

try:
    _resp = requests.get("https://nomads.ncep.noaa.gov/gribfilter.php?ds=gfs_0p25", timeout=10)
    content = _resp.content
except Exception as exc:
    logging.warning("Could not prefetch NOMADS GFS page: %s", exc)
    content = b""

download_button: ui.button
temp_elements = []

# Shared backend managers for the Plotting page
dataset_mgr = DatasetManager()
export_mgr = ExportSessionManager()
custom_colormaps: dict[str, dict] = {}


class PlotAppState:
    def __init__(self):
        self.pending_file: str | None = None


plot_app_state = PlotAppState()


# ---------------- FastAPI Routes for WebGL Plotter ----------------
@app.get("/plot_canvas")
def serve_plot_canvas():
    html = open(plot_template_path, encoding="utf-8").read()
    return HTMLResponse(content=html)


@app.get("/api/plot/grid")
def api_plot_grid(var_key: str, time_idx: int = 0, level_idx: int = 0):
    try:
        raw_bytes, meta = dataset_mgr.get_frame(var_key, time_idx=time_idx, level_idx=level_idx)
        return Response(
            content=raw_bytes,
            media_type="application/octet-stream",
            headers={
                "X-Grid-Meta": json.dumps(meta),
                "Cache-Control": "no-store",
            },
        )
    except Exception as exc:
        return Response(content=str(exc), status_code=400)


@app.post("/api/plot/export/frame")
async def api_plot_export_frame(request: Request, sid: str, idx: int):
    try:
        body = await request.body()
        count = export_mgr.add_frame(sid, idx, body)
        return {"ok": True, "count": count}
    except Exception as exc:
        return Response(content=str(exc), status_code=400)


# ---------------- Global Navbar ----------------
def global_navbar():
    ui.dark_mode().enable()
    with ui.row().style(
        """
        background-color: #1a1a1d; color: white; display: flex; justify-content: space-between;
        align-items: center; padding: 12px 30px; position: fixed; top: 0; left: 0; right: 0;
        z-index: 1000; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.25); height: 74px;
        """
    ):
        ui.label("MetPlot").style(
            """
            font-weight: bold; text-transform: uppercase; letter-spacing: 2px;
            background-color: #ef4444; color: white; font-size: 22px;
            padding: 10px 32px; border-radius: 10px;
            """
        )
        with ui.row().style("display: flex; gap: 26px; align-items: center;"):
            link_style = (
                "color: white; text-decoration: none; font-size: 15px; "
                "text-transform: uppercase; transition: color 0.2s ease;"
            )
            ui.link("Home", "/").style(link_style)
            ui.link("Download", "/download").style(link_style)
            ui.link("Plot", "/plot").style(link_style + " font-weight: 700; color: #f87171;")
            ui.link("Settings", "/settings").style(link_style)
            ui.link("ColormapTest", "/colormaptest").style(link_style)
            ui.button(
                "CPT_App",
                on_click=lambda: subprocess.Popen([sys.executable, "-m", "MetPlot.utils.colorgen"]),
                color="#27272a",
            )


class AppState:
    def __init__(self):
        self.inputs = {}


state = AppState()


def initialize_coords():
    labels = ["Top Latitude", "Bottom Latitude", "Left Longitude", "Right Longitude"]
    for label in labels:
        with ui.column():
            ui.label(label)
            key = label.split()[0].lower()
            state.inputs[key] = ui.input(
                on_change=lambda: update_bounding_box_from_inputs(state.inputs)
            )


@app.get("/update_coordinates/{top}/{bottom}/{left}/{right}")
def update_coordinates(top: float, bottom: float, left: float, right: float):
    if state.inputs:
        state.inputs["top"].value = str(top)
        state.inputs["bottom"].value = str(bottom)
        state.inputs["left"].value = str(left)
        state.inputs["right"].value = str(right)
    return {"message": "ok"}


def open_in_plotter(file_path: str):
    plot_app_state.pending_file = os.path.abspath(file_path)
    ui.navigate.to("/plot")


model_loads = {
    "GFS": lambda: load(
        GFSUSE(content),
        download_button,
        state.inputs["top"],
        state.inputs["bottom"],
        state.inputs["left"],
        state.inputs["right"],
        temp_elements,
        on_open_in_plotter=open_in_plotter,
    ),
    "GEM": lambda: load(
        GEMUSE("GEM"),
        download_button,
        state.inputs["top"],
        state.inputs["bottom"],
        state.inputs["left"],
        state.inputs["right"],
        temp_elements,
        on_open_in_plotter=open_in_plotter,
    ),
    "GEPS": lambda: load(
        GEMUSE("GEPS"),
        download_button,
        state.inputs["top"],
        state.inputs["bottom"],
        state.inputs["left"],
        state.inputs["right"],
        temp_elements,
        on_open_in_plotter=open_in_plotter,
    ),
    "ICON": lambda: load(
        ICONUSE(file_read(catalog_path("ICON", "MERGED_PARAMS.json"))),
        download_button,
        state.inputs["top"],
        state.inputs["bottom"],
        state.inputs["left"],
        state.inputs["right"],
        temp_elements,
        on_open_in_plotter=open_in_plotter,
    ),
    "ECMWF IFS 0.1°": lambda: load(
        ECMWFUSE("IFS_0P1"),
        download_button,
        state.inputs["top"],
        state.inputs["bottom"],
        state.inputs["left"],
        state.inputs["right"],
        temp_elements,
        on_open_in_plotter=open_in_plotter,
    ),
    "ECMWF IFS 0.25°": lambda: load(
        ECMWFUSE("IFS_0P25"),
        download_button,
        state.inputs["top"],
        state.inputs["bottom"],
        state.inputs["left"],
        state.inputs["right"],
        temp_elements,
        on_open_in_plotter=open_in_plotter,
    ),
    "ECMWF AIFS 0.25°": lambda: load(
        ECMWFUSE("AIFS_0P25"),
        download_button,
        state.inputs["top"],
        state.inputs["bottom"],
        state.inputs["left"],
        state.inputs["right"],
        temp_elements,
        on_open_in_plotter=open_in_plotter,
    ),
}


def model_load(variables_file: str, levels_file: str, model: str):
    while temp_elements:
        element = temp_elements.pop()
        try:
            element.delete()
        except RuntimeError:
            pass
    if model in model_loads:
        model_loads[model]()
    variables = file_read(variables_file)
    level_data = file_read(levels_file)
    level_data = [
        (line.strip(), line.strip().replace("lev_", "").replace("_mb", "mb"))
        for line in level_data
    ]

    with ui.column().style("margin-top: 15px; padding: 10px;") as el:
        temp_elements.append(el)
        ui.label("Variables").style("font-size: 14px;")
        keys = list(variables.keys())
        for i in range(0, len(keys), 12):
            with ui.row().classes("flex-wrap").style(
                "align-items: center; margin-bottom: -8px; justify-content: space-evenly; gap: 5px;"
            ):
                for key in keys[i : i + 12]:
                    levels_str = ", ".join(variables[key]["levels"])
                    ui.checkbox(text=key).tooltip(
                        f'Name: {variables[key]["name"]}, \n Levels: {levels_str}'
                    ).mark("Variable")

    with ui.column().style("margin-top: 15px; padding: 10px;") as el:
        temp_elements.append(el)
        ui.label("Vertical Levels").style("font-size: 14px;")
        with ui.row().classes("flex-wrap").style("align-items: center; margin-bottom: -8px;"):
            for original, formatted in level_data:
                ui.checkbox(text=formatted).mark(f"Level {original}")


MODELS = {
    "GFS": lambda: model_load(
        catalog_path("GFS", "MERGED_PARAMS.json"),
        catalog_path("GFS", "VERTICAL_LEVELS.txt"),
        "GFS",
    ),
    "GEM": lambda: model_load(
        catalog_path("CMC/GEM", "MERGED_PARAMS.json"),
        catalog_path("CMC/GEM", "VERTICAL_LEVELS.txt"),
        "GEM",
    ),
    "ICON": lambda: model_load(
        catalog_path("ICON", "MERGED_PARAMS.json"),
        catalog_path("ICON", "VERTICAL_LEVELS.txt"),
        "ICON",
    ),
    "GEPS": lambda: model_load(
        catalog_path("CMC/GEPS", "MERGED_PARAMS.json"),
        catalog_path("CMC/GEPS", "VERTICAL_LEVELS.txt"),
        "GEPS",
    ),
    "ECMWF IFS 0.1°": lambda: model_load(
        catalog_path("ECMWF/IFS", "MERGED_PARAMS.json"),
        catalog_path("ECMWF/IFS", "VERTICAL_LEVELS.txt"),
        "ECMWF IFS 0.1°",
    ),
    "ECMWF IFS 0.25°": lambda: model_load(
        catalog_path("ECMWF/IFS", "MERGED_PARAMS.json"),
        catalog_path("ECMWF/IFS", "VERTICAL_LEVELS.txt"),
        "ECMWF IFS 0.25°",
    ),
    "ECMWF AIFS 0.25°": lambda: model_load(
        catalog_path("ECMWF/AIFS", "MERGED_PARAMS.json"),
        catalog_path("ECMWF/AIFS", "VERTICAL_LEVELS.txt"),
        "ECMWF AIFS 0.25°",
    ),
}


def update_bounding_box_from_inputs(refs):
    try:
        top = float(refs["top"].value)
        bottom = float(refs["bottom"].value)
        left = float(refs["left"].value)
        right = float(refs["right"].value)
        ui.run_javascript(f"updateBoundingBoxFromInputs({top}, {bottom}, {left}, {right});")
    except (ValueError, KeyError, AttributeError):
        ui.notify("Please enter valid coordinates.")


# ---------------- Pages ----------------
@ui.page("/")
def main_page():
    global_navbar()
    with ui.column().style("margin-top: 100px; padding: 24px; gap: 12px;"):
        ui.label("MetPlot — Meteorological Data Downloader & WebGL Plotter").style(
            "font-size: 24px; font-weight: 700;"
        )
        ui.label(
            "Download GFS, GEM, GEPS, or ICON weather model data, then visualize and animate "
            "NetCDF/GRIB fields on OpenStreetMap with hardware-accelerated WebGL shaders."
        ).style("color: #cbd5e1; max-width: 720px;")
        with ui.row().style("gap: 12px; margin-top: 8px;"):
            ui.button("Go to Download", on_click=lambda: ui.navigate.to("/download"), color="#27272a")
            ui.button("Open WebGL Plotter", on_click=lambda: ui.navigate.to("/plot"), color="#ef4444")


@ui.page("/download")
def downloader_page():
    global_navbar()
    global download_button
    temp_elements.clear()
    state.inputs.clear()

    ui.select(
        label="Model",
        options=list(MODELS.keys()),
        on_change=lambda model: MODELS[model.value](),
    ).style("margin-top: 100px;")
    with ui.row().style("gap: 10px; margin-top: 20px; padding: 10px;"):
        initialize_coords()
    with ui.column():
        download_button = ui.button("Download").style("margin-top: 50px;")

    ui.add_body_html(CoordsHTML)


async def file_select_open(file_types=None):
    kwargs = {"dialog_type": webview.OPEN_DIALOG}
    if file_types:
        kwargs["file_types"] = file_types
    file = await app.native.main_window.create_file_dialog(**kwargs)
    return file if file else None


async def file_select_save(save_filename="", file_types=None):
    kwargs = {"dialog_type": webview.SAVE_DIALOG}
    if save_filename:
        kwargs["save_filename"] = save_filename
    if file_types:
        kwargs["file_types"] = file_types
    file = await app.native.main_window.create_file_dialog(**kwargs)
    if isinstance(file, (tuple, list)):
        return file[0] if file else None
    return file if file else None


# ---------------- NEW PLOTTING PAGE ----------------
RENDER_MODES = {
    "Smooth (WebGL)": 0,
    "Filled Contours": 1,
    "Smooth + Contour Lines": 2,
    "Filled + Contour Lines": 3,
    "Contour Lines Only": 4,
}
RENDER_MODE_NAMES = {v: k for k, v in RENDER_MODES.items()}

BASEMAP_OPTIONS = {
    "OpenStreetMap": "osm",
    "OpenTopoMap": "opentopo",
    "OSM Humanitarian": "osm_hot",
}

UNIT_PRESETS = {
    "Custom / Raw": (1.0, 0.0, ""),
    "K → °C (-273.15)": (1.0, -273.15, "°C"),
    "Pa → hPa (×0.01)": (0.01, 0.0, "hPa"),
    "m → mm (×1000)": (1000.0, 0.0, "mm"),
    "kg/m²/s → mm/h (×3600)": (3600.0, 0.0, "mm/h"),
    "m/s → kt (×1.94384)": (1.94384, 0.0, "kt"),
    "m/s → km/h (×3.6)": (3.6, 0.0, "km/h"),
    "gpm → dam (×0.1)": (0.1, 0.0, "dam"),
}

WIND_UNIT_PRESETS = {
    "m/s (×1)": (1.0, "m/s"),
    "kt (×1.94384)": (1.94384, "kt"),
    "km/h (×3.6)": (3.6, "km/h"),
}

LABEL_COLORS = {
    "White": "#ffffff",
    "Yellow": "#fde047",
    "Red": "#f87171",
    "Cyan": "#22d3ee",
    "Lime": "#4ade80",
}


@ui.page("/plot")
async def plot_page():
    global_navbar()

    ui.add_head_html(
        """
        <style>
          body { overflow: hidden; }
          .nicegui-content { padding: 0 !important; margin: 0 !important; }
        </style>
        <script>
          window._metplotCall = function(fnName, ...args) {
            return new Promise((resolve, reject) => {
              const start = Date.now();
              function attempt() {
                const f = document.getElementById('plot-frame');
                if (f && f.contentWindow && f.contentWindow.MetPlotGL) {
                  try {
                    const res = f.contentWindow.MetPlotGL[fnName](...args);
                    Promise.resolve(res).then(resolve).catch(reject);
                  } catch (e) {
                    reject(e);
                  }
                } else if (Date.now() - start > 10000) {
                  reject(new Error('WebGL plot iframe timed out'));
                } else {
                  setTimeout(attempt, 80);
                }
              }
              attempt();
            });
          };
          if (!window._metplotMsgBound) {
            window._metplotMsgBound = true;
            window.addEventListener('message', (e) => {
              if (!e.data) return;
              if (e.data.type === 'metplot_time_sync') {
                emitEvent('metplot_time_sync', e.data);
              } else if (e.data.type === 'metplot_label_added') {
                emitEvent('metplot_label_added', e.data);
              }
            });
          }
        </script>
        """
    )

    ps = SimpleNamespace(
        meta=None,
        layers=[],          # list[dict] ordered bottom -> top
        active_id=None,
        next_layer_num=1,
        time_float=0.0,
        num_times=1,
        playing=False,
        steps_per_sec=2.0,
        smooth_interp=True,
        syncing_slider=False,
        syncing_editor=False,
        basemap="osm",
        loading_frame=False,
        map_labels=[],      # list[dict]
        place_label_mode=False,
        hud_title="",
        hud_subtitle="",
        show_title=True,
        show_colorbar=True,
    )

    def _all_cmap_names():
        return list(BUILTIN_COLORMAPS.keys()) + list(custom_colormaps.keys())

    def _get_cmap_stops(name: str):
        if name in custom_colormaps:
            return custom_colormaps[name]["stops"]
        return BUILTIN_COLORMAPS.get(name, BUILTIN_COLORMAPS["Turbo"])

    def _get_var_info(var_key: str):
        if not ps.meta:
            return None
        return next((v for v in ps.meta["variables"] if v["key"] == var_key), None)

    def _active_layer():
        return next((l for l in ps.layers if l["id"] == ps.active_id), None)

    def _max_times():
        if not ps.layers or not ps.meta:
            return 1
        mx = 1
        for l in ps.layers:
            vk = l.get("varKey") if l["type"] == "scalar" else l.get("uVarKey")
            vi = _get_var_info(vk)
            if vi:
                mx = max(mx, len(vi["times"]))
        return mx

    def _serialize_layer(l: dict) -> dict:
        out = dict(l)
        if l["type"] == "scalar":
            out["cmapStops"] = _get_cmap_stops(l["cmapName"])
            out["lineColor"] = [0.08, 0.08, 0.08] if l["lineColorName"] == "Dark" else [0.96, 0.96, 0.96]
        return out

    async def sync_layers_to_gl(fit_bounds: bool = False):
        ps.num_times = _max_times()
        time_slider._props["max"] = max(0, ps.num_times - 1)
        time_slider.update()
        specs = [_serialize_layer(l) for l in ps.layers]
        meta = await ui.run_javascript(
            f"window._metplotCall('syncLayers', {json.dumps(specs)}, {json.dumps(ps.active_id)}, "
            f"{int(ps.num_times)}, {json.dumps(fit_bounds)})",
            timeout=20.0,
        )
        return meta

    async def push_layer_style(layer: dict):
        if not layer:
            return
        patch = _serialize_layer(layer)
        await ui.run_javascript(
            f"window._metplotCall('updateLayerStyle', {json.dumps(layer['id'])}, {json.dumps(patch)})"
        )

    async def push_playback():
        cfg = {
            "playing": bool(ps.playing),
            "stepsPerSec": float(ps.steps_per_sec),
            "smooth": bool(ps.smooth_interp),
            "numTimes": int(ps.num_times),
        }
        await ui.run_javascript(f"window._metplotCall('setPlayback', {json.dumps(cfg)})")

    async def push_hud_config():
        cfg = {
            "customTitle": ps.hud_title,
            "customSubtitle": ps.hud_subtitle,
            "showTitle": bool(ps.show_title),
            "showColorbar": bool(ps.show_colorbar),
        }
        await ui.run_javascript(f"window._metplotCall('setHudConfig', {json.dumps(cfg)})")

    async def push_map_labels():
        await ui.run_javascript(f"window._metplotCall('setMapLabels', {json.dumps(ps.map_labels)})")
        render_labels_list()

    async def render_current_time(fit_bounds: bool = False):
        if not ps.layers or ps.loading_frame:
            return
        ps.loading_frame = True
        try:
            meta = await ui.run_javascript(
                f"window._metplotCall('loadTime', {float(ps.time_float)}, {json.dumps(fit_bounds)})",
                timeout=15.0,
            )
            if meta:
                idx_i = max(0, min(ps.num_times - 1, int(ps.time_float)))
                time_readout.set_text(f"{meta.get('timeLabel', '')}   ({idx_i + 1} / {ps.num_times})")
        except Exception as exc:
            logging.error("Frame render error: %s", exc)
        finally:
            ps.loading_frame = False

    def _on_time_sync(e):
        if not ps.playing:
            return
        data = e.args or {}
        t = float(data.get("t", 0.0))
        tlabel = data.get("timeLabel", "")
        n_times = int(data.get("numTimes", 1))
        ps.time_float = t
        ps.syncing_slider = True
        try:
            time_slider.set_value(round(t, 2))
        finally:
            ps.syncing_slider = False
        idx_disp = min(n_times, int(t) + 1)
        time_readout.set_text(f"{tlabel}   ({idx_disp} / {n_times})")

    def _on_label_added(e):
        lbl = (e.args or {}).get("label")
        if lbl:
            ps.map_labels.append(lbl)
            render_labels_list()

    ui.on("metplot_time_sync", _on_time_sync)
    ui.on("metplot_label_added", _on_label_added)

    # ---------------- Layer Factory & Management ----------------
    def _make_scalar_layer(var_key: str, mode: int = 0, opacity: float = 0.78) -> dict:
        vinfo = _get_var_info(var_key)
        lid = f"layer_{ps.next_layer_num}"
        ps.next_layer_num += 1
        return {
            "id": lid,
            "type": "scalar",
            "visible": True,
            "varKey": var_key,
            "levelIdx": 0,
            "numTimes": len(vinfo["times"]) if vinfo else 1,
            "customName": vinfo["var_name"] if vinfo else var_key,
            "displayUnit": vinfo["units"] if vinfo else "",
            "scale": 1.0,
            "offset": 0.0,
            "mode": mode,
            "opacity": opacity,
            "vmin": 0.0,
            "vmax": 1.0,
            "contourLevels": 14,
            "lineWidth": 1.3,
            "lineColorName": "Dark",
            "clipOutOfRange": False,
            "maskBelow": False,
            "maskThreshold": 0.0,
            "cmapName": "Turbo",
        }

    def _make_wind_layer(u_key: str, v_key: str) -> dict:
        uinfo = _get_var_info(u_key)
        lid = f"wind_{ps.next_layer_num}"
        ps.next_layer_num += 1
        return {
            "id": lid,
            "type": "wind",
            "visible": True,
            "uVarKey": u_key,
            "vVarKey": v_key,
            "levelIdx": 0,
            "numTimes": len(uinfo["times"]) if uinfo else 1,
            "customName": "Wind Vectors",
            "vectorStyle": "arrows",
            "spacing": 36,
            "vectorScale": 1.0,
            "colorMode": "white",
            "opacity": 0.9,
            "scale": 1.0,
            "displayUnit": "m/s",
        }

    async def _autoscale_layer_frame(layer: dict):
        if not layer or layer["type"] != "scalar":
            return
        try:
            _, fmeta = await run_nc.io_bound(
                dataset_mgr.get_frame, layer["varKey"], int(ps.time_float), int(layer["levelIdx"])
            )
            sc = float(layer.get("scale", 1.0))
            off = float(layer.get("offset", 0.0))
            lo = fmeta["frameMin"] * sc + off
            hi = fmeta["frameMax"] * sc + off
            if hi < lo:
                lo, hi = hi, lo
            layer["vmin"] = round(lo, 4)
            layer["vmax"] = round(hi if hi > lo else lo + 1.0, 4)
        except Exception as exc:
            logging.error("Auto-frame failed: %s", exc)

    async def _autoscale_layer_all(layer: dict):
        if not layer or layer["type"] != "scalar":
            return
        try:
            gmin, gmax = await run_nc.io_bound(
                dataset_mgr.get_global_minmax, layer["varKey"], int(layer["levelIdx"])
            )
            sc = float(layer.get("scale", 1.0))
            off = float(layer.get("offset", 0.0))
            lo = gmin * sc + off
            hi = gmax * sc + off
            if hi < lo:
                lo, hi = hi, lo
            layer["vmin"] = round(lo, 4)
            layer["vmax"] = round(hi if hi > lo else lo + 1.0, 4)
        except Exception as exc:
            ui.notify(f"Auto-scale failed: {exc}", type="negative")

    async def add_scalar_layer_action(var_key: str | None = None, mode: int = 0, opacity: float = 0.78, fit: bool = False):
        if not ps.meta or not ps.meta["variables"]:
            ui.notify("Load a NetCDF or GRIB file first.", type="warning")
            return
        vk = var_key or ps.meta["variables"][0]["key"]
        layer = _make_scalar_layer(vk, mode=mode, opacity=opacity)
        await _autoscale_layer_frame(layer)
        ps.layers.append(layer)
        ps.active_id = layer["id"]
        render_layer_stack()
        populate_style_editor()
        await sync_layers_to_gl(fit_bounds=fit)

    async def open_add_wind_dialog():
        if not ps.meta or not ps.meta["variables"]:
            ui.notify("Load a NetCDF or GRIB file first.", type="warning")
            return
        var_opts = {v["key"]: v["label"] for v in ps.meta["variables"]}
        keys = list(var_opts.keys())
        # Auto-guess U and V variables if present
        guess_u = next((v["key"] for v in ps.meta["variables"] if v["var_name"].lower() in ("u", "u10", "u100", "ugrd", "u_component_of_wind")), keys[0])
        guess_v = next((v["key"] for v in ps.meta["variables"] if v["var_name"].lower() in ("v", "v10", "v100", "vgrd", "v_component_of_wind")), keys[min(1, len(keys) - 1)])

        with ui.dialog() as wdlg, ui.card().style("padding: 20px; width: 400px;"):
            ui.label("Add Wind Vector Layer").style("font-size: 17px; font-weight: 700;")
            u_sel = ui.select(label="U-Component (East-West)", options=var_opts, value=guess_u).classes("w-full")
            v_sel = ui.select(label="V-Component (North-South)", options=var_opts, value=guess_v).classes("w-full")
            style_sel = ui.select(label="Vector Style", options={"arrows": "Arrows", "barbs": "Wind Barbs (kt)"}, value="arrows").classes("w-full")

            async def _confirm_wind():
                wl = _make_wind_layer(u_sel.value, v_sel.value)
                wl["vectorStyle"] = style_sel.value
                ps.layers.append(wl)
                ps.active_id = wl["id"]
                wdlg.close()
                render_layer_stack()
                populate_style_editor()
                await sync_layers_to_gl(fit_bounds=False)
                sidebar_tabs.set_value("Style")

            with ui.row().classes("w-full justify-end gap-2 mt-3"):
                ui.button("Cancel", on_click=wdlg.close, color="#3f3f46")
                ui.button("Add Wind Layer", on_click=_confirm_wind, color="#ef4444")
        wdlg.open()

    async def load_dataset_path(path_str: str, append: bool = False):
        if not path_str or not path_str.strip():
            return
        path_str = path_str.strip().strip('"')
        ps.playing = False
        play_btn.props("icon=play_arrow")
        await push_playback()
        status_label.set_text(f"Loading {Path(path_str).name} ...")
        try:
            meta = await run_nc.io_bound(dataset_mgr.load_file, path_str, append)
        except Exception as exc:
            status_label.set_text("Load failed")
            ui.notify(f"Failed to load file: {exc}", type="negative")
            return

        ps.meta = meta
        file_path_input.set_value(meta["file_path"])
        status_label.set_text(f"Loaded: {meta['file_name']} ({len(meta['variables'])} vars)")

        var_opts = {v["key"]: v["label"] for v in meta["variables"]}
        sc_var_select.set_options(var_opts)
        w_u_select.set_options(var_opts)
        w_v_select.set_options(var_opts)

        if not append or not ps.layers:
            ps.layers = []
            ps.time_float = 0.0
            first_key = meta["variables"][0]["key"]
            await add_scalar_layer_action(first_key, mode=0, opacity=0.78, fit=True)
        else:
            ui.notify(f"Merged {Path(path_str).name} — add a new layer to overlay its variables!", type="positive")
            populate_style_editor()

    async def pick_data_file(append: bool = False):
        res = await file_select_open(
            file_types=("Weather Files (*.nc;*.nc4;*.grib;*.grib2;*.grb;*.grb2)", "All files (*.*)")
        )
        if res:
            fpath = res[0] if isinstance(res, (tuple, list)) else res
            await load_dataset_path(fpath, append=append)

    async def upload_cpt_native():
        layer = _active_layer()
        if not layer or layer["type"] != "scalar":
            ui.notify("Select a scalar/contour layer first.", type="warning")
            return
        res = await file_select_open(file_types=("CPT Colormap (*.cpt)", "All files (*.*)"))
        if not res:
            return
        fpath = res[0] if isinstance(res, (tuple, list)) else res
        try:
            text = Path(fpath).read_text(encoding="utf-8", errors="ignore")
            parsed = parse_cpt_text(text, name=f"CPT: {Path(fpath).stem}")
            custom_colormaps[parsed["name"]] = parsed
            sc_cmap_select.set_options(_all_cmap_names())
            layer["cmapName"] = parsed["name"]
            layer["vmin"] = round(parsed["vmin"], 4)
            layer["vmax"] = round(parsed["vmax"], 4)
            populate_style_editor()
            await push_layer_style(layer)
            ui.notify(f"Loaded {parsed['name']} (bounds: {layer['vmin']} .. {layer['vmax']})", type="positive")
        except Exception as exc:
            ui.notify(f"Invalid CPT file: {exc}", type="negative")

    # ---------------- 60 FPS GPU Animation Controls ----------------
    async def toggle_play():
        if ps.num_times <= 1 or not ps.layers:
            return
        ps.playing = not ps.playing
        play_btn.props("icon=pause" if ps.playing else "icon=play_arrow")
        await push_playback()

    async def step_frame(delta: int):
        if ps.num_times <= 1 or not ps.layers:
            return
        if ps.playing:
            ps.playing = False
            play_btn.props("icon=play_arrow")
            await push_playback()
        base = int(round(ps.time_float))
        ps.time_float = float((base + delta) % ps.num_times)
        ps.syncing_slider = True
        try:
            time_slider.set_value(ps.time_float)
        finally:
            ps.syncing_slider = False
        await render_current_time()

    # ---------------- Export Dialog ----------------
    async def open_export_dialog():
        if not ps.layers:
            ui.notify("Load a dataset first before exporting.", type="warning")
            return
        ps.playing = False
        play_btn.props("icon=play_arrow")
        await push_playback()

        n_times = ps.num_times
        drawn_box = await ui.run_javascript("window._metplotCall('getRegionBounds')")
        view_box = await ui.run_javascript("window._metplotCall('getCurrentViewBounds')")
        init_box = drawn_box or view_box or [45.0, 10.0, 20.0, 60.0]

        with ui.dialog() as exp_dlg, ui.card().style("padding: 22px; width: 450px;"):
            ui.label("Export Multi-Layer Animation (Video / GIF)").style("font-size: 18px; font-weight: 700;")
            ui.label(
                "Exports all visible layers (WebGL shading, contours, wind vectors, map labels, "
                "OSM basemap & HUD) with smooth GPU transitions."
            ).style("font-size: 12px; color: #94a3b8; margin-bottom: 8px;")

            fmt_select = ui.select(
                label="Output Format",
                options={"mp4": "MP4 Video (.mp4)", "gif": "Animated GIF (.gif)"},
                value="mp4",
            ).classes("w-full")

            region_mode = ui.select(
                label="Region",
                options={
                    "view": "Current Map Viewport",
                    "drawn": "Drawn Box (Shift+Drag)" if drawn_box else "Drawn Box (none drawn yet)",
                    "custom": "Custom Lat/Lon Bounding Box",
                },
                value="drawn" if drawn_box else "view",
            ).classes("w-full")

            with ui.grid(columns=2).classes("w-full gap-2") as bbox_grid:
                exp_top = ui.number(label="Top Lat", value=init_box[0], format="%.3f")
                exp_bot = ui.number(label="Bottom Lat", value=init_box[1], format="%.3f")
                exp_left = ui.number(label="Left Lon", value=init_box[2], format="%.3f")
                exp_right = ui.number(label="Right Lon", value=init_box[3], format="%.3f")
            bbox_grid.bind_visibility_from(region_mode, "value", backward=lambda v: v == "custom")

            with ui.row().classes("w-full gap-2"):
                start_in = ui.number(label="Start Step", value=0, min=0, max=max(0, n_times - 1), step=1).classes("flex-1")
                end_in = ui.number(label="End Step", value=max(0, n_times - 1), min=0, max=max(0, n_times - 1), step=1).classes("flex-1")

            with ui.row().classes("w-full gap-2"):
                subframes_select = ui.select(
                    label="Smoothness (Sub-frames/step)",
                    options={
                        1: "1 (Discrete steps)",
                        3: "3 (Light smooth)",
                        6: "6 (Smooth)",
                        12: "12 (Ultra smooth)",
                    },
                    value=6 if ps.smooth_interp else 1,
                ).classes("flex-1")
                fps_in = ui.number(label="Output FPS", value=24 if ps.smooth_interp else 6, min=1, max=60, step=1).classes("w-28")

            export_scale_sel = ui.select(
                label="Export Resolution",
                options={1: "1x (Viewport)", 2: "2x (Ultra HD / Supersampled)"},
                value=2,
            ).classes("w-full")

            include_hud_cb = ui.checkbox("Include Title, Timestamp & Colorbar HUD", value=True)
            exp_progress = ui.linear_progress(value=0).classes("w-full")
            exp_progress.set_visibility(False)
            exp_status = ui.label("").style("font-size: 12px; color: #cbd5e1;")

            async def run_export_action():
                s_idx = max(0, min(n_times - 1, int(start_in.value or 0)))
                e_idx = max(s_idx, min(n_times - 1, int(end_in.value or 0)))
                subf = max(1, int(subframes_select.value or 1))
                fps_val = max(1, min(60, int(fps_in.value or 24)))
                exp_scale = max(1, min(2, int(export_scale_sel.value or 1)))
                fmt = fmt_select.value

                bbox = None
                if region_mode.value == "drawn":
                    if not drawn_box:
                        ui.notify("No Shift+Drag box drawn; using current map view.", type="warning")
                    else:
                        bbox = drawn_box
                elif region_mode.value == "custom":
                    bbox = [
                        float(exp_top.value), float(exp_bot.value),
                        float(exp_left.value), float(exp_right.value),
                    ]

                out_path = await file_select_save(
                    save_filename=f"metplot_animation.{fmt}",
                    file_types=(("MP4 Video (*.mp4)",) if fmt == "mp4" else ("Animated GIF (*.gif)",)),
                )
                if not out_path:
                    return
                if not out_path.lower().endswith(f".{fmt}"):
                    out_path += f".{fmt}"

                total_frames = (e_idx - s_idx) * subf + 1
                export_go_btn.disable()
                exp_progress.set_visibility(True)
                exp_progress.set_value(0.05)
                exp_status.set_text(f"Rendering {total_frames} multi-layer frames ({exp_scale}x HD)...")

                sid = export_mgr.start(out_path, fmt=fmt, fps=fps_val)
                try:
                    opts = {
                        "sessionId": sid,
                        "startIdx": s_idx,
                        "endIdx": e_idx,
                        "includeHud": bool(include_hud_cb.value),
                        "bbox": bbox,
                        "subframes": subf,
                        "exportScale": exp_scale,
                    }
                    timeout_sec = max(90.0, total_frames * 1.4)
                    await ui.run_javascript(
                        f"window._metplotCall('runExport', {json.dumps(opts)})",
                        timeout=timeout_sec,
                    )
                    exp_progress.set_value(0.85)
                    exp_status.set_text(f"Encoding {fmt.upper()} file...")
                    saved = await run_nc.io_bound(export_mgr.finish, sid)
                    exp_progress.set_value(1.0)
                    exp_status.set_text(f"Saved: {saved}")
                    ui.notify(f"Exported successfully to {saved}", type="positive")
                except Exception as exc:
                    export_mgr.abort(sid)
                    exp_status.set_text(f"Export failed: {exc}")
                    ui.notify(f"Export failed: {exc}", type="negative")
                finally:
                    export_go_btn.enable()

            with ui.row().classes("w-full justify-end gap-2 mt-3"):
                ui.button("Cancel", on_click=exp_dlg.close, color="#3f3f46")
                export_go_btn = ui.button("Save & Export", on_click=run_export_action, color="#ef4444")

        exp_dlg.open()

    # ---------------- Dynamic UI Builders (Layer Stack, Style Editor, Labels) ----------------
    def render_layer_stack():
        layer_stack_col.clear()
        with layer_stack_col:
            if not ps.layers:
                ui.label("No layers yet. Open a NetCDF/GRIB file to start.").style("font-size: 12px; color: #71717a;")
                return
            # Display top layer first (visual stacking order)
            for rev_i, layer in enumerate(reversed(ps.layers)):
                real_idx = len(ps.layers) - 1 - rev_i
                is_active = (layer["id"] == ps.active_id)
                border = "1px solid #ef4444" if is_active else "1px solid #27272a"
                bg = "#27272a" if is_active else "#1f1f23"

                with ui.card().style(
                    f"width: 100%; padding: 8px 10px; background: {bg}; border: {border}; cursor: pointer;"
                ):
                    with ui.row().classes("w-full items-center justify-between no-wrap"):
                        async def _select_layer(lid=layer["id"]):
                            ps.active_id = lid
                            render_layer_stack()
                            populate_style_editor()
                            await ui.run_javascript(f"window._metplotCall('setActiveLayer', {json.dumps(lid)})")

                        with ui.column().style("gap: 1px; flex: 1; min-width: 0;").on("click", _select_layer):
                            badge = "WIND" if layer["type"] == "wind" else ("CONTOUR" if layer["mode"] == 4 else "SCALAR")
                            title = layer.get("customName") or layer.get("varKey", "Layer")
                            unit_s = layer.get("displayUnit", "")
                            sub = f"{badge} • {int(round(layer['opacity'] * 100))}%"
                            if unit_s:
                                sub += f" • {unit_s}"
                            ui.label(title).style("font-size: 13px; font-weight: 600; color: #f4f4f5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;")
                            ui.label(sub).style("font-size: 10px; color: #94a3b8;")

                        with ui.row().style("gap: 2px; flex-wrap: nowrap;"):
                            async def _toggle_vis(l=layer):
                                l["visible"] = not l["visible"]
                                render_layer_stack()
                                await sync_layers_to_gl(fit_bounds=False)

                            async def _move(idx=real_idx, delta=1):
                                target = idx + delta
                                if 0 <= target < len(ps.layers):
                                    ps.layers[idx], ps.layers[target] = ps.layers[target], ps.layers[idx]
                                    render_layer_stack()
                                    await sync_layers_to_gl(fit_bounds=False)

                            async def _remove(lid=layer["id"]):
                                ps.layers = [x for x in ps.layers if x["id"] != lid]
                                if ps.active_id == lid:
                                    ps.active_id = ps.layers[-1]["id"] if ps.layers else None
                                render_layer_stack()
                                populate_style_editor()
                                await sync_layers_to_gl(fit_bounds=False)

                            ui.button(
                                icon="visibility" if layer["visible"] else "visibility_off",
                                on_click=_toggle_vis,
                            ).props("flat round dense size=sm color=grey-4")
                            ui.button(icon="arrow_upward", on_click=lambda idx=real_idx: _move(idx, 1)).props("flat round dense size=sm color=grey-4")
                            ui.button(icon="arrow_downward", on_click=lambda idx=real_idx: _move(idx, -1)).props("flat round dense size=sm color=grey-4")
                            ui.button(icon="delete", on_click=_remove).props("flat round dense size=sm color=red-4")

    def populate_style_editor():
        layer = _active_layer()
        ps.syncing_editor = True
        try:
            if not layer:
                style_header.set_text("No active layer selected")
                scalar_editor_col.set_visibility(False)
                wind_editor_col.set_visibility(False)
                return

            style_header.set_text(f"Editing: {layer.get('customName', layer['id'])}")
            if layer["type"] == "scalar":
                scalar_editor_col.set_visibility(True)
                wind_editor_col.set_visibility(False)

                sc_name_input.set_value(layer.get("customName", ""))
                sc_var_select.set_value(layer["varKey"])
                vinfo = _get_var_info(layer["varKey"])
                if vinfo and vinfo["levels"]:
                    sc_level_select.set_options({
                        i: f"{lv} {vinfo['level_units']}".strip() for i, lv in enumerate(vinfo["levels"])
                    })
                    sc_level_select.set_value(layer["levelIdx"])
                    sc_level_select.set_visibility(True)
                else:
                    sc_level_select.set_visibility(False)

                sc_mode_select.set_value(RENDER_MODE_NAMES.get(layer["mode"], "Smooth"))
                sc_opacity_slider.set_value(layer["opacity"])
                sc_opacity_lbl.set_text(f"{int(round(layer['opacity'] * 100))}%")
                sc_contour_slider.set_value(layer["contourLevels"])
                sc_contour_lbl.set_text(str(layer["contourLevels"]))
                sc_lw_input.set_value(layer["lineWidth"])
                sc_lc_select.set_value(layer["lineColorName"])

                sc_scale_input.set_value(layer["scale"])
                sc_offset_input.set_value(layer["offset"])
                sc_unit_input.set_value(layer["displayUnit"])

                sc_cmap_select.set_options(_all_cmap_names())
                sc_cmap_select.set_value(layer["cmapName"])
                sc_vmin_input.set_value(layer["vmin"])
                sc_vmax_input.set_value(layer["vmax"])
                sc_clip_switch.set_value(layer["clipOutOfRange"])
                sc_mask_switch.set_value(layer.get("maskBelow", False))
                sc_mask_thresh_input.set_value(layer.get("maskThreshold", 0.0))
                cpt_bounds_btn.set_enabled(layer["cmapName"] in custom_colormaps)
            else:
                scalar_editor_col.set_visibility(False)
                wind_editor_col.set_visibility(True)

                w_name_input.set_value(layer.get("customName", "Wind Vectors"))
                w_u_select.set_value(layer["uVarKey"])
                w_v_select.set_value(layer["vVarKey"])
                uinfo = _get_var_info(layer["uVarKey"])
                if uinfo and uinfo["levels"]:
                    w_level_select.set_options({
                        i: f"{lv} {uinfo['level_units']}".strip() for i, lv in enumerate(uinfo["levels"])
                    })
                    w_level_select.set_value(layer["levelIdx"])
                    w_level_select.set_visibility(True)
                else:
                    w_level_select.set_visibility(False)

                w_style_select.set_value(layer["vectorStyle"])
                w_color_select.set_value(layer["colorMode"])
                w_spacing_slider.set_value(layer["spacing"])
                w_spacing_lbl.set_text(f"{layer['spacing']} px")
                w_scale_slider.set_value(layer["vectorScale"])
                w_scale_lbl.set_text(f"{layer['vectorScale']:.1f}x")
                w_opacity_slider.set_value(layer["opacity"])
                w_opacity_lbl.set_text(f"{int(round(layer['opacity'] * 100))}%")
                w_unit_mult_input.set_value(layer["scale"])
                w_unit_label_input.set_value(layer["displayUnit"])
        finally:
            ps.syncing_editor = False

    def render_labels_list():
        labels_list_col.clear()
        with labels_list_col:
            if not ps.map_labels:
                ui.label("No custom labels placed yet.").style("font-size: 11px; color: #71717a;")
                return
            for lbl in ps.map_labels:
                with ui.row().classes("w-full items-center justify-between").style(
                    "background: #1f1f23; border: 1px solid #27272a; border-radius: 6px; padding: 4px 8px;"
                ):
                    ui.label(f"{lbl['text']} ({lbl['lat']:.2f}, {lbl['lon']:.2f})").style(
                        f"font-size: 12px; color: {lbl.get('color', '#ffffff')};"
                    )
                    async def _del_lbl(lid=lbl["id"]):
                        ps.map_labels = [x for x in ps.map_labels if x["id"] != lid]
                        await push_map_labels()
                    ui.button(icon="close", on_click=_del_lbl).props("flat round dense size=xs color=red-4")

    # ---------------- Page Layout ----------------
    with ui.row().style(
        "margin-top: 74px; width: 100vw; height: calc(100vh - 74px); "
        "flex-wrap: nowrap; gap: 0; overflow: hidden;"
    ):
        # Left Sidebar (360px)
        with ui.column().style(
            "width: 360px; min-width: 360px; height: 100%; overflow: hidden; "
            "background-color: #18181b; border-right: 1px solid #27272a; padding: 12px; gap: 8px;"
        ):
            # Top File Bar
            with ui.row().classes("w-full gap-1"):
                ui.button("Open File", on_click=lambda: pick_data_file(False), color="#ef4444").props("dense").classes("flex-1")
                ui.button("+ Merge File", on_click=lambda: pick_data_file(True), color="#27272a").props("dense").classes("flex-1")
                ui.button(icon="movie", on_click=open_export_dialog, color="#3f3f46").props("dense").tooltip("Export MP4 / GIF")

            with ui.row().classes("w-full gap-1 items-center"):
                file_path_input = ui.input(placeholder="Paste .nc / .grib path...").props("dense outlined").classes("flex-1")
                ui.button("Load", on_click=lambda: load_dataset_path(file_path_input.value, False), color="#27272a").props("dense")
            status_label = ui.label("No file loaded").style("font-size: 11px; color: #94a3b8;")

            # Sidebar Tabs
            with ui.tabs().classes("w-full").props("dense active-color=red-5 indicator-color=red-5") as sidebar_tabs:
                tab_layers = ui.tab("Layers")
                tab_style = ui.tab("Style")
                tab_labels = ui.tab("Map & Labels")

            with ui.tab_panels(sidebar_tabs, value=tab_layers).style(
                "flex: 1; width: 100%; overflow-y: auto; background: transparent;"
            ):
                # -------- TAB 1: MULTI-LAYER STACK --------
                with ui.tab_panel(tab_layers).style("padding: 8px 2px;"):
                    with ui.row().classes("w-full gap-1 mb-2"):
                        ui.button(
                            "+ Scalar / Contour",
                            on_click=lambda: add_scalar_layer_action(mode=4 if ps.layers else 0, opacity=0.9 if ps.layers else 0.78),
                            color="#27272a",
                        ).props("dense").classes("flex-1")
                        ui.button(
                            "+ Wind Vectors",
                            on_click=open_add_wind_dialog,
                            color="#27272a",
                        ).props("dense").classes("flex-1")

                    ui.label("Click a layer to edit its opacity, contours, units & colormap in the Style tab.").style(
                        "font-size: 11px; color: #71717a; margin-bottom: 6px;"
                    )
                    layer_stack_col = ui.column().classes("w-full gap-2")

                # -------- TAB 2: ACTIVE LAYER STYLE & UNITS --------
                with ui.tab_panel(tab_style).style("padding: 8px 2px;"):
                    style_header = ui.label("No active layer selected").style(
                        "font-size: 13px; font-weight: 700; color: #f87171; margin-bottom: 6px;"
                    )

                    # -- Scalar / Contour Editor --
                    with ui.column().classes("w-full gap-2") as scalar_editor_col:
                        async def _sc_name_change(e):
                            if ps.syncing_editor: return
                            l = _active_layer()
                            if l:
                                l["customName"] = e.value or ""
                                render_layer_stack()
                                await push_layer_style(l)

                        sc_name_input = ui.input(label="Layer Display Name", on_change=_sc_name_change).props("dense outlined").classes("w-full")

                        async def _sc_var_change(e):
                            if ps.syncing_editor or not e.value: return
                            l = _active_layer()
                            if l and l["type"] == "scalar":
                                vinfo = _get_var_info(e.value)
                                l["varKey"] = e.value
                                l["levelIdx"] = 0
                                l["numTimes"] = len(vinfo["times"]) if vinfo else 1
                                l["customName"] = vinfo["var_name"] if vinfo else e.value
                                l["displayUnit"] = vinfo["units"] if vinfo else ""
                                l["scale"] = 1.0
                                l["offset"] = 0.0
                                await _autoscale_layer_frame(l)
                                render_layer_stack()
                                populate_style_editor()
                                await sync_layers_to_gl(fit_bounds=False)

                        sc_var_select = ui.select(label="Variable", options={}, on_change=_sc_var_change).props("dense outlined").classes("w-full")

                        async def _sc_lvl_change(e):
                            if ps.syncing_editor or e.value is None: return
                            l = _active_layer()
                            if l:
                                l["levelIdx"] = int(e.value)
                                await _autoscale_layer_frame(l)
                                populate_style_editor()
                                await sync_layers_to_gl(fit_bounds=False)

                        sc_level_select = ui.select(label="Vertical Level", options={}, on_change=_sc_lvl_change).props("dense outlined").classes("w-full")
                        sc_level_select.set_visibility(False)

                        async def _sc_mode_change(e):
                            if ps.syncing_editor or not e.value: return
                            l = _active_layer()
                            if l:
                                l["mode"] = RENDER_MODES[e.value]
                                render_layer_stack()
                                await push_layer_style(l)

                        sc_mode_select = ui.select(
                            label="Render Mode", options=list(RENDER_MODES.keys()),
                            value="Smooth (WebGL)", on_change=_sc_mode_change,
                        ).props("dense outlined").classes("w-full")

                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label("Opacity").style("font-size: 12px; color: #cbd5e1;")
                            sc_opacity_lbl = ui.label("78%").style("font-size: 12px; color: #94a3b8;")

                        async def _sc_opacity_change(e):
                            if ps.syncing_editor: return
                            l = _active_layer()
                            if l:
                                l["opacity"] = float(e.value)
                                sc_opacity_lbl.set_text(f"{int(round(l['opacity'] * 100))}%")
                                render_layer_stack()
                                await push_layer_style(l)

                        sc_opacity_slider = ui.slider(min=0.05, max=1.0, step=0.01, value=0.78, on_change=_sc_opacity_change).classes("w-full")

                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label("Contour Levels").style("font-size: 12px; color: #cbd5e1;")
                            sc_contour_lbl = ui.label("14").style("font-size: 12px; color: #94a3b8;")

                        async def _sc_contour_change(e):
                            if ps.syncing_editor: return
                            l = _active_layer()
                            if l:
                                l["contourLevels"] = int(e.value)
                                sc_contour_lbl.set_text(str(l["contourLevels"]))
                                await push_layer_style(l)

                        sc_contour_slider = ui.slider(min=4, max=40, step=1, value=14, on_change=_sc_contour_change).classes("w-full")

                        with ui.row().classes("w-full gap-2"):
                            async def _sc_lw(e):
                                if ps.syncing_editor: return
                                l = _active_layer()
                                if l:
                                    l["lineWidth"] = float(e.value or 1.2)
                                    await push_layer_style(l)

                            async def _sc_lc(e):
                                if ps.syncing_editor: return
                                l = _active_layer()
                                if l:
                                    l["lineColorName"] = e.value
                                    await push_layer_style(l)

                            sc_lw_input = ui.number(label="Line Width", value=1.3, min=0.4, max=4.0, step=0.2, on_change=_sc_lw).props("dense outlined").classes("flex-1")
                            sc_lc_select = ui.select(label="Line Color", options=["Dark", "Light"], value="Dark", on_change=_sc_lc).props("dense outlined").classes("flex-1")

                        ui.separator()
                        ui.label("UNITS & VALUE TRANSFORM (val × scale + offset)").style("font-size: 10px; font-weight: 700; color: #94a3b8;")

                        async def _sc_preset_change(e):
                            if ps.syncing_editor or not e.value: return
                            l = _active_layer()
                            if l and e.value in UNIT_PRESETS:
                                sc, off, un = UNIT_PRESETS[e.value]
                                l["scale"] = sc
                                l["offset"] = off
                                if un:
                                    l["displayUnit"] = un
                                await _autoscale_layer_frame(l)
                                render_layer_stack()
                                populate_style_editor()
                                await push_layer_style(l)

                        ui.select(label="Unit Preset", options=list(UNIT_PRESETS.keys()), value="Custom / Raw", on_change=_sc_preset_change).props("dense outlined").classes("w-full")

                        with ui.row().classes("w-full gap-1"):
                            async def _sc_scale_off(e):
                                if ps.syncing_editor: return
                                l = _active_layer()
                                if l:
                                    l["scale"] = float(sc_scale_input.value if sc_scale_input.value is not None else 1.0)
                                    l["offset"] = float(sc_offset_input.value if sc_offset_input.value is not None else 0.0)
                                    l["displayUnit"] = sc_unit_input.value or ""
                                    render_layer_stack()
                                    await push_layer_style(l)

                            sc_scale_input = ui.number(label="Scale (×)", value=1.0, format="%.6g", on_change=_sc_scale_off).props("dense outlined").classes("flex-1")
                            sc_offset_input = ui.number(label="Offset (+)", value=0.0, format="%.6g", on_change=_sc_scale_off).props("dense outlined").classes("flex-1")
                            sc_unit_input = ui.input(label="Unit", value="", on_change=_sc_scale_off).props("dense outlined").style("width: 72px;")

                        ui.separator()
                        ui.label("COLORMAP & BOUNDARIES").style("font-size: 10px; font-weight: 700; color: #94a3b8;")

                        async def _sc_cmap_change(e):
                            if ps.syncing_editor or not e.value: return
                            l = _active_layer()
                            if l:
                                l["cmapName"] = e.value
                                cpt_bounds_btn.set_enabled(e.value in custom_colormaps)
                                await push_layer_style(l)

                        sc_cmap_select = ui.select(label="Colormap", options=_all_cmap_names(), value="Turbo", on_change=_sc_cmap_change).props("dense outlined").classes("w-full")
                        ui.button("Upload Custom .CPT", on_click=upload_cpt_native, color="#3f3f46").props("dense").classes("w-full")

                        with ui.row().classes("w-full gap-2"):
                            async def _sc_bounds(e):
                                if ps.syncing_editor: return
                                l = _active_layer()
                                if l and sc_vmin_input.value is not None and sc_vmax_input.value is not None:
                                    l["vmin"] = float(sc_vmin_input.value)
                                    l["vmax"] = float(sc_vmax_input.value)
                                    await push_layer_style(l)

                            sc_vmin_input = ui.number(label="Min (vmin)", value=0.0, format="%.5g", on_change=_sc_bounds).props("dense outlined").classes("flex-1")
                            sc_vmax_input = ui.number(label="Max (vmax)", value=1.0, format="%.5g", on_change=_sc_bounds).props("dense outlined").classes("flex-1")

                        with ui.row().classes("w-full gap-1"):
                            async def _btn_auto_frame():
                                l = _active_layer()
                                if l:
                                    await _autoscale_layer_frame(l)
                                    populate_style_editor()
                                    await push_layer_style(l)

                            async def _btn_auto_all():
                                l = _active_layer()
                                if l:
                                    await _autoscale_layer_all(l)
                                    populate_style_editor()
                                    await push_layer_style(l)

                            async def _btn_cpt_bounds():
                                l = _active_layer()
                                if l and l["cmapName"] in custom_colormaps:
                                    c = custom_colormaps[l["cmapName"]]
                                    l["vmin"] = round(c["vmin"], 4)
                                    l["vmax"] = round(c["vmax"], 4)
                                    populate_style_editor()
                                    await push_layer_style(l)

                            ui.button("Auto Frame", on_click=_btn_auto_frame, color="#27272a").props("dense").classes("flex-1")
                            ui.button("Auto All", on_click=_btn_auto_all, color="#27272a").props("dense").classes("flex-1")
                            cpt_bounds_btn = ui.button("CPT Bounds", on_click=_btn_cpt_bounds, color="#27272a").props("dense").classes("flex-1")
                            cpt_bounds_btn.disable()

                        async def _sc_clip(e):
                            if ps.syncing_editor: return
                            l = _active_layer()
                            if l:
                                l["clipOutOfRange"] = bool(e.value)
                                await push_layer_style(l)

                        async def _sc_mask_change(e=None):
                            if ps.syncing_editor: return
                            l = _active_layer()
                            if l:
                                l["maskBelow"] = bool(sc_mask_switch.value)
                                l["maskThreshold"] = float(sc_mask_thresh_input.value if sc_mask_thresh_input.value is not None else 0.0)
                                await push_layer_style(l)

                        with ui.row().classes("w-full items-center gap-2"):
                            sc_mask_switch = ui.switch("Hide ≤ threshold (transparent 0)", value=False, on_change=_sc_mask_change).props("dense").classes("flex-1")
                            sc_mask_thresh_input = ui.number(label="≤ Val", value=0.0, format="%.4g", on_change=_sc_mask_change).props("dense outlined").style("width: 82px;")

                        sc_clip_switch = ui.switch("Hide out-of-range (< Min / > Max)", value=False, on_change=_sc_clip).props("dense")

                    # -- Wind Vector Editor --
                    with ui.column().classes("w-full gap-2") as wind_editor_col:
                        async def _w_name_change(e):
                            if ps.syncing_editor: return
                            l = _active_layer()
                            if l and l["type"] == "wind":
                                l["customName"] = e.value or "Wind"
                                render_layer_stack()
                                await push_layer_style(l)

                        w_name_input = ui.input(label="Layer Name", on_change=_w_name_change).props("dense outlined").classes("w-full")

                        async def _w_uv_change(e):
                            if ps.syncing_editor: return
                            l = _active_layer()
                            if l and l["type"] == "wind":
                                l["uVarKey"] = w_u_select.value
                                l["vVarKey"] = w_v_select.value
                                uinfo = _get_var_info(l["uVarKey"])
                                l["numTimes"] = len(uinfo["times"]) if uinfo else 1
                                await sync_layers_to_gl(fit_bounds=False)

                        w_u_select = ui.select(label="U-Component", options={}, on_change=_w_uv_change).props("dense outlined").classes("w-full")
                        w_v_select = ui.select(label="V-Component", options={}, on_change=_w_uv_change).props("dense outlined").classes("w-full")

                        async def _w_lvl_change(e):
                            if ps.syncing_editor or e.value is None: return
                            l = _active_layer()
                            if l and l["type"] == "wind":
                                l["levelIdx"] = int(e.value)
                                await sync_layers_to_gl(fit_bounds=False)

                        w_level_select = ui.select(label="Vertical Level", options={}, on_change=_w_lvl_change).props("dense outlined").classes("w-full")
                        w_level_select.set_visibility(False)

                        async def _w_style_update(e):
                            if ps.syncing_editor: return
                            l = _active_layer()
                            if l and l["type"] == "wind":
                                l["vectorStyle"] = w_style_select.value
                                l["colorMode"] = w_color_select.value
                                l["spacing"] = int(w_spacing_slider.value)
                                l["vectorScale"] = float(w_scale_slider.value)
                                l["opacity"] = float(w_opacity_slider.value)
                                w_spacing_lbl.set_text(f"{l['spacing']} px")
                                w_scale_lbl.set_text(f"{l['vectorScale']:.1f}x")
                                w_opacity_lbl.set_text(f"{int(round(l['opacity'] * 100))}%")
                                render_layer_stack()
                                await push_layer_style(l)

                        w_style_select = ui.select(label="Vector Style", options={"arrows": "Arrows", "barbs": "Wind Barbs (kt)"}, value="arrows", on_change=_w_style_update).props("dense outlined").classes("w-full")
                        w_color_select = ui.select(
                            label="Vector Color",
                            options={"white": "White", "black": "Black", "cyan": "Cyan", "yellow": "Yellow", "speed": "Color by Speed"},
                            value="white", on_change=_w_style_update,
                        ).props("dense outlined").classes("w-full")

                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label("Spacing (Density)").style("font-size: 12px; color: #cbd5e1;")
                            w_spacing_lbl = ui.label("36 px").style("font-size: 12px; color: #94a3b8;")
                        w_spacing_slider = ui.slider(min=18, max=80, step=2, value=36, on_change=_w_style_update).classes("w-full")

                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label("Arrow / Barb Size").style("font-size: 12px; color: #cbd5e1;")
                            w_scale_lbl = ui.label("1.0x").style("font-size: 12px; color: #94a3b8;")
                        w_scale_slider = ui.slider(min=0.4, max=2.5, step=0.1, value=1.0, on_change=_w_style_update).classes("w-full")

                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label("Opacity").style("font-size: 12px; color: #cbd5e1;")
                            w_opacity_lbl = ui.label("90%").style("font-size: 12px; color: #94a3b8;")
                        w_opacity_slider = ui.slider(min=0.1, max=1.0, step=0.05, value=0.9, on_change=_w_style_update).classes("w-full")

                        ui.separator()
                        async def _w_unit_preset(e):
                            if ps.syncing_editor or not e.value: return
                            l = _active_layer()
                            if l and l["type"] == "wind" and e.value in WIND_UNIT_PRESETS:
                                sc, un = WIND_UNIT_PRESETS[e.value]
                                l["scale"] = sc
                                l["displayUnit"] = un
                                populate_style_editor()
                                render_layer_stack()
                                await push_layer_style(l)

                        ui.select(label="Wind Unit Preset", options=list(WIND_UNIT_PRESETS.keys()), value="m/s (×1)", on_change=_w_unit_preset).props("dense outlined").classes("w-full")
                        with ui.row().classes("w-full gap-2"):
                            async def _w_unit_manual(e):
                                if ps.syncing_editor: return
                                l = _active_layer()
                                if l and l["type"] == "wind":
                                    l["scale"] = float(w_unit_mult_input.value or 1.0)
                                    l["displayUnit"] = w_unit_label_input.value or "m/s"
                                    render_layer_stack()
                                    await push_layer_style(l)

                            w_unit_mult_input = ui.number(label="Scale (×)", value=1.0, format="%.5g", on_change=_w_unit_manual).props("dense outlined").classes("flex-1")
                            w_unit_label_input = ui.input(label="Unit", value="m/s", on_change=_w_unit_manual).props("dense outlined").classes("flex-1")

                    scalar_editor_col.set_visibility(False)
                    wind_editor_col.set_visibility(False)

                # -------- TAB 3: MAP BASEMAP, TITLE & CUSTOM LABELS --------
                with ui.tab_panel(tab_labels).style("padding: 8px 2px;"):
                    ui.label("OSM BASEMAP (NO AUTH / NO CARTODB)").style("font-size: 10px; font-weight: 700; color: #94a3b8;")

                    async def _on_basemap_change(e):
                        ps.basemap = BASEMAP_OPTIONS[e.value]
                        await ui.run_javascript(f"window._metplotCall('setBasemap', {json.dumps(ps.basemap)})")

                    ui.select(
                        options=list(BASEMAP_OPTIONS.keys()), value="OpenStreetMap",
                        on_change=_on_basemap_change,
                    ).props("dense outlined").classes("w-full mb-2")

                    with ui.row().classes("w-full gap-2 mb-2"):
                        ui.button("Fit Data", on_click=lambda: ui.run_javascript("window._metplotCall('fitDataBounds')"), color="#27272a").props("dense").classes("flex-1")
                        ui.button("Clear Box", on_click=lambda: ui.run_javascript("window._metplotCall('clearRegionBox')"), color="#27272a").props("dense").classes("flex-1")

                    ui.separator()
                    ui.label("WEBGL UPSCALING & QUALITY").style("font-size: 10px; font-weight: 700; color: #94a3b8; margin-top: 6px;")

                    async def _on_quality_change(e=None):
                        cfg = {
                            "renderScale": float(gl_scale_sel.value),
                            "interpMode": int(gl_interp_sel.value),
                        }
                        await ui.run_javascript(f"window._metplotCall('setRenderQuality', {json.dumps(cfg)})")

                    with ui.row().classes("w-full gap-2 mb-2"):
                        gl_scale_sel = ui.select(
                            label="Supersampling",
                            options={1.0: "1x (Fast)", 1.5: "1.5x (Sharp)", 2.0: "2x (Ultra HD)", 3.0: "3x (4K SSAA)"},
                            value=2.0,
                            on_change=_on_quality_change,
                        ).props("dense outlined").classes("flex-1")
                        gl_interp_sel = ui.select(
                            label="Interpolation",
                            options={1: "Bicubic (HD)", 0: "Bilinear"},
                            value=1,
                            on_change=_on_quality_change,
                        ).props("dense outlined").classes("flex-1")

                    ui.separator()
                    ui.label("MAP TITLE & HUD OVERLAY").style("font-size: 10px; font-weight: 700; color: #94a3b8; margin-top: 6px;")

                    async def _on_hud_change(e=None):
                        ps.hud_title = hud_title_in.value or ""
                        ps.hud_subtitle = hud_sub_in.value or ""
                        ps.show_title = bool(show_title_sw.value)
                        ps.show_colorbar = bool(show_cb_sw.value)
                        await push_hud_config()

                    hud_title_in = ui.input(label="Custom Title (blank = auto)", on_change=_on_hud_change).props("dense outlined").classes("w-full")
                    hud_sub_in = ui.input(label="Custom Subtitle / Note", on_change=_on_hud_change).props("dense outlined").classes("w-full")
                    with ui.row().classes("w-full justify-between"):
                        show_title_sw = ui.switch("Show Title", value=True, on_change=_on_hud_change).props("dense")
                        show_cb_sw = ui.switch("Show Colorbar", value=True, on_change=_on_hud_change).props("dense")

                    ui.separator()
                    ui.label("CUSTOM MAP PINS & LABELS").style("font-size: 10px; font-weight: 700; color: #94a3b8; margin-top: 6px;")

                    with ui.row().classes("w-full gap-2"):
                        lbl_text_in = ui.input(label="Label Text", value="City / Storm").props("dense outlined").classes("flex-1")
                        lbl_color_sel = ui.select(label="Color", options=list(LABEL_COLORS.keys()), value="White").props("dense outlined").style("width: 100px;")

                    async def _toggle_place_mode():
                        ps.place_label_mode = not ps.place_label_mode
                        place_lbl_btn.props("color=red" if ps.place_label_mode else "color=grey-9")
                        place_lbl_btn.set_text("Stop Placing Labels" if ps.place_label_mode else "Click Map to Place Label")
                        col_hex = LABEL_COLORS.get(lbl_color_sel.value, "#ffffff")
                        await ui.run_javascript(
                            f"window._metplotCall('setLabelPlacementMode', {json.dumps(ps.place_label_mode)}, "
                            f"{json.dumps(lbl_text_in.value or 'Label')}, {json.dumps(col_hex)})"
                        )

                    place_lbl_btn = ui.button("Click Map to Place Label", on_click=_toggle_place_mode, color="#27272a").props("dense").classes("w-full mt-1")

                    with ui.row().classes("w-full gap-1 mt-2 items-center"):
                        pin_lat_in = ui.number(label="Lat", value=25.0, format="%.3f").props("dense outlined").classes("flex-1")
                        pin_lon_in = ui.number(label="Lon", value=55.0, format="%.3f").props("dense outlined").classes("flex-1")

                        async def _add_manual_pin():
                            ps.map_labels.append({
                                "id": f"pin_{len(ps.map_labels)}_{int(pin_lat_in.value or 0)}",
                                "lat": float(pin_lat_in.value or 0.0),
                                "lon": float(pin_lon_in.value or 0.0),
                                "text": lbl_text_in.value or "Label",
                                "color": LABEL_COLORS.get(lbl_color_sel.value, "#ffffff"),
                                "fontSize": 13,
                            })
                            await push_map_labels()

                        ui.button("Add", on_click=_add_manual_pin, color="#ef4444").props("dense")

                    with ui.row().classes("w-full justify-between items-center mt-2"):
                        ui.label("Placed Labels").style("font-size: 11px; color: #94a3b8;")
                        async def _clear_labels():
                            ps.map_labels = []
                            await push_map_labels()
                        ui.button("Clear All", on_click=_clear_labels).props("flat dense size=xs color=red-4")

                    labels_list_col = ui.column().classes("w-full gap-1 mt-1")
                    render_labels_list()

        # Right Map + Bottom 60 FPS Animation Bar
        with ui.column().style("flex: 1; height: 100%; gap: 0; overflow: hidden;"):
            ui.html(
                '<iframe id="plot-frame" src="/plot_canvas" '
                'style="width:100%; height:100%; border:none; display:block;"></iframe>',
                
            ).style("flex: 1; width: 100%; min-height: 0;")

            with ui.row().style(
                "width: 100%; height: 58px; background-color: #18181b; "
                "border-top: 1px solid #27272a; padding: 0 16px; "
                "align-items: center; gap: 12px; flex-wrap: nowrap;"
            ):
                play_btn = ui.button(icon="play_arrow", on_click=toggle_play, color="#ef4444").props("round dense")
                ui.button(icon="skip_previous", on_click=lambda: step_frame(-1), color="#27272a").props("round dense")
                ui.button(icon="skip_next", on_click=lambda: step_frame(1), color="#27272a").props("round dense")

                async def _pause_for_scrub():
                    if ps.playing:
                        ps.playing = False
                        play_btn.props("icon=play_arrow")
                        await push_playback()

                async def _on_slider_change(e):
                    if ps.syncing_slider or ps.playing:
                        return
                    new_t = float(e.value or 0.0)
                    if abs(new_t - ps.time_float) > 1e-4:
                        ps.time_float = new_t
                        await render_current_time()

                time_slider = ui.slider(min=0, max=0, step=0.02, value=0, on_change=_on_slider_change).classes("flex-1")
                time_slider.on("mousedown", _pause_for_scrub)
                time_slider.on("touchstart", _pause_for_scrub)
                time_readout = ui.label("--").style(
                    "font-size: 12px; color: #e2e8f0; min-width: 195px; text-align: right; font-variant-numeric: tabular-nums;"
                )

                async def _on_smooth_toggle(e):
                    ps.smooth_interp = bool(e.value)
                    time_slider._props["step"] = 0.02 if ps.smooth_interp else 1
                    time_slider.update()
                    await push_playback()
                    if not ps.playing:
                        await render_current_time()

                ui.switch("Smooth 60fps", value=True, on_change=_on_smooth_toggle).props("dense")

                async def _on_speed_change(e):
                    ps.steps_per_sec = float(e.value)
                    await push_playback()

                ui.select(
                    options={0.5: "0.5x", 1.0: "1x", 2.0: "2x", 4.0: "4x", 8.0: "8x", 12.0: "12x"},
                    value=2.0,
                    label="Speed",
                    on_change=_on_speed_change,
                ).props("dense outlined").style("width: 86px;")

    render_layer_stack()

    async def _startup_autoload():
        await asyncio.sleep(0.35)
        if plot_app_state.pending_file:
            target = plot_app_state.pending_file
            plot_app_state.pending_file = None
            await load_dataset_path(target, append=False)
        elif dataset_mgr.file_path:
            ps.meta = dataset_mgr.get_metadata()
            file_path_input.set_value(ps.meta["file_path"])
            status_label.set_text(f"Loaded: {ps.meta['file_name']} ({len(ps.meta['variables'])} vars)")
            var_opts = {v["key"]: v["label"] for v in ps.meta["variables"]}
            sc_var_select.set_options(var_opts)
            w_u_select.set_options(var_opts)
            w_v_select.set_options(var_opts)
            await add_scalar_layer_action(ps.meta["variables"][0]["key"], mode=0, opacity=0.78, fit=True)

    ui.timer(0.1, _startup_autoload, once=True)


# ---------------- Existing Pages ----------------
async def save_plot(fig):
    file = await file_select_save()
    if file:
        fig.savefig(file, dpi=200)


@ui.page("/colormaptest")
def color_map_test():
    global_navbar()
    with ui.row().style("gap: 10px; margin-top: 80px; padding: 10px;"):
        initialize_coords()
    ui.add_body_html(CoordsHTML)

    CMAP = SimpleNamespace(text=None)

    async def type_selector(value):
        if value.value == "By CPT File":
            file = await file_select_open()
            if file:
                CMAP.text = file[0]
        else:
            with (ui.dialog() as dialog, ui.card().style("padding: 20px;")):
                cmap_entry = ui.input(label="Enter CMAP")
                ui.button("Submit", on_click=lambda e: (setattr(CMAP, "text", cmap_entry.value), dialog.close()))
            dialog.open()

    with ui.column().style("gap: 10px; margin-top: 40px; padding: 10px;"):
        ui.select(["By CPT File", "By Name"], on_change=lambda value: type_selector(value))
        ui.label("Current CMAP : None").bind_text_from(CMAP)
        with ui.row().style("margin-top:40px"):
            matplotlib_plot = ui.matplotlib(figsize=(8, 8))
            with matplotlib_plot.figure as fig:
                pass

            def plot_action():
                fig.clear()
                fig.set_constrained_layout(True)
                if all(
                    [
                        top := int(float(state.inputs["top"].value or 0)),
                        bottom := int(float(state.inputs["bottom"].value or 0)),
                        left := int(float(state.inputs["left"].value or 0)),
                        right := int(float(state.inputs["right"].value or 0)),
                    ]
                ):
                    subregion = [top, right, left, bottom]
                    PlotData(str(CMAP.text), *subregion, fig=fig)
                else:
                    PlotData(str(CMAP.text), fig=fig)
                fig.canvas.draw()
                matplotlib_plot.update()
                save_butt.enable()

            with ui.column():
                ui.button("Plot", on_click=plot_action)
                save_butt = ui.button("Save", on_click=lambda: save_plot(fig))
                save_butt.disable()


async def set_panoply_path():
    file = await file_select_open()
    if file:
        subprocess.run(["setx", "PANOPLY_PATH", file[0]], shell=True)
        ui.notify("Set Panoply Path")


@ui.page("/settings")
def settings_page():
    global_navbar()
    ui.button(text="Set Panoply Path", on_click=set_panoply_path).style("margin-top:100px;")
    with ui.row().style("margin-top: 15px; padding: 20px;"):
        if os.getenv("PANOPLY_PATH"):
            ui.label(f"Panoply Path is set : {os.getenv('PANOPLY_PATH')}")
        else:
            ui.label("Panoply Path is not set yet.")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(native=True, window_size=(1600, 900), favicon="⛈️", title="MetPlot", reload=False)
