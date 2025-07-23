import multiprocessing



import json
import os
import logging
import subprocess

import requests
import webview
from nicegui import ui, app
from modeldownloads import GFS_Load, GEM_Load

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app.title = 'MetPlot'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
template_path = os.path.join(BASE_DIR, 'templates', 'CoordsMAP.html')
CoordsHTML = open(template_path).read()
content = requests.get('https://nomads.ncep.noaa.gov/gribfilter.php?ds=gfs_0p25').content
top_entry = None
bottom_entry = None
left_entry = None
right_entry = None
download_button : ui.button
temp_elements = []

def global_navbar():
    ui.dark_mode().enable()
    with ui.row().style('''
        background-color: #1a1a1d; color: white; display: flex; justify-content: space-between; 
        align-items: center; padding: 15px 30px; position: fixed; top: 0; left: 0; right: 0; 
        z-index: 1000; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
    '''):
        ui.label('MetPlot').style('''
            font-weight: bold; text-transform: uppercase; letter-spacing: 2px;
            background-color: #ef4444; color: white; font-size: 24px;
            padding: 20px 48px; border-radius: 12px;
        ''')
        with ui.row().style('display: flex; gap: 30px;'):
            ui.link('Home', '/').style(
                'color: white; text-decoration: none; font-size: 16px; text-transform: uppercase; transition: color 0.3s ease, transform 0.3s ease;')
            ui.link('Download', '/download').style(
                'color: white; text-decoration: none; font-size: 16px; text-transform: uppercase; transition: color 0.3s ease, transform 0.3s ease;')
            ui.link('Settings', '/settings').style(
                'color: white; text-decoration: none; font-size: 16px; text-transform: uppercase; transition: color 0.3s ease, transform 0.3s ease;')
            #ui.link('RadarToCDF', '/radartocdf').style(
            #    'color: white; text-decoration: none; font-size: 16px; text-transform: uppercase; transition: color 0.3s ease, transform 0.3s ease;')


def file_read(file):
    with open(file) as file:
        if file.name.endswith('.json'):
            content = json.load(file)
        else:
            content = file.readlines()
            content = [i.strip('\n') for i in content]

        file.close()
    return content

@app.get('/update_coordinates/{top}/{bottom}/{left}/{right}')
def update_coordinates(top: float, bottom: float, left: float, right: float):
    global top_entry, bottom_entry, left_entry, right_entry
    top_entry.value = str(top)
    bottom_entry.value = str(bottom)
    left_entry.value = str(left)
    right_entry.value = str(right)

def model_load(variables_file : str, levels_file : str, model : str):
    while temp_elements:
        element = temp_elements.pop()
        element.delete()

    if model =='GFS':
     GFS_Load(download_button, top_entry, bottom_entry, left_entry, right_entry, temp_elements, content)
    else:
        GEM_Load(download_button, temp_elements)


    variables = file_read(variables_file)
    level_data = file_read(levels_file)

    level_data = [(line.strip(), line.strip().replace("lev_", "").replace("_mb", "mb"))
                  for line in level_data]

    with ui.column().style('margin-top: 15px; padding: 10px;') as el:
        temp_elements.append(el)

        ui.label('Variables').style('font-size: 14px;')
        keys = list(variables.keys())

        for i in range(0, len(keys), 12):
            with ui.row().classes('flex-wrap').style(
                    'align-items: center; margin-bottom: -8px; justify-content: space-evenly; gap: 5px;'
            ):
                for key in keys[i:i + 12]:
                    levels_str = ', '.join(variables[key]['levels'])
                    ui.checkbox(text=key).tooltip(f'Name: {variables[key]["name"]}, \n Levels: {levels_str}'
                                                  ).mark('Variable')

    ###################################################################
    with ui.column().style('margin-top: 15px; padding: 10px;') as el:
        temp_elements.append(el)


        ui.label('Vertical Levels').style('font-size: 14px;')

        with ui.row().classes('flex-wrap').style('align-items: center; margin-bottom: -8px;'):
                for original, formatted in level_data   :
                    ui.checkbox(text=formatted).mark(f'Level {original}')


MODELS = {'GFS': lambda : model_load('static/Variables/GFS/MERGED_PARAMS.json',
                                     'static/Variables/GFS/VERTICAL_LEVELS.txt', 'GFS'),

          'GEM' : lambda : model_load('static/Variables/GEM/MERGED_PARAMS.json',
                                      'static/Variables/GEM/VERTICAL_LEVELS.txt', 'GEM')}










@ui.page('/')
def main():
    global_navbar()

    with ui.column().style('margin-top: 100px; padding: 20px;'):
        ui.label('An App to Download Meteorological Data')


@ui.page('/download')
def downloader():
    global_navbar()
    ui.select(label='Model', options=[option for option in MODELS],
              on_change=
              lambda model: MODELS[model.value]()).style('margin-top:100px;')

    with ui.row().style("gap: 10px; margin-top: 20px; padding: 10px;"):
        global top_entry, bottom_entry, left_entry, right_entry, download_button

        for label in ['Top Latitude', 'Bottom Latitude', 'Left Longitude', 'Right Longitude']:
            with ui.column():
                ui.label(label)
                entry = ui.input(on_change=lambda: update_bounding_box_from_inputs())
                globals()[f"{label.split()[0].lower()}_entry"] = entry

        with ui.column():
          download_button= ui.button("Download").style(
              'margin-top:50px;'
          )



    def update_bounding_box_from_inputs():
        try:
            top = float(top_entry.value)
            bottom = float(bottom_entry.value)
            left = float(left_entry.value)
            right = float(right_entry.value)

            ui.run_javascript(f'''
                updateBoundingBoxFromInputs({top}, {bottom}, {left}, {right});
            ''')

        except ValueError:
            ui.notify('Please enter valid coordinates.')

    ui.add_body_html(CoordsHTML)

async def set_panoply_path():
    file = await app.native.main_window.create_file_dialog(dialog_type=webview.OPEN_DIALOG)
    if file:
     subprocess.run(['setx', 'PANOPLY_PATH', file[0]], shell=True)
     ui.notify("Set Panoply Path")
    else:
        return


@ui.page('/settings')
def settings_page():
    global_navbar()
    ui.button(text='Set Panoply Path', on_click=set_panoply_path).style('margin-top:100px;')

    with ui.row().style('margin-top: 15px; padding: 20px;'):

      if os.getenv('PANOPLY_PATH'):
        ui.label(f"Panoply Path is set : {os.getenv('PANOPLY_PATH')}")
      else:
          ui.label("Panoply Path is not set yet.")



ui.run(native=True,  window_size=(1600, 900), favicon='⛈️', title='MetPlot')
