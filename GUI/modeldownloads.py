import subprocess, threading, os, webview
from MetPlot.Downloader.Parsers.ModelAbstract import Selection, WeatherModel
from nicegui import ui, ElementFilter, app, run as run_nc
from MetPlot.Downloader.FileHandler import GribCreation
from MetPlot.Downloader.MemoryDownload import Downloader
from multiprocessing import Manager
from EventBus_Observers import EventBus, Observable


Bus = EventBus()
def finished_dialog(dialog, file):
    with dialog, ui.card().style('padding: 20px;'):
        ui.label("Download has finished.")
        if not os.getenv("PANOPLY_PATH"):

            ui.button("Exit", on_click=dialog.close)
        else:
            ui.label("Panoply Detected, Would you like to open it?")

            grib_file = os.path.abspath(file)
            print(os.getenv("PANOPLY_PATH"))

            ui.button("Open With Panoply", on_click=lambda: (
                dialog.close(), subprocess.run(f'"{os.getenv("PANOPLY_PATH")}" "{grib_file}"', shell=True)))
            ui.button("Exit", on_click=dialog.close)

def counter(prgrbar, sum_count):
    queue = Manager().Queue()
    count = 0
    count_lock = threading.Lock()

    def count_handler(q, full_count):
        nonlocal count
        while True:
            q.get()
            with count_lock:
                count += 1
                prgrbar.set_value(count / full_count)

    return queue , threading.Thread(target=count_handler, args=(queue, sum_count), daemon=True).start

def get_selections(from_hour, to_hour, hours):
    selected_hours = [h for h in hours if int(from_hour.value) <= int(h) <= int(to_hour.value)]
    selected_vars = [cb.text for cb in ElementFilter(kind=ui.checkbox, marker='Variable') if cb.value]
    selected_levels = [cb._markers[1] for cb in ElementFilter(kind=ui.checkbox, marker='Level') if cb.value]
    return selected_hours, selected_vars, selected_levels



def download(model: WeatherModel, sel: Selection, filename: str):
    urls = model.build_urls(sel)
    if sel.size_var is not None:
        sel.size_var.value = model.estimate_size(urls, sel)
    chunks = Downloader(urls, sel.queue).submit_downloads()
    chunks = model.postprocess(chunks)
    GribCreation(chunks, filename)
    model.finalize(filename, sel)


def load(model: WeatherModel, download_button : ui.button, top_entry, bottom_entry,
         left_entry, right_entry, generated_elements):
    Bus.clear_subscribers()
    for e in [top_entry, bottom_entry, left_entry, right_entry]:
        e.enable()


    async def Download(run_date, run):
        file = await app.native.main_window.create_file_dialog(
            dialog_type=webview.SAVE_DIALOG)
        if isinstance(file, tuple):
            file = file[0]

        hours = list(model.forecast_hours(run_date,run))

        async def confirm_selection():
            if int(to_hour.value) <= int(from_hour.value):
                ui.notify('Invalid range! "To" hour must be greater than "From" hour.',
                          type='negative')
                return

            selected_hours, selected_vars, selected_levels = get_selections(
                from_hour, to_hour, hours)

            subregion = None
            if all([top_entry.value, left_entry.value, right_entry.value, bottom_entry.value]):
                subregion = [int(float(top_entry.value)), int(float(bottom_entry.value)),
                             int(float(left_entry.value)), int(float(right_entry.value))]

            sel = Selection(hours=selected_hours, variables=selected_vars,
                            levels=selected_levels, run=run, subregion=subregion,
                            size_var=size_var, run_date=run_date)

            prgrbar = ui.linear_progress(value=0)
            queue, counter_thread = counter(prgrbar, model.expected_count(sel))
            counter_thread()
            sel.queue = queue

            await run_nc.io_bound(download, model, sel, file)
            dialog.clear()
            finished_dialog(dialog, file)

        with (ui.dialog() as dialog, ui.card().style('padding: 20px;')):
            ui.label('Select Forecast Hours Range').style('font-size: 16px; font-weight: bold;')
            from_hour = ui.select(label='From Hour', options=hours)
            to_hour = ui.select(label='To Hour', options=hours)
            ui.button('Submit', on_click=confirm_selection).style('margin-top: 10px;')
            size_label = ui.label("Estimated Size: ?")
            size_var = Observable(name="Size", inital_value=0, bus=Bus)
            Bus.subscribe("Size_changed",
                          lambda: size_label.set_text(f"Estimated Size: {size_var.value / 1000000} MB"))
        dialog.open()

    with ui.row():
        model_data = model.run_options()
        run_dates = ui.select(options=list(model_data.keys()))
        runs = ui.select(options=[''])
        run_dates.on_value_change(lambda: runs.set_options(model_data.get(run_dates.value)))
        generated_elements.extend([run_dates,runs])
        download_button._event_listeners.clear()
        download_button.on_click(lambda: Download(run_dates.value,runs.value))
