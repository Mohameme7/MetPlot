from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import subprocess, threading, os, re ,json, asyncio, bz2, webview
from MetPlot.utils.coordinates import bbox_percent
import requests
from nicegui import ui, ElementFilter, app, run
from MetPlot.Downloader.FileHandler import GribCreation, crop_coords
from MetPlot.Downloader.MemoryDownload import Downloader
from MetPlot.Downloader.Parsers.NomadsUtils import NomadsParse
from MetPlot.Downloader.Parsers.GEM import GEM
from itertools import product
from multiprocessing import Manager
from MetPlot.Downloader.Parsers.icon import IconParse
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


def fetch_sizes(urls):
    sizes = []
    def fetch_size(url):
        req = requests.get(url, stream=True)
        sizes.append(int(req.headers.get('Content-Length') or 0))
    with ThreadPoolExecutor() as executor:
        executor.map(fetch_size, urls)
    return sum(sizes)

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
    downloaded_data = download_object.submit_downloads()
    GribCreation(downloaded_data, filename).merge_grib_files()





def GFS_Load(download_button, top_entry, bottom_entry, left_entry, right_entry, generated_elements, content):

    for element in [top_entry, bottom_entry, left_entry, right_entry]:
        element.enable()

    nomads = NomadsParse(content)

    async def Download(run_date, run_time):
        file = await app.native.main_window.create_file_dialog(dialog_type=webview.SAVE_DIALOG)
        if isinstance(file, tuple):
            file = file[0]
        information = nomads.get_available_runs()
        most_recent_run = next(iter(information))
        if run_date == most_recent_run.strip('.gfs') and run_time == information[most_recent_run][0]:
            hours = nomads.get_forecast_hours()
        else:
            hours = list(range(1, 121, 1)) + list(range(123, 385, 3))
        async def confirm_selection():
            if int(to_hour.value) > int(from_hour.value):
                selected_hours, selected_vars, selected_levels = get_selections(from_hour, to_hour, hours)
                prgrbar = ui.linear_progress(value=0)
                queue, counter_thread = counter(prgrbar, len(selected_hours))
                counter_thread()
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
                finished_dialog(dialog, file)

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

def FilterGEM(level):
   NonISBL = {
        'SFC': ['0'],
        'MSL': ['0'],
        'TGL': ['2', '10'],
        'NTAT': ['0'],
        'DBLL': ['0'],
        'PVU': ['1'],
        'EATM' : ['0', '']
    }
   if level in NonISBL:
       return level, NonISBL[level]
   return 'ISBL', [level]

def GEM_download(**kwargs):
    urls = []
    hours = kwargs.get('hours')
    levels = kwargs.get('levels')
    variables = kwargs.get('variables')
    run_time = kwargs.get('run_time')
    file_name = kwargs.get('file_name')
    queue = kwargs.get('queue')
    subregion = kwargs.get('subregion')
    size_var = kwargs.get('size_var')

    for hour in hours:
        for level, variable in product(levels, variables):
            typeoflvl, level_values  = FilterGEM(level)
            for lv in level_values:
             urls.append(GEM.create_url(hour, run_time, variable, typeoflvl, lv))
    if subregion:
       size_var.value=fetch_sizes(urls)*bbox_percent(*subregion)
    else:
        size_var.value = fetch_sizes(urls)

    download_object = Downloader(urls, queue)
    downloaded_data = download_object.submit_downloads()
    GribCreation(downloaded_data, file_name).merge_grib_files()
    if subregion:
        crop_coords(
            file_name,
            file_name.replace('.grib', '_Cropped.grib'),
            subregion[2], subregion[3], subregion[1], subregion[0]
        )
        if os.path.exists(file_name):
            os.remove(file_name)



def GEM_Load(download_button : ui.button, generated_elements, top_entry, bottom_entry, left_entry, right_entry):
    Bus.clear_subscribers()

    GEM_Parse = GEM()
    for element in [top_entry, bottom_entry, left_entry, right_entry]:
        element.enable()
    async def Download(run_time):
        file = await app.native.main_window.create_file_dialog(dialog_type=webview.SAVE_DIALOG)
        if isinstance(file, tuple):
            file = file[0]


        hours = GEM_Parse.get_forecast_hours(run_time)
        async def confirm_selection():
            if int(to_hour.value) > int(from_hour.value):
                selected_hours, selected_vars, selected_levels = get_selections(from_hour, to_hour, hours)
                alllinkscount = sum(
                     len(FilterGEM(level)[1])
                     for hour in selected_hours
                     for level, _ in product(selected_levels, selected_vars)
                )

                prgrbar = ui.linear_progress(value=0)
                queue, counter_thread = counter(prgrbar, alllinkscount)
                counter_thread()

                await run.io_bound(
                    GEM_download,
                    hours=selected_hours,
                    run_time=run_time,
                    levels=selected_levels,
                    variables=selected_vars,
                    file_name = file,
                    queue=queue,
                    subregion = subregion,
                    size_var = size_var
                )
                dialog.clear()
                finished_dialog(dialog, file)

            else:
                ui.notify('Invalid range! "To" hour must be greater than "From" hour.', type='negative')

        with (ui.dialog() as dialog, ui.card().style('padding: 20px;')):
            ui.label('Select Forecast Hours Range').style('font-size: 16px; font-weight: bold;')
            from_hour = ui.select(label='From Hour', options=hours)
            to_hour = ui.select(label='To Hour', options=hours)
            ui.button('Submit', on_click=confirm_selection
                      ).style('margin-top: 10px;')
            size_label = ui.label(f"Estimated Size: ?")
            size_var = Observable(name="Size", inital_value=0, bus=Bus)
            Bus.subscribe("Size_changed", lambda: size_label.set_text(f"Estimated Size: {size_var.value/1000000} MB"))
        dialog.open()
        if all([top_entry.value, left_entry.value, right_entry.value, bottom_entry.value]):
            subregion = [int(float(top_entry.value)), int(float(bottom_entry.value)),
                         int(float(left_entry.value)), int(float(right_entry.value))]
        else:
            subregion = None

    with ui.row():
        run_dates = ui.select(options=list(GEM_Parse.get_runs_hours().keys()))
        generated_elements.extend([run_dates])
        download_button.on_click(lambda: Download(run_dates.value))

