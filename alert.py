#!/usr/bin/env python3
import sys
import math
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


ATOM_NS = "http://www.w3.org/2005/Atom"
GEORSS_NS = "http://www.georss.org/georss"
CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"
KML_NS = "http://www.opengis.net/kml/2.2"


NS = {"atom": ATOM_NS, "georss": GEORSS_NS, "cap": CAP_NS}


FEED_URL = "https://api.weather.gov/alerts/active.atom"


# Map CAP severity → icon color
SEVERITY_ICON = {
    "Extreme": "http://maps.google.com/mapfiles/kml/paddle/red-circle.png",
    "Severe": "http://maps.google.com/mapfiles/kml/paddle/red-circle.png",
    "Moderate": "http://maps.google.com/mapfiles/kml/paddle/ylw-circle.png",
    "Minor": "http://maps.google.com/mapfiles/kml/paddle/grn-circle.png",
}
DEFAULT_ICON = "http://maps.google.com/mapfiles/kml/paddle/wht-circle.png"




def http_get(url: str, timeout=30) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CAP-KML/1.0 (+https://github.com/jeandeauxmail-cell/alertstest)",
            "Accept": "application/atom+xml,application/xml,text/xml",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()




def polygon_centroid(latlons):
    """Return centroid (lat, lon) of a polygon given list of (lat, lon). Uses planar approx.
    If area ~ 0, falls back to mean of vertices.
    """
    if not latlons:
        return None
    # Convert to (x=lon, y=lat)
    pts = [(p[1], p[0]) for p in latlons]
    a = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a) < 1e-9:
        # Degenerate → mean
        lat = sum(p[0] for p in latlons) / len(latlons)
        lon = sum(p[1] for p in latlons) / len(latlons)
        return (lat, lon)
    a *= 0.5
    cx /= (6 * a)
    cy /= (6 * a)
    # back to (lat, lon) = (y, x)
    return (cy, cx)

def parse_point_from_entry(entry: ET.Element):
    # Prefer georss:point
    p = entry.find("georss:point", NS)
    if p is not None and p.text:
        try:
            lat_str, lon_str = p.text.strip().split()
            return (float(lat_str), float(lon_str))
        except Exception:
            pass
    # Else try georss:polygon centroid
    poly = entry.find("georss:polygon", NS)
    if poly is not None and poly.text:
        nums = poly.text.strip().split()
        try:
            coords = [(float(nums[i]), float(nums[i + 1])) for i in range(0, len(nums), 2)]
            return polygon_centroid(coords)
        except Exception:
            pass
    return None
def text_of(el: ET.Element, path: str) -> str:
    node = el.find(path, NS)
    return node.text.strip() if node is not None and node.text else ""

def build_kml(entries):
    ET.register_namespace("", KML_NS)
    kml = ET.Element(ET.QName(KML_NS, "kml"))
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = "NOAA Active Alerts (Points)"
    for sev, icon in {**SEVERITY_ICON, "Unknown": DEFAULT_ICON}.items():
        sid = f"sev_{sev.lower()}"
        st = ET.SubElement(doc, "Style", id=sid)
        istyle = ET.SubElement(st, "IconStyle")
        ET.SubElement(istyle, "scale").text = "1.2"
        icon_el = ET.SubElement(istyle, "Icon")
        ET.SubElement(icon_el, "href").text = icon
        lstyle = ET.SubElement(st, "LabelStyle")
        ET.SubElement(lstyle, "scale").text = "0.9"


# Balloon template (uses ExtendedData)
    bst = ET.SubElement(doc, "Style", id="balloon")
    b = ET.SubElement(bst, "BalloonStyle")
    b.text = (
        "<![CDATA["
        "<div style='font-family:Arial, sans-serif;'>"
        "<h3>$[name]</h3>"
        "<p><b>Event:</b> $[ext_event]</p>"
        "<p><b>Severity:</b> $[ext_severity] &nbsp; <b>Urgency:</b> $[ext_urgency] &nbsp; <b>Certainty:</b> $[ext_certainty]</p>"
        "<p><b>Effective:</b> $[ext_effective]<br/>"
        "<b>Expires:</b> $[ext_expires]</p>"
        "<p><b>Areas:</b> $[ext_areaDesc]</p>"
        "<p><b>Description</b><br/>$[ext_description]</p>"
        "<p><b>Instruction</b><br/>$[ext_instruction]</p>"
        "<p><a href='$[ext_id]' target='_blank'>Alert Link</a></p>"
        "</div>"
        "]]>"
    )
    for e in entries:
        pt = e["point"]
        sev = e.get("severity") or "Unknown"
        style_url = f"#sev_{sev.lower()}"
        
        
        pm = ET.SubElement(doc, "Placemark")
        ET.SubElement(pm, "name").text = e.get("title") or e.get("event") or "Alert"
        ET.SubElement(pm, "styleUrl").text = style_url
        # Pair with balloon style via StyleMap (inline)
        sm = ET.SubElement(pm, "Style")
        ET.SubElement(sm, "BalloonStyle") # presence triggers use of document balloon style
        ET.SubElement(pm, "Snippet").text = e.get("headline") or e.get("summary") or ""
        
        
        ext = ET.SubElement(pm, "ExtendedData")
        def add_data(name, value):
            d = ET.SubElement(ext, "Data", name=name)
            ET.SubElement(d, "value").text = value or ""
        
        
        add_data("ext_event", e.get("event"))
        add_data("ext_severity", e.get("severity"))
        add_data("ext_urgency", e.get("urgency"))
        add_data("ext_certainty", e.get("certainty"))
        add_data("ext_effective", e.get("effective"))
        add_data("ext_expires", e.get("expires"))
        add_data("ext_areaDesc", e.get("areaDesc"))
        add_data("ext_description", e.get("description"))
        add_data("ext_instruction", e.get("instruction"))
        add_data("ext_id", e.get("id"))
        
        
        pt_el = ET.SubElement(pm, "Point")
        ET.SubElement(pt_el, "coordinates").text = f"{pt[1]},{pt[0]},0"
        
        
    return ET.ElementTree(kml)

def main(out_path: str):
    raw = http_get(FEED_URL)
    root = ET.fromstring(raw)
    entries_xml = root.findall("atom:entry", NS)
    
    
    entries = []
    for entry in entries_xml:
        point = parse_point_from_entry(entry)
        if not point:
            continue # skip if we can't place it
        data = {
            "point": point,
            "id": text_of(entry, "atom:id"),
            "title": text_of(entry, "atom:title"),
            "updated": text_of(entry, "atom:updated"),
            "summary": text_of(entry, "atom:summary"),
            # CAP fields
            "event": text_of(entry, "cap:event"),
            "effective": text_of(entry, "cap:effective"),
            "expires": text_of(entry, "cap:expires"),
            "urgency": text_of(entry, "cap:urgency"),
            "severity": text_of(entry, "cap:severity"),
            "certainty": text_of(entry, "cap:certainty"),
            "areaDesc": text_of(entry, "cap:areaDesc"),
            "headline": text_of(entry, "cap:headline"),
            "description": text_of(entry, "cap:description"),
            "instruction": text_of(entry, "cap:instruction"),
        }
        entries.append(data)
        
    kml_tree = build_kml(entries)

    # Pretty-print
    ET.indent(kml_tree, space=" ", level=0)
    kml_tree.write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {out_path} with {len(entries)} placemarks", file=sys.stderr)

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "site/alerts.kml"
    main(out)
