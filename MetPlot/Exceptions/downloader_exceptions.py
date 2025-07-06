class InvalidRequestMethodError(ValueError):
    """Raised when an invalid request method is provided."""
    pass


class InvalidCoordinates(ValueError):
    """Raised when coordinates do not meet the criteria."""
    pass


class InvalidColorMapFormat(ValueError):
    """Raised when the provided colormap format is invalid"""
    pass


class NomadsError(Exception):
    """Exception base class for all errors related to the GFS Model."""
    pass


class InvalidParameter(NomadsError):
    """Raised when the provided parameter is not available."""
    pass


class InvalidURL(NomadsError):
    pass


