import datetime
import os
import customtkinter as ctk
from tkinter import colorchooser
import tkinter as tk
from PIL import Image, ImageTk
from tkinter.filedialog import asksaveasfilename
from CMAPTest import PlotData

class ColorToolApp(ctk.CTk):
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
        """Creates Widgets for the interface"""

        self.title_label = ctk.CTkLabel(self, text="CPT Generator", font=("Arial", 16))
        self.title_label.grid(row=0, column=2, columnspan=3, pady=20)

        self.gradient_preview = ctk.CTkCanvas(self, height=50, width=650, bg="white")
        self.gradient_preview.grid(row=1, column=2, padx=20, pady=20, columnspan=3)

        self.color_inputs_frame = ctk.CTkFrame(self)
        self.color_inputs_frame.grid(row=2, column=3, padx=20, pady=20, rowspan=4, sticky="nsew")

        self.save_button = ctk.CTkButton(self, text="Save As CPT", command=self.__export_cpt_with_name)
        self.save_button.grid(row=2, column=0, columnspan=3, pady=10, padx=10, sticky="w")

        self.dragging_color_index = None

        # Binding events for the gradient preview canvas
        self.gradient_preview.bind("<Button-1>", self.__add_color)
        self.gradient_preview.bind("<ButtonRelease-1>", self.__stop_drag)  # Stop dragging and update
        self.gradient_preview.bind("<B1-Motion>", self.drag_color_motion)  # Update color bar during motion

        # More buttons below the save button
        self.savebutt2 = ctk.CTkButton(self, text="Save CPT As Class __str__", command=self.SaveAsVAR)
        self.savebutt2.grid(row=3, column=0, columnspan=3, pady=10, padx=10, sticky="w")

        self.PositionFix = ctk.CTkButton(self, text="Equalize Positions", command=self.FixPosition)
        self.PositionFix.grid(row=4, column=0, columnspan=3, pady=10, padx=10, sticky="w")

        self.TestCMAP = ctk.CTkButton(self, text="Test Colormap", command=self.genmap)
        self.TestCMAP.grid(row=5, column=0, columnspan=3, pady=10, padx=10, sticky="w")

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
        self.color_inputs_frame = ctk.CTkFrame(self)
        self.color_inputs_frame.grid(row=2, column=3, padx=20, pady=20, rowspan=4, sticky="nsew")

        img = Image.new("RGB", (650, 50))
        pixels = img.load()
        for i in range(650):
            position = (i / 650) * 100
            color = self.__get_gradient_color(position)
            for j in range(50):
                pixels[i, j] = color

        self.gradient_img = ImageTk.PhotoImage(img)
        self.gradient_preview.create_image(0, 0, anchor=ctk.NW, image=self.gradient_img)
        for i, color in enumerate(self.colors):
            self.__create_color_stop(i, color["color"], color["position"])

    def __create_color_stop(self, index, color, position):
        x_position = position * 6.5
        stop = self.gradient_preview.create_oval(x_position - 10, 20, x_position + 10, 30, fill=color, outline="white", width=2)
        self.gradient_preview.tag_bind(stop, "<Button-1>", lambda e, idx=index: self.start_drag(e, idx))
        self.gradient_preview.tag_bind(stop, "<ButtonRelease-1>", self.__stop_drag)

        frame = ctk.CTkFrame(self.color_inputs_frame)
        frame.grid(row=index, column=0, sticky="ew", pady=2)

        color_button = ctk.CTkButton(frame, text="Choose Color", fg_color=color, width=3, command=lambda idx=index: self.__change_color(idx))
        color_button.grid(row=0, column=0, padx=5)

        position_entry = ctk.CTkEntry(frame, width=210)
        position_entry.insert(0, position)
        position_entry.grid(row=0, column=1, padx=5)
        position_entry.bind("<FocusOut>", lambda e, idx=index: self.__update_position(idx, position_entry.get()))

        remove_button = ctk.CTkButton(frame, text="Remove", command=lambda idx=index: self.remove_color(idx))
        remove_button.grid(row=0, column=2, padx=5)

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
            self.__update_gradient()  # Update the gradient bar
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

    def drag_color_motion(self, event):
        """Update the color bar (canvas) during the drag."""
        if self.dragging_color_index is not None:
            x = event.x
            new_position = (x / 6.5)  # Convert to percentage position
            new_position = max(0, min(100, new_position))

            # Temporarily update the position of the color stop (without updating the frame values)
            self.colors[self.dragging_color_index]['position'] = new_position
            self.__update_gradient()  # Update the canvas (color bar) immediately

    def __stop_drag(self, event=None):
        """Update the frame (values) after the drag is finished."""
        if self.dragging_color_index is not None:
            # Update values in the color inputs frame only after the drag is finished
            self.colors.sort(key=lambda x: x['position'])
            self.__update_gradient()  # Final update to color bar after drag finishes

            # Update the values in the input fields (position, color)
            self.__update_color_inputs()

            self.dragging_color_index = None

    def __update_color_inputs(self):
        """Update the values in the color inputs frame."""
        for idx, color in enumerate(self.colors):
            # Update position entry widgets
            position_entry = self.color_inputs_frame.grid_slaves(row=idx, column=1)[0]
            position_entry.delete(0, tk.END)
            position_entry.insert(0, color['position'])

            # Update color button widgets
            color_button = self.color_inputs_frame.grid_slaves(row=idx, column=0)[0]
            color_button.configure(fg_color=color['color'])

    def __generate_cpt_content(self):
        """Generates the CPT content as a string."""
        content = []
        for color in self.colors:
            content.append(f"{color['color']} {color['position']}")
        return "\n".join(content)

    def __export_cpt_with_name(self):
        """Exports the CPT to a file."""
        file_path = asksaveasfilename(defaultextension=".cpt", filetypes=[("CPT files", "*.cpt")])
        if file_path:
            with open(file_path, "w") as file:
                file.write(self.__generate_cpt_content())


ColorToolApp()
