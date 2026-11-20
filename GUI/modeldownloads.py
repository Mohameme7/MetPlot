import os
import subprocess
import threading
from multiprocessing import Manager
from pathlib import Path

import webview
from nicegui import ElementFilter, app, run as run_nc, ui

from EventBus_Observers import EventBus, Observable
from MetPlot.Downloader.FileHandler import GribCreation
from MetPlot.Downloader.MemoryDownload import Downloader
from MetPlot.Downloader.Parsers.ModelAbstract import Selection, WeatherModel
from MetPlot.Interpolation import GribInterpolator

Bus = EventBus()


def _run_interpolation(src_grib: str, dst_nc: str, freq: str, grouped: bool) -> str:
    with GribInterpolator(src_grib, freq=freq) as gi:
        try:
            gi.to_netcdf(dst_nc, grouped=grouped)
        except Exception:
            if not grouped:
                # Fallback to grouped NetCDF if level coordinates clash during flat merge
                gi.to_netcdf(dst_nc, grouped=True)
            else:
                raise
    return os.path.abspath(dst_nc)


def interpolation_finished_dialog(dialog, nc_file: str, on_open_in_plotter=None):
    abs_nc = os.path.abspath(nc_file)

    def open_nc():
        dialog.close()
        if on_open_in_plotter:
            on_open_in_plotter(abs_nc)

    with dialog, ui.card().style("padding: 24px; min-width: 420px;"):
        ui.label("Interpolation Complete").style("font-size: 18px; font-weight: 700; color: #4ade80;")
        ui.label(f"Saved NetCDF to: {abs_nc}").style(
            "font-size: 12px; color: #94a3b8; word-break: break-all;"
        )
        ui.label("Would you like to open the interpolated file in the Plotting page now?").style(
            "margin-top: 8px;"
        )
        with ui.row().style("gap: 10px; margin-top: 14px; flex-wrap: wrap;"):
            if on_open_in_plotter:
                ui.button("Open in Plotter", on_click=open_nc, color="#ef4444")
            if os.getenv("PANOPLY_PATH"):
                ui.button(
                    "Open With Panoply",
                    on_click=lambda: (
                        dialog.close(),
                        subprocess.run(f'"{os.getenv("PANOPLY_PATH")}" "{abs_nc}"', shell=True),
                    ),
                )
            ui.button("Close", on_click=dialog.close, color="#3f3f46")


def finished_dialog(dialog, file: str, on_open_in_plotter=None):
    abs_file = os.path.abspath(file)

    def open_raw():
        dialog.close()
        if on_open_in_plotter:
            on_open_in_plotter(abs_file)

    with dialog, ui.card().style("padding: 24px; min-width: 440px;"):
        ui.label("Download Complete").style("font-size: 18px; font-weight: 700;")
        ui.label(f"Saved to: {abs_file}").style(
            "font-size: 12px; color: #94a3b8; word-break: break-all;"
        )
        ui.label("What would you like to do next?").style("margin-top: 8px;")

        with ui.row().style("gap: 10px; margin-top: 10px; flex-wrap: wrap;"):
            if on_open_in_plotter:
                ui.button("Open in Plotter", on_click=open_raw, color="#ef4444")
            if os.getenv("PANOPLY_PATH"):
                ui.button(
                    "Open With Panoply",
                    on_click=lambda: (
                        dialog.close(),
                        subprocess.run(f'"{os.getenv("PANOPLY_PATH")}" "{abs_file}"', shell=True),
                    ),
                )
            ui.button("Close", on_click=dialog.close, color="#3f3f46")

        ui.separator().style("margin: 14px 0 8px 0;")
        ui.label("Interpolate Time Steps → NetCDF").style(
            "font-size: 13px; font-weight: 700; color: #e2e8f0;"
        )
        with ui.row().classes("w-full items-center gap-3 mt-1"):
            freq_select = ui.select(
                label="Target Step",
                options={
                    "1h": "Hourly (1h)",
                    "30min": "30 min",
                    "3h": "3-Hourly (3h)",
                    "15min": "15 min",
                },
                value="1h",
            ).props("dense outlined").style("width: 155px;")
            grouped_cb = ui.checkbox("Grouped NetCDF", value=False).tooltip(
                "Store each vertical level type in its own NetCDF group (auto-used on coord clash)."
            )

        interp_status = ui.label("").style("font-size: 12px; color: #cbd5e1; margin-top: 4px;")
        interp_spinner = ui.spinner("dots", size="md", color="red")
        interp_spinner.set_visibility(False)

        async def start_interpolation():
            default_nc = f"{Path(abs_file).stem}_interpolated.nc"
            out_nc = await app.native.main_window.create_file_dialog(
                dialog_type=webview.SAVE_DIALOG,
                save_filename=default_nc,
                file_types=("NetCDF File (*.nc)", "All files (*.*)"),
            )
            if isinstance(out_nc, (tuple, list)):
                out_nc = out_nc[0] if out_nc else None
            if not out_nc:
                return
            if not out_nc.lower().endswith(".nc"):
                out_nc += ".nc"

            interp_btn.disable()
            interp_spinner.set_visibility(True)
            interp_status.set_text(f"Interpolating ({freq_select.value}) to {Path(out_nc).name} ...")
            try:
                saved_nc = await run_nc.io_bound(
                    _run_interpolation,
                    abs_file,
                    out_nc,
                    freq_select.value,
                    bool(grouped_cb.value),
                )
                dialog.clear()
                interpolation_finished_dialog(dialog, saved_nc, on_open_in_plotter=on_open_in_plotter)
            except Exception as exc:
                interp_spinner.set_visibility(False)
                interp_status.set_text(f"Interpolation failed: {exc}")
                ui.notify(f"Interpolation failed: {exc}", type="negative")
                interp_btn.enable()

        interp_btn = ui.button(
            "Interpolate to NetCDF",
            icon="auto_fix_high",
            on_click=start_interpolation,
            color="#2563eb",
        ).style("margin-top: 8px;")


