import sys
import subprocess
from pathlib import Path


class GribCreation:
    def __init__(self, Data, FileName: str):
        self.Data = Data
        self.FileName = FileName
        self.merge_grib_files()

    def merge_grib_files(self) -> str:
        """Merge multiple GRIB byte chunks directly into one GRIB file.
        """
        with open(self.FileName, "wb") as outfile:
            for grib_content in self.Data:
                if grib_content:
                    outfile.write(grib_content)
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
        output_file,
    ]

    subprocess.run(cmd, check=True)
