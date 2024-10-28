import re
import os
import io
import matplotlib.pyplot as plt
from MetPlot.Exceptions.downloader_exceptions import InvalidCoordinates, InvalidCMAP
from MetPlot.utils.parsecpt import read_file, create_colormap, parse_cpt_string


def validate_coords(botlat, toplat, leftlon, rightlon) -> None:
    """Validates Given Coordinates
    :param botlat: Bottom latitude
    :param toplat : Top latitude
    :param leftlon : Left longitude
    :param rightlon : Right longitude
    :raises InvalidCoordinates Exception
    :returns None
    """

    if not (-90 <= botlat <= 90 and -90 <= toplat <= 90 and -180 <= leftlon <= 180 and -180 <=
            rightlon <= 180):
        raise InvalidCoordinates("Coordinates are out of bounds")
    if not (toplat > botlat or rightlon > leftlon):
        raise InvalidCoordinates("Invalid coordinate ordering")





def ColorMapValidator(Colormap):
    if isinstance(Colormap, str):
        if is_cpt_format(Colormap):
            Colormap = create_colormap(parse_cpt_string(Colormap))
            return Colormap
        try:
            Colormap = plt.get_cmap(Colormap)
            return Colormap
        except Exception:
            if os.path.isfile(Colormap):
                FileContent = read_file(Colormap)
                if is_cpt_format(FileContent):
                    Colormap = create_colormap(parse_cpt_string(FileContent))
                    return Colormap
    elif isinstance(Colormap, io.TextIOWrapper):
        content = Colormap.read()
        if is_cpt_format(content):
            Colormap = create_colormap(parse_cpt_string(content))
            return Colormap
    raise InvalidCMAP("Invalid Colormap format supplied")

def is_cpt_format(content: str) -> bool:
    range_line_pattern = re.compile(
        r"^\s*-?\d+(\.\d+)?\s+\d+\s+\d+\s+\d+\s+-?\d+(\.\d+)?\s+\d+\s+\d+\s+\d+\s*$"
    )
    special_line_pattern = re.compile(r"^\s*[BFN]\s+\d+\s+\d+\s+\d+\s*$")
    lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.startswith("#")
    ]

    return all(
        range_line_pattern.match(line) or special_line_pattern.match(line)
        for line in lines
    )
    # Honestly I haven't written this myself, Regex isn't very fun to do

