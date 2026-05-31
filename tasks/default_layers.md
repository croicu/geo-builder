# Default Layers

## Problem Statement

Currently the layers when the aread designer creates a new area are not reflecting the activities during a trip, they are mixed up:
```
    {
      "type": "circle",
      "visible": true,
      "style": {
        "opacity": 0.3,
        "color": "#007f00",
        "surface": true
      },
      "acquisition": {
        "provider": "overpass",
        "filter": "leisure",
        "values": ["park"]
      }
    },
    {
      "type": "heatmap",
      "visible": true,
      "style": {},
      "acquisition": {
        "provider": "overpass",
        "filter": "amenity",
        "values": ["sustenance", "entertainment"]
      }
    },
    {
      "type": "heatmap",
      "visible": true,
      "style": {
        "scale": 3.0, 
        "color": "#ffff00"  
      },
      "acquisition": {
        "provider": "overpass",
        "filter": "historic",
        "values": ["monuments", "memorials"]
      }
    },
```

## Proposed new structure
- Introduce a layer name in template.json the will be the name of the created layer.
- To facilitate switching between layers according to the current activity during the trip, create the following default layers when a new area is defined:
  - Layer 1 - Name: Restaurants/Food: Color: #C41C3B (deep crimson red)
  - Layer 2 - Name: Attractions/Tourism: Color: #6A0DAD (dark purple)
  - Layer 3 - Name: Shops/Services: Color: #004B87 (navy blue)
  - Layer 4 - Name: Culture/Entertainment: Color: #D4AF37 (bold gold)
- Adjust the overpass queries to get the associated geo coordinates for the layers.
  
The designer has the ability to define any other custom layer by dirctly editting the json file.