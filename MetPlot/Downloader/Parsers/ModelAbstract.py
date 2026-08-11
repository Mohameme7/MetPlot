from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Selection:
    hours: list
    variables: list
    levels: list
    run: str
    subregion: list | None = None
    queue: object = None
    size_var: object = None
    run_date : str = None


class WeatherModel(ABC):
    @abstractmethod
    def build_urls(self, sel: Selection) -> list[str]: ...

    @abstractmethod
    def run_options(self) -> dict: ...

    @abstractmethod
    def forecast_hours(self, run_date, run) -> list: ...

    def postprocess(self, chunks: list[bytes]) -> list[bytes]:
        return chunks

    def estimate_size(self, urls: list[str], sel: Selection) -> int:
        return 0

    def finalize(self, filename: str, sel: Selection) -> None:
        pass

    def expected_count(self, sel: Selection) -> int:
        return len(self.build_urls(sel))