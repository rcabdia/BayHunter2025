# pip install cartopy matplotlib
from typing import Any, Dict, Iterable, List, Optional, Tuple
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import pandas as pd

class PolygonGeoHelper:
    """
    Helper to:
      - store a polygon (lon, lat)
      - test if points are inside (edge-inclusive)
      - filter dicts where value[list[lon_index], list[lat_index]] is a point
      - plot polygon + optional points using Cartopy
    """

    def __init__(self,
                 polygon: List[Tuple[float, float]],
                 lon_index: int = 2,
                 lat_index: int = 3):
        if len(polygon) < 3:
            raise ValueError("polygon must have at least 3 vertices.")
        self.polygon = polygon  # list[(lon, lat)] in CW or CCW order
        self.lon_index = lon_index
        self.lat_index = lat_index

    # ----------------- Geometry -----------------
    @staticmethod
    def _point_on_segment(px: float, py: float,
                          x1: float, y1: float,
                          x2: float, y2: float,
                          eps: float = 1e-12) -> bool:
        # cross product for collinearity
        cross = (py - y1) * (x2 - x1) - (px - x1) * (y2 - y1)
        if abs(cross) > eps:
            return False
        # within bounding box via dot product trick
        dot = (px - x1) * (px - x2) + (py - y1) * (py - y2)
        return dot <= eps

    def point_in_polygon(self, lon: float, lat: float) -> bool:
        """Ray-casting with edge-inclusive check."""
        poly = self.polygon
        n = len(poly)
        inside = False

        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]

            # Edge inclusive
            if self._point_on_segment(lon, lat, x1, y1, x2, y2):
                return True

            # Ray casting
            if (y1 > lat) != (y2 > lat):
                x_at_y = x1 + (x2 - x1) * (lat - y1) / (y2 - y1)
                if x_at_y >= lon:
                    inside = not inside
        return inside

    # ----------------- Data filtering -----------------
    def filter_dict(self,
                    data: Dict[Any, List[Any]],
                    skip_invalid: bool = True) -> Dict[Any, List[Any]]:
        """
        Keep only items whose (lon,lat) at [lon_index],[lat_index] lie inside polygon.
        """
        out = {}
        for k, vals in data.items():
            try:
                lon = float(vals[self.lon_index])
                lat = float(vals[self.lat_index])
            except Exception as e:
                if skip_invalid:
                    continue
                raise ValueError(f"Invalid coordinates for key {k}: {e}")

            if self.point_in_polygon(lon, lat):
                out[k] = vals
        return out

    # ----------------- Plotting (Cartopy) -----------------
    def _smart_extent(self,
                      lons: List[float],
                      lats: List[float],
                      pad: float,
                      central_longitude: float) -> Tuple[float, float, float, float]:
        """Extent with basic anti-meridian handling."""
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)
        span = max_lon - min_lon
        if span > 180:
            pivot = central_longitude
            shifted = [(((lon - pivot + 540) % 360) - 180) for lon in lons]
            min_s, max_s = min(shifted), max(shifted)
            min_lon = ((min_s + pivot + 540) % 360) - 180
            max_lon = ((max_s + pivot + 540) % 360) - 180
        return (min_lon - pad, max_lon + pad, min_lat - pad, max_lat + pad)

    def plot(self,
             points: Optional[Iterable[Tuple[float, float]]] = None,
             classify_points: bool = True,
             title: str = "Polygon",
             extent_pad_deg: float = 0.5,
             central_longitude: float = 0.0,
             figsize: Tuple[int, int] = (8, 6),
             stations: str = None) -> None:

        """
        Plot the polygon and (optional) points using Cartopy PlateCarree.
        - If classify_points=True, points inside are marked with 'o', outside with 'x'.
        """
        lons = [p[0] for p in self.polygon]
        lats = [p[1] for p in self.polygon]
        if stations:
            df = pd.read_csv(stations, sep=";")
        proj = ccrs.PlateCarree(central_longitude=central_longitude)
        fig = plt.figure(figsize=figsize)
        ax = plt.axes(projection=proj)

        # Map features
        ax.add_feature(cfeature.LAND, zorder=0, edgecolor='none', alpha=0.3)
        ax.add_feature(cfeature.OCEAN, zorder=0, edgecolor='none', alpha=0.3)
        ax.add_feature(cfeature.COASTLINE, linewidth=0.5, alpha=0.6)
        ax.add_feature(cfeature.BORDERS, linewidth=0.4, linestyle=":", alpha=0.5)
        gl = ax.gridlines(draw_labels=True, linewidth=0.4, alpha=0.5)
        gl.top_labels = gl.right_labels = False

        xmin, xmax, ymin, ymax = self._smart_extent(
            lons, lats, extent_pad_deg, central_longitude
        )
        ax.set_extent((xmin, xmax, ymin, ymax), crs=ccrs.PlateCarree())

        # Polygon (close the loop)
        ax.plot(lons + [lons[0]], lats + [lats[0]],
                transform=ccrs.PlateCarree(), linewidth=2)
        ax.scatter(lons, lats, transform=ccrs.PlateCarree(), s=30, zorder=3)
        if stations:
            ax.scatter(df['longitude'], df['latitude'], transform=ccrs.PlateCarree(), edgecolors="black",
                       linewidths=0.75, marker="^")
        # Label vertices 1..N
        for i, (x, y) in enumerate(self.polygon, start=1):
            ax.text(x, y, f"{i}", transform=ccrs.PlateCarree(),
                    fontsize=9, ha="left", va="bottom")

        # Overlay points
        if points is not None:
            pts = list(points)
            if classify_points:
                inside, outside = [], []
                for (x, y) in pts:
                    (inside if self.point_in_polygon(x, y) else outside).append((x, y))

                if inside:
                    ax.scatter([x for x, _ in inside], [y for _, y in inside],
                               transform=ccrs.PlateCarree(), s=22, marker="o", label="inside")
                if outside:
                    ax.scatter([x for x, _ in outside], [y for _, y in outside],
                               transform=ccrs.PlateCarree(), s=22, marker="x", label="outside")
                ax.legend(loc="lower left")
            else:
                ax.scatter([x for x, _ in pts], [y for _, y in pts],
                           transform=ccrs.PlateCarree(), s=22, marker="o")

        ax.set_title(title)
        plt.tight_layout()
        plt.show()


