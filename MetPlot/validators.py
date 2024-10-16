from MetPlot.Exceptions.downloader_exceptions import InvalidCoordinates


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

