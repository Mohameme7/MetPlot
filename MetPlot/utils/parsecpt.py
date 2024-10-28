import matplotlib.colors as mcolors
import io


def read_file(file):
       return open(file, 'r').read()


def parse_cpt_string(cpt_string):
    """Parses the CPT Content and returns the colors"""
    cpt_colors = []
    cpt_file = io.StringIO(cpt_string)

    for line in cpt_file:
        if line.startswith('#') or not line.strip():
            continue
        parts = line.split()
        if len(parts) == 8:
            pos1, r1, g1, b1, pos2, r2, g2, b2 = map(float, parts)
            cpt_colors.append((pos1 / 100, (r1 / 255, g1 / 255, b1 / 255)))
            cpt_colors.append((pos2 / 100, (r2 / 255, g2 / 255, b2 / 255)))

    cpt_colors = sorted(set(cpt_colors), key=lambda x: x[0])

    if cpt_colors:
        first_pos = cpt_colors[0][0]
        last_pos = cpt_colors[-1][0]

        normalized_colors = [
            ((pos - first_pos) / (last_pos - first_pos), color) for pos, color in cpt_colors]
        return normalized_colors

    return []


def create_colormap(cpt_colors):
    """Creates a colormap for matplotlib from parsed CPT colors"""
    positions = [c[0] for c in cpt_colors]
    rgb_colors = [c[1] for c in cpt_colors]
    cmap = mcolors.LinearSegmentedColormap.from_list('custom_cmap', list(zip(positions, rgb_colors)))
    return cmap


