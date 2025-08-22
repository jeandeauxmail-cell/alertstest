import requests
import xml.etree.ElementTree as ET

def fetch_alerts():
    url = "https://api.weather.gov/alerts/active.atom"
    response = requests.get(url)
    return response.content

def parse_alerts(xml_data):
    root = ET.fromstring(xml_data)
    alerts = []
    
    for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
        title = entry.find('{http://www.w3.org/2005/Atom}title').text
        summary = entry.find('{http://www.w3.org/2005/Atom}summary').text
        point = entry.find('{http://www.w3.org/2005/Atom}georss:point')
        
        if point is not None:
            lat, lon = point.text.split()
            alerts.append({
                'title': title,
                'summary': summary,
                'coordinates': (lon, lat)  # KML uses (lon, lat)
            })
    
    return alerts

def create_kml(alerts):
    kml = ['<?xml version="1.0" encoding="UTF-8"?>']
    kml.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
    kml.append('<Document>')
    
    for alert in alerts:
        kml.append('<Placemark>')
        kml.append(f'<name>{alert["title"]}</name>')
        kml.append(f'<description>{alert["summary"]}</description>')
        kml.append('<Point>')
        kml.append(f'<coordinates>{alert["coordinates"][0]},{alert["coordinates"][1]}</coordinates>')
        kml.append('</Point>')
        kml.append('</Placemark>')
    
    kml.append('</Document>')
    kml.append('</kml>')
    
    return '\n'.join(kml)

def main():
    xml_data = fetch_alerts()
    alerts = parse_alerts(xml_data)
    kml_data = create_kml(alerts)
    
    with open('alerts.kml', 'w') as f:
        f.write(kml_data)

if __name__ == "__main__":
    main()