def counter(prgrbar, sum_count):
    queue = Manager().Queue()
    count = 0
    count_lock = threading.Lock()
    denom = max(1, sum_count)

    def count_handler(q, full_count):
        nonlocal count
        while True:
            q.get()
            with count_lock:
                count += 1
                prgrbar.set_value(min(1.0, count / full_count))

    return queue, threading.Thread(target=count_handler, args=(queue, denom), daemon=True).start


def get_selections(from_hour, to_hour, hours):
    selected_hours = [h for h in hours if int(from_hour.value) <= int(h) <= int(to_hour.value)]
    selected_vars = [cb.text for cb in ElementFilter(kind=ui.checkbox, marker="Variable") if cb.value]
    selected_levels = [cb._markers[1] for cb in ElementFilter(kind=ui.checkbox, marker="Level") if cb.value]
    return selected_hours, selected_vars, selected_levels


def download(model: WeatherModel, sel: Selection, filename: str):
    urls = model.build_urls(sel)
    if sel.size_var is not None:
        sel.size_var.value = model.estimate_size(urls, sel)
    chunks = Downloader(urls, sel.queue).submit_downloads()
    chunks = model.postprocess(chunks)
    GribCreation(chunks, filename)
    model.finalize(filename, sel)


def load(
    model: WeatherModel,
    download_button: ui.button,
    top_entry,
    bottom_entry,
    left_entry,
    right_entry,
    generated_elements,
    on_open_in_plotter=None,
):
    Bus.clear_subscribers()
    for e in [top_entry, bottom_entry, left_entry, right_entry]:
        e.enable()

    async def Download(run_date, run):
        file = await app.native.main_window.create_file_dialog(dialog_type=webview.SAVE_DIALOG)
        if isinstance(file, (tuple, list)):
            file = file[0] if file else None
        if not file:
            return

        hours = list(model.forecast_hours(run_date, run))

        async def confirm_selection():
            if int(to_hour.value) <= int(from_hour.value):
                ui.notify('Invalid range! "To" hour must be greater than "From" hour.', type="negative")
                return

            selected_hours, selected_vars, selected_levels = get_selections(from_hour, to_hour, hours)

            subregion = None
            if all([top_entry.value, left_entry.value, right_entry.value, bottom_entry.value]):
                subregion = [
                    int(float(top_entry.value)),
                    int(float(bottom_entry.value)),
                    int(float(left_entry.value)),
                    int(float(right_entry.value)),
                ]

            sel = Selection(
                hours=selected_hours,
                variables=selected_vars,
                levels=selected_levels,
                run=run,
                subregion=subregion,
                size_var=size_var,
                run_date=run_date,
            )

            prgrbar = ui.linear_progress(value=0)
            queue, counter_thread = counter(prgrbar, model.expected_count(sel))
            counter_thread()
            sel.queue = queue

            await run_nc.io_bound(download, model, sel, file)
            dialog.clear()
            finished_dialog(dialog, file, on_open_in_plotter=on_open_in_plotter)

        with (ui.dialog() as dialog, ui.card().style("padding: 20px;")):
            ui.label("Select Forecast Hours Range").style("font-size: 16px; font-weight: bold;")
            from_hour = ui.select(label="From Hour", options=hours)
            to_hour = ui.select(label="To Hour", options=hours)
            ui.button("Submit", on_click=confirm_selection).style("margin-top: 10px;")
            size_label = ui.label("Estimated Size: ?")
            size_var = Observable(name="Size", inital_value=0, bus=Bus)
            Bus.subscribe(
                "Size_changed",
                lambda: size_label.set_text(f"Estimated Size: {size_var.value / 1_000_000:.2f} MB"),
            )
        dialog.open()

    with ui.row():
        model_data = model.run_options()
        run_dates = ui.select(options=list(model_data.keys()))
        runs = ui.select(options=[""])
        run_dates.on_value_change(lambda: runs.set_options(model_data.get(run_dates.value, [])))
        generated_elements.extend([run_dates, runs])
        download_button._event_listeners.clear()
        download_button.on_click(lambda: Download(run_dates.value, runs.value))
