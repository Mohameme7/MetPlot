import asyncio
import threading

import customtkinter as ctk

from MetPlot.Downloader.Async_Downloader.AsyncApproach import download_and_write_all
from MetPlot.Downloader.URLGenerator import URLGen

urls = []
hours = list(range(1, 121, 1)) + list(range(120,156,3))
for hour in hours:
    url = URLGen(hour, '2025-1-5', '12', ['VVEL', 'APCP'], ['surface', 850, 1000, 500], subregion=[42, 12, 25, 60])
    urls.append(str(url))


def start_download(output_file, progress_label, time_label):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(download_and_write_all(output_file, progress_label, time_label))
    finally:
        loop.stop()
        loop.close()


def create_gui():
    app = ctk.CTk()
    app.title("Downloader")
    app.geometry("400x250")

    frame = ctk.CTkFrame(app, corner_radius=10)
    frame.pack(pady=20, padx=20, fill="both", expand=True)

    progress_label = ctk.CTkLabel(frame, text="Click 'Start' to begin downloading.")
    progress_label.pack(pady=10)

    time_label = ctk.CTkLabel(frame, text="")
    time_label.pack(pady=10)

    def on_start():
        progress_label.configure(text="Downloading in progress...")
        time_label.configure(text="")
        download_thread = threading.Thread(
            target=start_download, args=("GFSTest.grib", progress_label, time_label)
        )
        download_thread.start()

    button = ctk.CTkButton(frame, text="Start", command=on_start)
    button.pack(pady=10)

    app.mainloop()


if __name__ == "__main__":
    download_progress = [0]
    create_gui()