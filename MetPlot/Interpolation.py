import os
import pygrib
from concurrent.futures import ThreadPoolExecutor, as_completed

class GribInterpolator:
    def __init__(self, file_path, output_file):
        self.file_path = file_path
        self.output_file = output_file

    def __enter__(self):
        """Open the GRIB file when entering the context and gets data."""
        self.grbs = pygrib.open(self.file_path)
        self.variables_levels = self._get_variables_levels()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Closes file"""
        self.grbs.close()

    def _get_variables_levels(self):
        """Extract available variables, levels, and their forecast steps."""
        variables_levels = {}
        for grb in self.grbs:
            key = (grb.name, grb.level)
            variables_levels.setdefault(key, []).append(grb.forecastTime)
        return {key: sorted(steps) for key, steps in variables_levels.items()}

    def _find_missing_steps(self, steps):
        """Identify gaps in forecast steps."""
        all_steps = list(range(min(steps), max(steps) + 1))
        return [step for step in all_steps if step not in steps]

    def _interpolate_data(self, var, level, steps):
        """Perform linear interpolation to fill missing forecast steps, not the best option always but its fine and fast"""
        interpolated = {}
        missing_steps = self._find_missing_steps(steps)
        print(missing_steps)
        for step in missing_steps:
            lower_step = max([s for s in steps if s < step], default=None)
            upper_step = min([s for s in steps if s > step], default=None)

            if lower_step is None or upper_step is None:

                continue

            start_grb = self.grbs.select(name=var, level=level, forecastTime=lower_step)[0]
            end_grb = self.grbs.select(name=var, level=level, forecastTime=upper_step)[0]

            ratio = (step - lower_step) / (upper_step - lower_step)
            interpolated[step] = start_grb.values + (end_grb.values - start_grb.values) * ratio
            print(f"Interpolated {step}")
        return var, level, interpolated

    def run_interpolation(self) -> dict:
        """Perform interpolation using multi-threading.
        :returns Interpolated Data as dict
        """
        interpolated_values = {}
        with ThreadPoolExecutor(max_workers=os.cpu_count() + 1) as executor:
            futures = {
                executor.submit(self._interpolate_data, var, level, steps): (var, level)
                for (var, level), steps in self.variables_levels.items()
            }

            for future in as_completed(futures):
                var, level = futures[future]
                var, level, data = future.result()
                if data:
                    interpolated_values.setdefault(var, {})[level] = data


        return interpolated_values

    def merge_to_grib(self, interpolated_values):
        """Merge interpolated data with the original GRIB file."""
        with open(self.output_file, 'wb') as out_file:
            written_steps = set()

            with pygrib.open(self.file_path) as grbs:
                for grb in grbs:
                    out_file.write(grb.tostring())
                    key = (grb.name, grb.level, grb.forecastTime)
                    written_steps.add(key)

            for var, levels in interpolated_values.items():
                for level, steps in levels.items():
                    for step, data in steps.items():
                        key = (var, level, step)
                        if key not in written_steps:
                            template_grb = self.grbs.select(name=var, level=level)[0]
                            new_grb = self._create_grib_message(template_grb, step, data)
                            out_file.write(new_grb.tostring())

    def _create_grib_message(self, grb, step, data):
        """Create a new GRIB message using the template of an existing message."""
        new_grb = pygrib.fromstring(grb.tostring())

        new_grb['forecastTime'] = step # This may vary from model to model, I'll try to find a dynamic solution later
        new_grb['values'] = data
        new_grb.packingType = 'grid_simple'  # To avoid excessive file sizes

        return new_grb


