# Publishing the `service` layer through GeoServer

GeoServer's role here is **cartographic publishing** — base WMS layers for
context/overview maps, and standards-based WFS access for other GIS clients
(QGIS, ArcGIS, other web maps). The FastAPI backend remains the source of
truth for the app's actual "nearby search" logic (radius / nearest-N /
distance sort), because those are attribute+distance queries that are
easier and faster to run and cache in an app-tier endpoint than to express
purely as OGC filters. Use both together, not one instead of the other.

## 1. Create a workspace

Admin UI → **Data → Workspaces → Add new workspace**
- Name: `nearby`
- Namespace URI: `http://nearby.local/geoserver`

## 2. Create a PostGIS store

Admin UI → **Data → Stores → Add new Store → PostGIS**

| Field | Value |
|---|---|
| Workspace | `nearby` |
| Data Source Name | `services_db` |
| host | your PostGIS host |
| port | 5432 |
| database | `nearby_services` |
| schema | `public` |
| user / passwd | your credentials |
| Expose primary keys | ✅ enabled (needed for WFS-T if you ever allow edits) |

## 3. Publish the `service` layer

Admin UI → **Data → Layers → Add a new layer** → pick `services_db` → `service`

- **Declared SRS**: `EPSG:4326` (the `geom` column is `geography(Point,4326)`;
  GeoServer will read it correctly as long as the declared CRS matches)
- Compute the bounding box from data (native + lat/lon bbox → "Compute from data")
- **Enable CQL/ECQL filtering** on this layer so clients can filter by
  category without a custom endpoint, e.g.:

  ```
  https://<geoserver>/nearby/wms?service=WMS&version=1.1.0&request=GetMap
    &layers=nearby:service
    &cql_filter=category_code='hospital'
    &bbox=73.80,18.48,73.95,18.58&width=768&height=512&srs=EPSG:4326&format=image/png
  ```

- **WFS spatial filter (radius) example**, useful for external GIS clients
  that talk WFS 2.0 directly rather than the app API:

  ```
  https://<geoserver>/nearby/ows?service=WFS&version=2.0.0&request=GetFeature
    &typeNames=nearby:service
    &cql_filter=DWITHIN(geom, POINT(73.8636 18.5236), 2000, meters)
    AND category_code='pharmacy'
  ```

  Note: GeoServer's `DWITHIN` filter takes `(geometry, point, distance, unit)`
  in that order and works directly against the `geography` column.

## 4. Style with SLD (optional, for the WMS overview layer)

Give each category a distinct marker so a plain WMS overview map (e.g. for
embedding in a dashboard, or as a printable map) is legible without the
custom Leaflet UI. Create one SLD per category or a single rule-based SLD
keyed on `category_code`, e.g.:

```xml
<Rule>
  <Name>hospital</Name>
  <ogc:Filter>
    <ogc:PropertyIsEqualTo>
      <ogc:PropertyName>category_code</ogc:PropertyName>
      <ogc:Literal>hospital</ogc:Literal>
    </ogc:PropertyIsEqualTo>
  </ogc:Filter>
  <PointSymbolizer>
    <Graphic>
      <Mark><WellKnownName>cross</WellKnownName>
        <Fill><CssParameter name="fill">#FF5D5D</CssParameter></Fill>
      </Mark>
      <Size>10</Size>
    </Graphic>
  </PointSymbolizer>
</Rule>
```

Repeat with distinct WKN marks/colors for `pharmacy`, `police`, `atm`,
`school`, `fuel`, `park`, `other`.

## 5. Where GeoServer fits into the Leaflet frontend

Two integration options, not mutually exclusive:

**A. Base/overview WMS layer (recommended addition to `frontend/index.html`)**
Add a togglable overlay so users can see *all* published services at once,
independent of the app's search results:

```js
L.tileLayer.wms("https://<geoserver>/nearby/wms", {
  layers: "nearby:service",
  format: "image/png",
  transparent: true,
  version: "1.1.0"
}).addTo(map); // wire to a layer-control toggle
```

**B. WFS GetFeature as a fallback data source**
If the FastAPI backend is ever unavailable, the frontend could fall back to
querying GeoServer's WFS directly with a bbox or CQL filter and computing
distance client-side. This is slower and duplicates logic, so treat it as
a degraded-mode fallback, not the primary path.

## 6. Access control

- Expose only `GetMap`/`GetFeature` (read) on the `nearby:service` layer to
  anonymous/public roles; keep the store's write credentials restricted to
  an admin role, since the FastAPI backend is currently read-only against
  this schema too (no WFS-T/editing is enabled by default in this setup).
- Put GeoServer behind the same reverse proxy/TLS termination as the rest
  of the stack; don't expose the raw 8080 admin console publicly.
