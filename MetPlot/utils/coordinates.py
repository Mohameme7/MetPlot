import math

def bbox_percent(top, bottom, left, right) -> float:
    """Calculate how much percent a bounding box takes of the globe"""

    R = 6371
    lat1 = math.radians(top)
    lat2 = math.radians(bottom)
    lon1 = math.radians(left)
    lon2 = math.radians(right)
    dlon = (lon2 - lon1) % (2 * math.pi)
    if dlon > math.pi:
        dlon = 2 * math.pi - dlon
    area_box = (R**2) * dlon * abs(math.sin(lat1) - math.sin(lat2))
    area_earth = 4 * math.pi * (R**2)
    return (area_box / area_earth * 100)/100