import re
import os
import io
import matplotlib.pyplot as plt
from MetPlot.Exceptions.downloader_exceptions import InvalidCoordinates, InvalidColorMapFormat
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





def color_map_validator(colormap):
    if isinstance(colormap, str):
        if is_cpt_format(colormap):
            colormap = create_colormap(parse_cpt_string(colormap))
            return colormap


        try:
            colormap = plt.get_cmap(colormap)
            return colormap
        except ValueError:
            if os.path.isfile(colormap):
                file_content = read_file(colormap)
                if is_cpt_format(file_content):
                    colormap = create_colormap(parse_cpt_string(file_content))
                    return colormap
    elif isinstance(colormap, io.TextIOWrapper):
        content = colormap.read()
        if is_cpt_format(content):
            colormap = create_colormap(parse_cpt_string(content))
            return colormap
    else:

        raise InvalidColorMapFormat("Invalid Colormap format supplied")

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

