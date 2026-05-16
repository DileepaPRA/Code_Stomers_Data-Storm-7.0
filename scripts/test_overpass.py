import requests

query = """
[out:json][timeout:30];
(
  node["amenity"="school"](6.8,79.8,7.0,80.0);
  way["amenity"="school"](6.8,79.8,7.0,80.0);
);
out center;
"""

resp = requests.post("https://overpass-api.de/api/interpreter", data={"data": query}, timeout=30)
print(f"Status: {resp.status_code}")
data = resp.json()
elems = data.get("elements", [])
print(f"Elements: {len(elems)}")
if elems:
    print(f"Sample: {elems[0]}")
