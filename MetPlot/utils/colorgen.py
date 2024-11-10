import datetime
import os
import tkinter as tk
from tkinter import colorchooser
from PIL import Image, ImageTk
from tkinter.filedialog import asksaveasfilename
from MetPlot.utils.CMAPTest import PlotData
class ColorToolApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("CPT Generator")
        self.geometry("800x600")

        self.colors = [
            {"color": "#ff0000", "position": 100},
            {"color": "#00ff00", "position": 50},
            {"color": "#0000ff", "position": 0}
        ]
        self.cpt = ''
        self.__create_widgets()
        self.__update_gradient()
        self.mainloop()
    def __repr__(self):
        return self.cpt


    def __create_widgets(self):
        '''Creates Widgets for the interface'''
        self.title_label = tk.Label(self, text="CPT Generator", font=("Arial", 16))
        self.title_label.pack(pady=20)

        self.gradient_preview = tk.Canvas(self, height=50, width=650, bg="white")
        self.gradient_preview.pack(padx=20, pady=20)

        self.color_inputs_frame = tk.Frame(self)
        self.color_inputs_frame.pack(side=tk.RIGHT, padx=20, pady=20)


        self.save_button = tk.Button(self, text="Save As CPT", command=self.__export_cpt_with_name)
        self.save_button.pack(side=tk.TOP,anchor="w", padx=10)

        self.dragging_color_index = None

        self.gradient_preview.bind("<Button-1>", self.__add_color)
        self.gradient_preview.bind("<B1-Motion>", self.drag_color_stop)
        self.gradient_preview.bind("<ButtonRelease-1>", self.__stop_drag)

        self.savebutt2 = tk.Button(self, text="Save CPT As Class __str__", command=self.SaveAsVAR)
        self.savebutt2.pack(side=tk.TOP, anchor="w",padx=10)
        self.PositionFix = tk.Button(self, text="Equalize Positions", command=self.FixPosition)
        self.PositionFix.pack(side=tk.TOP,anchor="w", padx=10)

        self.TestCMAP = tk.Button(self,anchor="w", text="Test Colormap", command = self.genmap)
        self.TestCMAP.pack(side=tk.TOP, padx=10, anchor="w")

    def SaveAsVAR(self):
        """Saves the CPT as a string and can be called with __str__, EG: print(ColorClass)"""
        self.cpt = self.__generate_cpt_content()
        self.destroy()


    def FixPosition(self):
        ColorNum = len(self.colors)
        for idx, color in enumerate(self.colors):
            new_position = (100 / (ColorNum - 1)) * idx
            self.__update_position(idx, new_position)

    def genmap(self):
        PlotData(self.__generate_cpt_content())

    def __update_gradient(self):
        self.gradient_preview.delete("all")
        self.color_inputs_frame.destroy()
        self.color_inputs_frame = tk.Frame(self)
        self.color_inputs_frame.pack(pady=20)

        img = Image.new("RGB", (650, 50))
        pixels = img.load()
        for i in range(650):
            position = (i / 650) * 100
            color = self.__get_gradient_color(position)
            for j in range(50):
                pixels[i, j] = color

        self.gradient_img = ImageTk.PhotoImage(img)
        self.gradient_preview.create_image(0, 0, anchor=tk.NW, image=self.gradient_img)
        for i, color in enumerate(self.colors):
            self.__create_color_stop(i, color["color"], color["position"])

    def __create_color_stop(self, index, color, position):
        x_position = position * 6.5
        stop = self.gradient_preview.create_oval(x_position - 10, 20, x_position + 10, 30, fill=color, outline="white", width=2)
        self.gradient_preview.tag_bind(stop, "<Button-1>", lambda e, idx=index: self.start_drag(e, idx))
        self.gradient_preview.tag_bind(stop, "<ButtonRelease-1>", self.__stop_drag)

        frame = tk.Frame(self.color_inputs_frame)
        frame.pack(fill=tk.X, pady=2)

        color_button = tk.Button(frame, bg=color, width=3, command=lambda idx=index: self.__change_color(idx))
        color_button.pack(side=tk.LEFT, padx=5)

        position_entry = tk.Entry(frame, width=5)
        position_entry.insert(0, position)
        position_entry.pack(side=tk.LEFT, padx=5)
        position_entry.bind("<FocusOut>", lambda e, idx=index: self.__update_position(idx, position_entry.get()))

        remove_button = tk.Button(frame, text="Remove", command=lambda idx=index: self.remove_color(idx))
        remove_button.pack(side=tk.LEFT, padx=5)

    def __get_gradient_color(self, position):
        self.colors.sort(key=lambda x: x['position'])

        if position <= self.colors[0]['position']:
            return self.hex_to_rgb(self.colors[0]['color'])
        elif position >= self.colors[-1]['position']:
            return self.hex_to_rgb(self.colors[-1]['color'])
        for i in range(len(self.colors) - 1):
            pos1 = self.colors[i]['position']
            pos2 = self.colors[i + 1]['position']
            if pos1 == pos2:
                continue
            if pos1 <= position <= pos2:
                ratio = (position - pos1) / (pos2 - pos1)
                color1 = self.hex_to_rgb(self.colors[i]['color'])
                color2 = self.hex_to_rgb(self.colors[i + 1]['color'])
                blended_color = (
                    int(color1[0] + (color2[0] - color1[0]) * ratio),
                    int(color1[1] + (color2[1] - color1[1]) * ratio),
                    int(color1[2] + (color2[2] - color1[2]) * ratio)
                )
                return blended_color
        return (0, 0, 0)

    def hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def __add_color(self, event):
        '''Adds A New color when clicking on the color bar'''
        if self.dragging_color_index is None:
            position = event.x / 5.6
            new_color = {"color": "#ffffff", "position": position}
            self.colors.append(new_color)
            self.colors.sort(key=lambda x: x['position'])
            self.__update_gradient()

    def __change_color(self, index):
        color_code = colorchooser.askcolor(title="Choose color")[1]
        if color_code:
            self.colors[index]['color'] = color_code
            self.__update_gradient()

    def __update_position(self, index, value):
        try:
            position = float(value)
            self.colors[index]['position'] = max(0, min(100, position))
            self.colors.sort(key=lambda x: x['position'])
            self.__update_gradient()
        except ValueError:
            pass

    def remove_color(self, index):
        if len(self.colors) > 2:
            self.colors.pop(index)
            self.__update_gradient()

    def start_drag(self, event, index):
        """Event func to trigger when the user is starting to drag"""
        self.dragging_color_index = index
        self.drag_data = {'x': event.x}

    def drag_color_stop(self, event):
        if self.dragging_color_index is not None:
            x = event.x
            new_position = (x / 6.5)
            new_position = max(0, min(100, new_position))

            self.colors[self.dragging_color_index]['position'] = new_position
            self.colors.sort(key=lambda x: x['position'])
            self.__update_gradient()

    def __stop_drag(self, event=None):
        self.dragging_color_index = None

    def __export_cpt_with_name(self):
        """Exports the CPT To a file"""
        CPTContent = self.__generate_cpt_content()
        InitialDir = None
        if os.path.exists(os.path.join(os.path.expanduser("~"), ".gissjava")):
            InitialDir = os.path.join(os.path.expanduser("~"), ".gissjava/colorbars")
        save_filename = asksaveasfilename(initialdir=InitialDir,title="Save file as", defaultextension=".txt",
                                          filetypes=[("CPT Files", "*.cpt"), ("All files", "*.*")])
        if save_filename:
            with open(save_filename, 'w') as f:
                f.write(CPTContent)
        else:
            with open(f"{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.cpt", 'w') as file:
                file.write(CPTContent)


    def __generate_cpt_content(self):
        """Generates the CPT Content"""
        cpt_content = "# CPT-GRASS\n# COLOR_MODEL = RGB\n"
        self.colors.sort(key=lambda x: x['position'])
        for i in range(len(self.colors) - 1):
            current_color = self.colors[i]
            next_color = self.colors[i + 1]
            current_rgb = self.hex_to_rgb(current_color["color"])
            next_rgb = self.hex_to_rgb(next_color["color"])
            cpt_content += f"{current_color['position']} {current_rgb[0]} {current_rgb[1]} {current_rgb[2]} {next_color['position']} {next_rgb[0]} {next_rgb[1]} {next_rgb[2]}\n"
        return cpt_content




ColorToolApp()