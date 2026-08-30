import math
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def compute_summary(points):
    if not points:
        return {"distance_km": 0.0, "duration_min": 0.0, "avg_speed_kmh": 0.0}
    distance_m = 0.0
    for a, b in zip(points, points[1:]):
        distance_m += haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
    t0 = datetime.fromisoformat(points[0]["time"])
    t1 = datetime.fromisoformat(points[-1]["time"])
    duration_min = max((t1 - t0).total_seconds() / 60, 0.0)
    avg_speed_kmh = (distance_m / 1000) / (duration_min / 60) if duration_min > 0 else 0.0
    return {
        "distance_km": round(distance_m / 1000, 2),
        "duration_min": round(duration_min, 1),
        "avg_speed_kmh": round(avg_speed_kmh, 1),
    }


def build_kml(points, title):
    coords_line = " ".join(f"{p['lon']},{p['lat']},0" for p in points)
    placemarks = []
    for p in points:
        desc = f"Ora: {p['time']}<br/>Viteza: {p['speed_kmh']} km/h<br/>Precizie: {p['accuracy']} m"
        placemarks.append(f"""
    <Placemark>
      <name>{escape(p['time'])}</name>
      <description>{escape(desc)}</description>
      <Point><coordinates>{p['lon']},{p['lat']},0</coordinates></Point>
    </Placemark>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{escape(title)}</name>
    <Style id="track">
      <LineStyle><color>ff0000ff</color><width>4</width></LineStyle>
    </Style>
    <Placemark>
      <name>Traseu</name>
      <styleUrl>#track</styleUrl>
      <LineString>
        <tessellate>1</tessellate>
        <coordinates>{coords_line}</coordinates>
      </LineString>
    </Placemark>{''.join(placemarks)}
  </Document>
</kml>"""


def export_kmz(points, out_path, title):
    kml_str = build_kml(points, title)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml_str)
    return out_path
