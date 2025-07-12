import os
import subprocess
import threading

import webview
from nicegui import ui, ElementFilter, app, run, observables


from MetPlot.Downloader.FileHandler import GribCreation
from MetPlot.Downloader.MemoryDownload import Downloader
from MetPlot.Downloader.Parsers.NomadsUtils import NomadsParse
from MetPlot.Downloader.Parsers.GEM import GEM
from itertools import product
from multiprocessing import Manager
import threading


def GFS_download(**kwargs):
    hours = kwargs.get('hours')
    run_date = kwargs.get('run_date')
    run_time = kwargs.get('run_time')
    variables = kwargs.get('variables')
    levels = kwargs.get('levels')
    filename = kwargs.get('filename')
    subregion = kwargs.get('subregion')
    queue = kwargs.get('queue')


    urls = []
    for hour in hours:
        urls.append(NomadsParse.create_url(hour, run_date, run_time, variables, levels, subregion))


    download_object = Downloader(urls, queue=queue if queue else None)

    downloaded_data = download_object.submitdownloads()
    GribCreation(downloaded_data, filename).merge_grib_files()




def GFS_Load(download_button, top_entry, bottom_entry, left_entry, right_entry, generated_elements, content):
    nomads = NomadsParse(content)

    async def Download(run_date, run_time):
        file = await app.native.main_window.create_file_dialog(dialog_type=webview.SAVE_DIALOG)

        information = nomads.get_available_runs()
        most_recent_run = next(iter(information))
        if run_date == most_recent_run and run_time == information[most_recent_run][0]:
            hours = nomads.get_forecast_hours()

        else:
            hours = list(range(1, 121, 1)) + list(range(123, 385, 3))

        async def confirm_selection():
            if int(to_hour.value) > int(from_hour.value):
                selected_hours = list(range(int(from_hour.value), int(to_hour.value) + 1))
                selected_vars = [cb.text for cb in ElementFilter(kind=ui.checkbox, marker='Variable') if cb.value]
                selected_levels = [cb._markers[1] for cb in ElementFilter(kind=ui.checkbox, marker='Level') if cb.value]
                queue = Manager().Queue()

                count = 0

                count_lock = threading.Lock()

                def count_handler(q):
                    nonlocal count
                    while True:
                            q.get()
                            with count_lock:
                                count += 1
                                prgrbar.set_value(count/len(hours))
                counter_thread = threading.Thread(target=count_handler, args=(queue,), daemon=True)
                counter_thread.start()
                prgrbar = ui.linear_progress(value=0)

                await run.cpu_bound(
                    GFS_download,
                    hours=selected_hours,
                    run_date=run_date.replace('gfs.', ''),
                    run_time=run_time,
                    filename=file,
                    levels=selected_levels,
                    variables=selected_vars,
                    subregion=subregion,
                    queue=queue,
                )



                dialog.clear()
                with dialog, ui.card().style('padding: 20px;'):
                    ui.label("Download has finished.")
                    if not os.getenv("PANOPLY_PATH"):

                        ui.button("Exit", on_click=dialog.close)
                    else:
                      ui.label("Panoply Detected, Would you like to open it?")

                      grib_file = os.path.abspath(file)

                      ui.button("Open With Panoply", on_click=lambda: (
                        dialog.close(), subprocess.run(f'"{os.getenv("PANOPLY_PATH")}" "{grib_file}"', shell=True)))
                      ui.button("Exit", on_click=dialog.close)
            else:
                ui.notify('Invalid range! "To" hour must be greater than "From" hour.', type='negative')

        with (ui.dialog() as dialog, ui.card().style('padding: 20px;')):
            ui.label('Select Forecast Hours Range').style('font-size: 16px; font-weight: bold;')

            from_hour = ui.select(label='From Hour', options=hours)
            to_hour = ui.select(label='To Hour', options=hours)

            ui.button('Submit', on_click=confirm_selection
                      ).style('margin-top: 10px;')

        if all([top_entry.value, left_entry.value, right_entry.value, bottom_entry.value]):
            subregion = [int(float(top_entry.value)), int(float(bottom_entry.value)),
                         int(float(left_entry.value)), int(float(right_entry.value))]
        else:
            subregion = None
        dialog.open()

    with ui.row():
        run_dates = ui.select(options=list(nomads.get_available_runs().keys()))
        runs = ui.select(options=[''])
        run_dates.on_value_change(lambda: runs.set_options(nomads.get_available_runs().get(run_dates.value)))
        generated_elements.extend([run_dates, runs])
        download_button.on_click(lambda: Download(run_dates.value.strip('.gfs'), runs.value))


def GEM_download(**kwargs):
    urls = []
    hours = kwargs.get('hours')
    levels = kwargs.get('levels')
    variables = kwargs.get('variables')
    run_time = kwargs.get('run_time')
    for hour in hours:
        for level, variable in product(levels, variables):
            urls.append(GEM.create_url(hour, run_time, variable, 'ISBL', level))
    download_object = Downloader(urls)
    downloaded_data = download_object.submitdownloads()
    GribCreation(downloaded_data, 'gem.grib').merge_grib_files()


def GEM_Load(download_button, generated_elements):
    raise NotImplementedError
    ###
    GEM_Parse = GEM()
    with ui.row():
        run_dates = ui.select(options=list(GEM_Parse.get_runs_hours().keys()))
        runs = ui.select(options=[''])
        run_dates.on_value_change(lambda: runs.set_options(GEM_Parse.get_runs_hours().get(run_dates.value)))
        generated_elements.extend([run_dates, runs])
        download_button.on_click(lambda: ui.notify("Test"))
