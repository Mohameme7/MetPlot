import os
import sys
import tempfile
import subprocess
from pathlib import Path
import pygrib


class GribCreation:
    def __init__(self, Data, FileName: str):
        self.Data = Data
        self.FileName = FileName
        self.merge_grib_files()

    def merge_grib_files(self) -> str:
        """Merge multiple GRIB data into one file."""
        with open(self.FileName, 'wb') as outfile:
            for i, grib_content in enumerate(self.Data):

                    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                        temp_file.write(grib_content)
                        temp_file.flush()

                        with pygrib.open(temp_file.name) as gf:
                            for msg in gf:
                                outfile.write(msg.tostring())
                        temp_file.close()
                        os.remove(temp_file.name)
        return self.FileName


def crop_coords(input_file, output_file, lat_min, lat_max, lon_min, lon_max):
    base_dir = Path(__file__).parent.parent / "wgrib"
    if sys.platform == "win32":
        wgrib2_path = base_dir / "wgrib2.exe"
    else:
        wgrib2_path = base_dir / "wgrib2"

    cmd = [
        str(wgrib2_path),
        input_file,
        "-small_grib", f"{lat_min}:{lat_max}", f"{lon_min}:{lon_max}",
        output_file
    ]

    subprocess.run(cmd, check=True)
