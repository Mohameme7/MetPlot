import sys
import types
import queue
from unittest import mock

import httpx
import numpy as np
import pytest

try:
    import pygrib  # noqa: F401
except ImportError:
    sys.modules["pygrib"] = types.ModuleType("pygrib")

from MetPlot.Downloader import FileHandler, misc
from MetPlot.Downloader.MemoryDownload import Downloader
from MetPlot.Downloader.RequestHandler import RequestClient, RequestInfo
from MetPlot.Exceptions.downloader_exceptions import InvalidRequestMethodError


# ---------------- RequestClient ----------------
def test_request_client_defaults():
    c = RequestClient()
    assert c.follow_redirects is True
    assert "Mozilla" in c.headers["User-Agent"]
    c.close()


def test_send_request_get_and_post():
    c = RequestClient()
    resp = httpx.Response(200, content=b"hi")
    with mock.patch.object(c, "get", return_value=resp) as g, mock.patch.object(c, "post", return_value=resp) as p:
        info = c.SendRequest("get", url="http://x")
        assert isinstance(info, RequestInfo)
        assert (info.status_code, info.response_text, info.success) == (200, b"hi", True)
        g.assert_called_once_with(url="http://x")
        c.SendRequest("post", url="http://x", json={})
        p.assert_called_once_with(url="http://x", json={})
    c.close()


def test_send_request_failure_flag():
    c = RequestClient()
    with mock.patch.object(c, "get", return_value=httpx.Response(404, content=b"")):
        assert c.SendRequest("get", url="u").success is False
    c.close()


def test_send_request_invalid_method():
    c = RequestClient()
    with pytest.raises(InvalidRequestMethodError):
        c.SendRequest("delete", url="u")
    c.close()


# ---------------- Downloader ----------------
def _ok(data=b"data"):
    return RequestInfo(200, data, True, None)


def test_retrieve_data_success_notifies_queue():
    q = queue.Queue()
    d = Downloader(["u"], q)
    with mock.patch.object(d, "SendRequest", return_value=_ok()):
        assert d.retrieve_data("u") == b"data"
    assert q.qsize() == 1


def test_retrieve_data_http_failure_returns_empty():
    q = queue.Queue()
    d = Downloader(["u"], q)
    with mock.patch.object(d, "SendRequest", return_value=RequestInfo(404, b"", False, None)):
        assert d.retrieve_data("u") == b""
    assert q.qsize() == 1


def test_retrieve_data_retries_then_succeeds():
    d = Downloader(["u"])
    side = [httpx.ConnectError("x"), httpx.ReadTimeout("x"), _ok(b"ok")]
    with mock.patch.object(d, "SendRequest", side_effect=side) as s, mock.patch("time.sleep") as sl:
        assert d.retrieve_data("u") == b"ok"
    assert s.call_count == 3
    assert [c.args[0] for c in sl.call_args_list] == [1, 2]


def test_retrieve_data_gives_up():
    q = queue.Queue()
    d = Downloader(["u"], q)
    with mock.patch.object(d, "SendRequest", side_effect=httpx.RemoteProtocolError("x")) as s, \
            mock.patch("time.sleep"):
        assert d.retrieve_data("u") == b""
    assert s.call_count == Downloader.MAX_RETRIES
    assert q.qsize() == 1


def test_retrieve_data_unexpected_error_propagates():
    d = Downloader(["u"])
    with mock.patch.object(d, "SendRequest", side_effect=KeyError("x")):
        with pytest.raises(KeyError):
            d.retrieve_data("u")


def test_submit_downloads_preserves_order():
    d = Downloader(["a", "b", "c"])
    with mock.patch.object(d, "retrieve_data", side_effect=lambda u: u.encode()):
        assert d.submit_downloads() == [b"a", b"b", b"c"]


def test_submit_downloads_empty():
    assert Downloader([]).submit_downloads() == []


# ---------------- misc ----------------
def test_fetch_sizes():
    heads = iter([{"Content-Length": "10"}, {"Content-Length": "5"}, {}])
    with mock.patch.object(misc.requests, "get",
                           side_effect=lambda *a, **k: types.SimpleNamespace(headers=next(heads))):
        assert misc.fetch_sizes(["a", "b", "c"]) == 15


def test_fetch_sizes_empty():
    assert misc.fetch_sizes([]) == 0


def test_file_read_json_and_text(tmp_path):
    j = tmp_path / "a.json"
    j.write_text('{"a": 1}')
    t = tmp_path / "a.txt"
    t.write_text("x\ny\n")
    assert misc.file_read(str(j)) == {"a": 1}
    assert misc.file_read(str(t)) == ["x", "y"]


# ---------------- FileHandler ----------------
def test_crop_coords_command(monkeypatch):
    with mock.patch.object(FileHandler.subprocess, "run") as run:
        FileHandler.crop_coords("in.grib", "out.grib", 1, 2, 3, 4)
    cmd = run.call_args.args[0]
    assert cmd[0].endswith("wgrib2.exe" if sys.platform == "win32" else "wgrib2")
    assert cmd[1:] == ["in.grib", "-small_grib", "1:2", "3:4", "out.grib"]
    assert run.call_args.kwargs["check"] is True


def test_crop_coords_propagates_failure():
    import subprocess
    with mock.patch.object(FileHandler.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "x")):
        with pytest.raises(subprocess.CalledProcessError):
            FileHandler.crop_coords("a", "b", 1, 2, 3, 4)


def test_grib_creation_merges(tmp_path):
    class Msg:
        def __init__(self, b): self.b = b
        def tostring(self): return self.b

    class FakeGF:
        def __init__(self, path): self.path = path
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def __iter__(self):
            return iter([Msg(open(self.path, "rb").read() + b"1"), Msg(b"2")])

    out = tmp_path / "out.grib"
    with mock.patch.object(FileHandler.pygrib, "open", create=True, side_effect=lambda p: FakeGF(p)):
        gc = FileHandler.GribCreation([b"A", b"B"], str(out))
    assert out.read_bytes() == b"A12B12"
    assert gc.FileName == str(out)


def test_grib_creation_empty(tmp_path):
    out = tmp_path / "o.grib"
    FileHandler.GribCreation([], str(out))
    assert out.read_bytes() == b""