# ----------------- Example usage -----------------
if __name__ == "__main__":
    # Define your polygon (lon, lat) in order (no need to repeat first point)
    stations = "/Users/roberto/Documents/sismologia/BayHunter/data/upflow.txt"


    # full dataset
    trapezoid_pts = [
        (-33.50, 41.00),  # top-left
        (-22.00, 41.00),  # top-right
        (-7.50, 32.50),  # bottom-right
        (-7.50, 26.50),
        (-19.00, 26.50),
        (-20.00, 29.50),
        (-33.50, 37.00) # bottom-left
    ]



    helper = PolygonGeoHelper(trapezoid_pts, lon_index=2, lat_index=3)

    # Sample dict with coordinates at [2]=lon, [3]=lat
    places = {
        "A": ["foo", 123, -3.705, 40.418],
        "B": ["bar", 456,  2.352, 48.857],
        "C": ["baz", 789, -0.127, 51.507],
        "D": ["qux", 111, -3.703, 40.415],
    }

    inside_only = helper.filter_dict(places)
    print("Filtered keys:", list(inside_only.keys()))

    # Optional: plot with some points
    test_points = [(v[2], v[3]) for v in places.values()]
    helper.plot(points=test_points,
                classify_points=True,
                title="Polygon & Points (inside vs outside)",
                extent_pad_deg=0.2, stations=stations)