def Icon_download(**kwargs):
    hours = kwargs.get('hours')
    run_date = kwargs.get('run_date')
    run_time = kwargs.get('run_time')
    variables = kwargs.get('variables')
    levels = kwargs.get('levels')
    typesoflevels = kwargs.get("typesoflevels")
    filename = kwargs.get('filename')
    queue = kwargs.get('queue')
    size_var = kwargs.get('size_var')

    urls = []
    for hour in hours:
        for level, variable, typeoflevel in product(levels, variables, typesoflevels):
             urls.append(IconParse.create_url(int(hour), run_time,run_date, typeoflevel, variable, level))
    size_var.value = fetch_sizes(urls)


    download_object = Downloader(urls, queue=queue if queue else None)
    downloaded_data = download_object.submit_downloads()
    grib_bytes_list = [bz2.decompress(data) for data in downloaded_data]
    GribCreation(grib_bytes_list, filename).merge_grib_files()


def Icon_load(download_button,generated_elements,var_json, *args):
    Bus.clear_subscribers()
    for arg in args:
        arg.disable()

    content = var_json




    async def Download(run_time, run_date):
        file = await app.native.main_window.create_file_dialog(dialog_type=webview.SAVE_DIALOG)
        if isinstance(file, tuple):
            file = file[0]

        hours = list(model_parser.get_forecast_hours(run_time))
        async def confirm_selection():
            if int(to_hour.value) > int(from_hour.value):
                selected_hours, selected_vars, selected_levels = get_selections(from_hour, to_hour, hours)
                selected_levels = selected_levels or [None]
                selected_level_types = []
                for var in selected_vars:
                    levels = content[var]['levels']

                    for lvl in levels:
                        m = re.findall(r"typeOfLevel\s*:\s*(\S+)", lvl)
                        if m:
                         selected_level_types.append(m[0])

                alllinkscount = len(selected_hours) * len(selected_levels) * len(selected_vars) * len(selected_level_types)


                prgrbar = ui.linear_progress(value=0)
                queue, counter_thread = counter(prgrbar, alllinkscount)
                counter_thread()

                await run.io_bound(
                    Icon_download,
                    hours=selected_hours,
                    run_time=run_time,
                    levels=selected_levels,
                    variables=selected_vars,
                    run_date = run_date,
                    typesoflevels = selected_level_types,
                    filename = file,
                    queue=queue,
                    size_var=size_var,

                )
                dialog.clear()
                finished_dialog(dialog, file)

            else:
                ui.notify('Invalid range! "To" hour must be greater than "From" hour.', type='negative')

        with (ui.dialog() as dialog, ui.card().style('padding: 20px;')):
            ui.label('Select Forecast Hours Range').style('font-size: 16px; font-weight: bold;')

            from_hour = ui.select(label='From Hour', options=hours)
            to_hour = ui.select(label='To Hour', options=hours)
            ui.button('Submit', on_click=confirm_selection
                      ).style('margin-top: 10px;')
            size_label = ui.label(f"Estimated Size: ?")
            size_var = Observable(name="Size", inital_value=0, bus=Bus)
            Bus.subscribe("Size_changed", lambda: size_label.set_text(f"Estimated Size: {size_var.value/1000000} MB"))
        dialog.open()


    with ui.row():
        model_parser = IconParse()
        utc_now = datetime.now(timezone.utc)
        utc_today = utc_now.strftime('%Y-%m-%d')
        utc_yesterday = (utc_now - timedelta(days=1)).strftime('%Y-%m-%d')
        today_runs, yesterday_runs = model_parser.get_available_runs()
        dates_run = {
            utc_today : today_runs,
            utc_yesterday : yesterday_runs
        }

        run_dates = ui.select(options=[utc_today, utc_yesterday],
                              on_change = lambda : runs.set_options(dates_run[run_dates.value]))

        runs = ui.select(options=[])
        generated_elements.extend([run_dates, runs])

        download_button.on_click(lambda: Download(runs.value, datetime.strptime(run_dates.value, "%Y-%m-%d")
                                                  .strftime("%Y%m%d")))
