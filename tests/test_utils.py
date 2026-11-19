import math

import numpy as np
import pytest

from MetPlot.Exceptions.downloader_exceptions import (
    InvalidColorMapFormat, InvalidCoordinates, InvalidParameter, InvalidRequestMethodError,
    InvalidURL, NomadsError)
from MetPlot.Exceptions.parser_errors import InvalidRun
from MetPlot.utils.RandDataGenerator import MapDataGenerator, MapInfo
from MetPlot.utils.coordinates import bbox_percent
from MetPlot.utils.idx_reader import IDX_Reader
from MetPlot.utils.parsecpt import create_colormap, parse_cpt_string, read_file
from MetPlot.validators import color_map_validator, is_cpt_format, validate_coords
from MetPlot.Variables import catalog_path
import MetPlot

CPT = "0 0 0 0 50 255 0 0\n50 255 0 0 100 255 255 255\n"


# ---- exceptions
def test_exception_hierarchy():
    for exc in (InvalidRequestMethodError, InvalidCoordinates, InvalidColorMapFormat, InvalidRun):
        assert issubclass(exc, ValueError)
    assert issubclass(InvalidParameter, NomadsError)
    assert issubclass(InvalidURL, NomadsError)
    assert issubclass(NomadsError, Exception)


def test_version():
    assert MetPlot.__version__ == "0.1.0"


# ---- validate_coords
def test_validate_coords_ok():
    assert validate_coords(-10, 10, -20, 20) is None


@pytest.mark.parametrize("kw", [
    dict(botlat=-91, toplat=10, leftlon=0, rightlon=10),
    dict(botlat=0, toplat=91, leftlon=0, rightlon=10),
    dict(botlat=0, toplat=10, leftlon=-181, rightlon=10),
    dict(botlat=0, toplat=10, leftlon=0, rightlon=181),
])
def test_validate_coords_out_of_bounds(kw):
    with pytest.raises(InvalidCoordinates):
        validate_coords(**kw)


def test_validate_coords_bad_ordering():
    with pytest.raises(InvalidCoordinates):
        validate_coords(botlat=10, toplat=0, leftlon=10, rightlon=0)


def test_validate_coords_boundaries_inclusive():
    validate_coords(-90, 90, -180, 180)


# ---- cpt
def test_is_cpt_format():
    assert is_cpt_format(CPT)
    assert is_cpt_format("# comment\n" + CPT + "B 0 0 0\nF 255 255 255\nN 128 128 128\n")
    assert not is_cpt_format("viridis")
    assert not is_cpt_format("0 0 0 0 50 255 0")


def test_parse_cpt_string():
    colors = parse_cpt_string(CPT)
    assert colors[0][0] == 0.0 and colors[-1][0] == 1.0
    assert colors[0][1] == (0, 0, 0)
    assert colors[-1][1] == (1.0, 1.0, 1.0)
    assert [c[0] for c in colors] == sorted(c[0] for c in colors)


def test_parse_cpt_string_empty_and_comments():
    assert parse_cpt_string("") == []
    assert parse_cpt_string("# only comment\n\n") == []


def test_create_colormap():
    cmap = create_colormap(parse_cpt_string(CPT))
    assert cmap.name == "custom_cmap"
    assert cmap(0.0)[:3] == pytest.approx((0, 0, 0))
    assert cmap(1.0)[:3] == pytest.approx((1, 1, 1))


def test_read_file(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello")
    assert read_file(str(p)) == "hello"


# ---- color_map_validator
def test_colormap_validator_named():
    assert color_map_validator("viridis").name == "viridis"


def test_colormap_validator_cpt_string():
    assert color_map_validator(CPT).name == "custom_cmap"


def test_colormap_validator_cpt_file(tmp_path):
    p = tmp_path / "x.cpt"
    p.write_text(CPT)
    assert color_map_validator(str(p)).name == "custom_cmap"


def test_colormap_validator_textio(tmp_path):
    p = tmp_path / "x.cpt"
    p.write_text(CPT)
    with open(p) as f:
        assert color_map_validator(f).name == "custom_cmap"


def test_colormap_validator_invalid_type():
    with pytest.raises(InvalidColorMapFormat):
        color_map_validator(123)


def test_colormap_validator_unknown_name_returns_none():
    # Current behaviour: unknown name that is not a file falls through and returns None
    # (or raises ValueError depending on the matplotlib version).
    try:
        assert color_map_validator("definitely_not_a_cmap_xyz") is None
    except ValueError:
        pass


# ---- bbox_percent
def test_bbox_percent_globe_is_fraction():
    assert 0 < bbox_percent(90, -90, -90, 90) <= 1


def test_bbox_percent_zero_width():
    assert bbox_percent(10, -10, 5, 5) == 0


def test_bbox_percent_symmetry_and_scale():
    small = bbox_percent(10, 0, 0, 10)
    big = bbox_percent(20, 0, 0, 20)
    assert big > small
    assert bbox_percent(10, 0, 0, 10) == pytest.approx(bbox_percent(0, 10, 0, 10))


def test_bbox_percent_hemisphere_formula():
    # Northern hemisphere, half the longitude => 1/4 of globe area
    assert bbox_percent(90, 0, 0, 180) == pytest.approx(0.25)


def test_bbox_percent_wraps_dateline():
    assert bbox_percent(10, 0, 170, -170) == pytest.approx(bbox_percent(10, 0, 0, 20))


# ---- idx reader
def test_idx_reader_is_json():
    assert IDX_Reader._is_json('{"a": 1}')
    assert not IDX_Reader._is_json("not json")
    assert IDX_Reader([]) is not None


# ---- MapDataGenerator
def test_map_info_defaults():
    m = MapInfo()
    assert (m.smoothness, m.botlat, m.toplat, m.rightlon, m.leftlon) == (5, -90, 90, 180, -180)


def test_map_data_generator():
    g = MapDataGenerator(smoothness=2, botlat=0, toplat=10, rightlon=20, leftlon=10)
    lon, lat = g.griddedCoords
    assert lon.shape == lat.shape == (100, 100)
    assert lat.min() == 0 and lat.max() == 10
    assert lon.min() == 10 and lon.max() == 20
    assert g.data.shape == (100, 100)
    assert np.isfinite(g.data).all()


def test_map_data_generator_invalid_coords():
    with pytest.raises(InvalidCoordinates):
        MapDataGenerator(botlat=-100)


def test_map_data_regenerates():
    g = MapDataGenerator()
    first = g.data.copy()
    assert not np.array_equal(first, g._generate_random_data())


# ---- Variables catalog
@pytest.mark.parametrize("model", ["GFS", "ICON", "CMC/GEM", "CMC/GEPS"])
def test_catalog_files_exist_and_valid(model):
    import json, os
    params = catalog_path(model, "MERGED_PARAMS.json")
    levels = catalog_path(model, "VERTICAL_LEVELS.txt")
    assert os.path.isfile(params) and os.path.isfile(levels)
    data = json.load(open(params, encoding="utf-8"))
    assert data and all("levels" in v for v in data.values())
