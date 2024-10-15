class InvalidRequestMethodError(ValueError):
    """Raised when an invalid request method is provided."""
    pass


class InvalidCoordinates(ValueError):
    pass


class InvalidCMAP(ValueError):
    pass


class NomadsError(Exception):
    pass


class InvalidParameter(NomadsError):
    pass


class InvalidURL(NomadsError):
    pass
