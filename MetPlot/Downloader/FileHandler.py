import os
import tempfile

import pygrib


class GribCreation:
    def __init__(self, Data, FileName: str):
        self.Data = Data
        self.FileName = FileName
        self.merge_grib_files()

    def merge_grib_files(self) -> None:
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

