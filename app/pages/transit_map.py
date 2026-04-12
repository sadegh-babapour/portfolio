# app/pages/transit_map.py
# Live Calgary Transit map — Leaflet.js via NiceGUI ui.html
# Refreshes every 30 seconds, shows current + ghost positions,
# colours stale buses orange, supports route and quadrant filtering.

from nicegui import ui
from app.components.navbar import with_layout
from app.services.db import fetch_latest_vehicles, fetch_route_ids

QUADRANTS = ['All', 'NE', 'NW', 'SE', 'SW']

# Quadrant tint colours (marker fill)
QUADRANT_COLOURS = {
    'NE': '#4A90D9',   # blue
    'NW': '#7B68EE',   # purple
    'SE': '#50C878',   # green
    'SW': '#FF8C00',   # orange
}
STALE_COLOUR  = '#FF4444'   # red — same position as last fetch
DEFAULT_COLOUR = '#4A90D9'


def _vehicles_to_js(vehicles: list[dict]) -> str:
    """Serialise vehicle list to a JS array literal for Leaflet."""
    items = []
    for v in vehicles:
        colour = STALE_COLOUR if v['is_stale'] else QUADRANT_COLOURS.get(v['quadrant'], DEFAULT_COLOUR)
        prev = ''
        if v['prev_lat'] and v['prev_lon']:
            prev = f"[{v['prev_lat']},{v['prev_lon']}]"
        else:
            prev = 'null'
        label = f"Route {v['route_id'] or '?'} — Vehicle {v['vehicle_id']}"
        speed_kmh = round(v['speed'] * 3.6, 1) if v['speed'] else 0
        popup = (
            f"<b>{label}</b><br>"
            f"Speed: {speed_kmh} km/h<br>"
            f"Bearing: {v['bearing'] or '?'}°<br>"
            f"Quadrant: {v['quadrant'] or '?'}<br>"
            f"{'⚠️ Stale position' if v['is_stale'] else '✅ Moving'}"
        )
        items.append(
            f"{{lat:{v['lat']},lon:{v['lon']},"
            f"prev:{prev},"
            f"colour:'{colour}',"
            f"popup:{repr(popup)}}}"
        )
    return '[' + ','.join(items) + ']'


MAP_HTML = """
<div id="transit-map" style="width:100%;height:600px;border-radius:8px;"></div>
<script>
(function() {
  // Only initialise once
  if (window._transitMapReady) { return; }
  window._transitMapReady = true;

  var map = L.map('transit-map').setView([51.0447, -114.0719], 11);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 18
  }).addTo(map);

  window._transitMap     = map;
  window._transitMarkers = [];   // current position markers
  window._ghostMarkers   = [];   // previous position markers

  window.updateTransitMarkers = function(vehicles) {
    // Clear existing
    window._transitMarkers.forEach(function(m) { map.removeLayer(m); });
    window._ghostMarkers.forEach(function(m)   { map.removeLayer(m); });
    window._transitMarkers = [];
    window._ghostMarkers   = [];

    vehicles.forEach(function(v) {
      // Ghost dot (previous position)
      if (v.prev) {
        var ghost = L.circleMarker(v.prev, {
          radius: 5,
          fillColor: v.colour,
          color: v.colour,
          fillOpacity: 0.25,
          opacity: 0.25,
          weight: 1
        }).addTo(map);
        window._ghostMarkers.push(ghost);
      }

      // Current position marker
      var marker = L.circleMarker([v.lat, v.lon], {
        radius: 7,
        fillColor: v.colour,
        color: '#ffffff',
        fillOpacity: 0.9,
        opacity: 1,
        weight: 1.5
      }).bindPopup(v.popup).addTo(map);

      window._transitMarkers.push(marker);
    });
  };
})();
</script>
"""


@ui.page('/transit')
@with_layout
def transit_map_page():
    ui.page_title('Calgary Transit Live Map')

    # ── state ──────────────────────────────────────────────────────
    selected_route    = {'value': None}
    selected_quadrant = {'value': None}

    # ── header row ─────────────────────────────────────────────────
    with ui.row().classes('w-full items-center gap-4 px-4 pt-4'):
        ui.label('🚌 Calgary Transit — Live Map').classes('text-2xl font-bold flex-1')

        vehicle_count = ui.label('').classes('text-grey')

        # Route filter
        route_ids = fetch_route_ids()
        route_options = ['All routes'] + route_ids
        route_select = ui.select(
            options=route_options,
            value='All routes',
            label='Route',
        ).classes('w-36')

        # Quadrant filter
        quadrant_select = ui.select(
            options=QUADRANTS,
            value='All',
            label='Quadrant',
        ).classes('w-28')

    # ── legend ─────────────────────────────────────────────────────
    with ui.row().classes('gap-4 px-4 pb-2 items-center'):
        for quad, colour in QUADRANT_COLOURS.items():
            with ui.row().classes('items-center gap-1'):
                ui.html(f'<span style="display:inline-block;width:12px;height:12px;'
                        f'border-radius:50%;background:{colour};"></span>')
                ui.label(quad).classes('text-sm')
        with ui.row().classes('items-center gap-1'):
            ui.html(f'<span style="display:inline-block;width:12px;height:12px;'
                    f'border-radius:50%;background:{STALE_COLOUR};"></span>')
            ui.label('Stale / delayed').classes('text-sm')
        with ui.row().classes('items-center gap-1'):
            ui.html('<span style="display:inline-block;width:12px;height:12px;'
                    'border-radius:50%;background:#aaa;opacity:0.4;"></span>')
            ui.label('Ghost (prev position)').classes('text-sm')

    # ── map container ───────────────────────────────────────────────
    with ui.column().classes('w-full px-4 pb-4'):
        # Leaflet CSS + JS
        ui.html('<link rel="stylesheet" '
                'href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>')
        ui.html('<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>')

        map_element = ui.html(MAP_HTML).classes('w-full')

    # ── refresh function ────────────────────────────────────────────
    def refresh():
        route = route_select.value
        quad  = quadrant_select.value

        route_filter = None if route == 'All routes' else route
        quad_filter  = None if quad  == 'All'        else quad

        vehicles = fetch_latest_vehicles(
            route_id=route_filter,
            quadrant=quad_filter,
        )

        count = len(vehicles)
        vehicle_count.set_text(f'{count} vehicles')

        js_data = _vehicles_to_js(vehicles)
        ui.run_javascript(f'if(window.updateTransitMarkers) updateTransitMarkers({js_data});')

    # Wire filter changes to immediate refresh
    route_select.on('update:model-value', lambda _: refresh())
    quadrant_select.on('update:model-value', lambda _: refresh())

    # Auto-refresh every 30 seconds
    ui.timer(30.0, refresh)

    # Initial load
    refresh()