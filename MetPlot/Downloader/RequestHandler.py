import httpx
from typing import Literal, NamedTuple
from MetPlot.Exceptions.downloader_exceptions import InvalidRequestMethodError

class RequestInfo(NamedTuple):
    """Returned Request Information Needed for the download process"""
    status_code: int
    response_text: str
    success: bool
    response_handler : httpx.Response


class RequestClient(httpx.Client):
    def __init__(self):
        super().__init__(timeout=httpx.Timeout(20))

    def SendRequest(self, method: Literal['get', 'post'], **kwargs) -> RequestInfo:
        """
        Sends a request with desired method and parameters
        :param method: Request Method
        :param kwargs: Request Params, eg: url, json, data, proxy
        :return Returns a RequestInfo object : (status_code, response_text, success, response_object)
        :raises ValueError: If Request Method is not supported
        """
        RequestTypes = {
            'post': lambda: self.post(**kwargs),
            'get': lambda: self.get(**kwargs),
        }
        if method in RequestTypes:
            response = RequestTypes[method.lower()]()
            return RequestInfo(status_code=response.status_code, response_text=response.content,
                               success=response.is_success, response_handler=response)

        raise InvalidRequestMethodError(f'{method} not found.')
