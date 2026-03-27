from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class DetectedBox:
    cls: int
    conf: float
    xyxy: tuple[float, float, float, float]

    @property
    def center(self) -> Point2D:
        x1, y1, x2, y2 = self.xyxy
        return Point2D((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.xyxy
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    @property
    def width(self) -> float:
        x1, _, x2, _ = self.xyxy
        return max(0.0, x2 - x1)

    @property
    def height(self) -> float:
        _, y1, _, y2 = self.xyxy
        return max(0.0, y2 - y1)

    @property
    def aspect_ratio(self) -> float:
        h = max(1.0, self.height)
        return self.width / h