# # app/pages/transit_map_v2.py
# import asyncio
# import random
# from nicegui import ui
# from app.components.navbar import with_layout
# from app.services.db import fetch_latest_vehicles, fetch_route_ids

# QUADRANTS = ['All', 'NE', 'NW', 'SE', 'SW']

# QUADRANT_COLOURS = {
#     'NE': '#4A90D9',
#     'NW': '#A78BFA',
#     'SE': '#34D399',
#     'SW': '#FB923C',
# }
# STALE_COLOUR   = '#F87171'
# DEFAULT_COLOUR = '#4A90D9'

# TILE_DARK  = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
# TILE_LIGHT = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'
# TILE_ATTRIBUTION = '© OpenStreetMap contributors © CARTO'


# def _colour(v: dict) -> str:
#     if v['is_stale']:
#         return STALE_COLOUR
#     return QUADRANT_COLOURS.get(v['quadrant'], DEFAULT_COLOUR)


# @ui.page('/transitv2')
# @with_layout
# def transit_map_v2_page():
#     ui.page_title('Calgary Transit Live Map v2')

#     current_layers = []
#     dark_mode      = {'on': True}
#     # holds the current sample of 5 vehicle_ids
#     tracked_ids    = {'ids': []}

#     # ── header ─────────────────────────────────────────────────────
#     with ui.row().classes('w-full items-center gap-4 px-4 pt-4 flex-wrap'):
#         ui.label('🚌 Calgary Transit — Live Map').classes('text-2xl font-bold flex-1')
#         vehicle_count = ui.label('').classes('text-grey')
#         map_toggle = ui.button('☀️ Light map').classes('ml-2')

#     # ── controls row ───────────────────────────────────────────────
#     with ui.row().classes('w-full items-center gap-4 px-4 pb-2 flex-wrap'):
#         quadrant_select = ui.select(
#             options=QUADRANTS,
#             value='All',
#             label='Quadrant',
#         ).classes('w-28')

#         route_ids    = fetch_route_ids()
#         route_select = ui.select(
#             options=['All routes'] + route_ids,
#             value='All routes',
#             label='Route',
#         ).classes('w-36')

#         # vehicle picker — populated after first fetch
#         vehicle_select = ui.select(
#             options=[],
#             value=None,
#             label='Pick a bus',
#             clearable=True,
#         ).classes('w-48')

#         resample_btn = ui.button('🔀 New sample').classes('ml-2')

#     # ── legend ─────────────────────────────────────────────────────
#     with ui.row().classes('gap-4 px-4 pb-2 items-center flex-wrap'):
#         for quad, colour in QUADRANT_COLOURS.items():
#             with ui.row().classes('items-center gap-1'):
#                 ui.html(f'<span style="display:inline-block;width:12px;height:12px;'
#                         f'border-radius:50%;background:{colour}"></span>')
#                 ui.label(quad).classes('text-sm')
#         with ui.row().classes('items-center gap-1'):
#             ui.html(f'<span style="display:inline-block;width:12px;height:12px;'
#                     f'border-radius:50%;background:{STALE_COLOUR}"></span>')
#             ui.label('Stale / delayed').classes('text-sm')
#         with ui.row().classes('items-center gap-1'):
#             ui.html('<span style="display:inline-block;width:12px;height:12px;'
#                     'border-radius:50%;background:#aaa;opacity:0.35"></span>')
#             ui.label('Ghost (prev position)').classes('text-sm')

#     # ── map ────────────────────────────────────────────────────────
#     m = ui.leaflet(
#         center=(51.0447, -114.0719),
#         zoom=11,
#     ).classes('w-full').style('height:640px')

#     m.clear_layers()
#     tile_layer_state = {
#         'layer': m.tile_layer(
#             url_template=TILE_DARK,
#             options={'attribution': TILE_ATTRIBUTION, 'maxZoom': 19, 'subdomains': 'abcd'},
#         )
#     }

#     # ── tile toggle ────────────────────────────────────────────────
#     def toggle_map_style():
#         if tile_layer_state['layer']:
#             m.remove_layer(tile_layer_state['layer'])
#         if dark_mode['on']:
#             tile_layer_state['layer'] = m.tile_layer(
#                 url_template=TILE_LIGHT,
#                 options={'attribution': TILE_ATTRIBUTION, 'maxZoom': 19, 'subdomains': 'abcd'},
#             )
#             dark_mode['on'] = False
#             map_toggle.set_text('🌙 Dark map')
#         else:
#             tile_layer_state['layer'] = m.tile_layer(
#                 url_template=TILE_DARK,
#                 options={'attribution': TILE_ATTRIBUTION, 'maxZoom': 19, 'subdomains': 'abcd'},
#             )
#             dark_mode['on'] = True
#             map_toggle.set_text('☀️ Light map')

#     map_toggle.on('click', lambda _: toggle_map_style())

#     # ── refresh ────────────────────────────────────────────────────
#     async def refresh(resample: bool = False):
#         loop = asyncio.get_event_loop()

#         route = route_select.value
#         quad  = quadrant_select.value

#         # fetch all matching vehicles in thread pool
#         all_vehicles = await loop.run_in_executor(
#             None,
#             lambda: fetch_latest_vehicles(
#                 route_id=None if route == 'All routes' else route,
#                 quadrant=None if quad  == 'All'        else quad,
#             )
#         )

#         if not all_vehicles:
#             vehicle_count.set_text('0 vehicles')
#             return

#         # update vehicle picker options (vehicle IDs)
#         all_ids = [v['vehicle_id'] for v in all_vehicles]

#         # pick sample of 5 — resample or keep existing if still valid
#         if resample or not tracked_ids['ids']:
#             tracked_ids['ids'] = random.sample(all_ids, min(5, len(all_ids)))
#             vehicle_select.options = tracked_ids['ids']
#             vehicle_select.value   = None
#             vehicle_select.update()

#         # if user picked a specific bus, show just that one
#         if vehicle_select.value:
#             display = [v for v in all_vehicles if v['vehicle_id'] == vehicle_select.value]
#         else:
#             display = [v for v in all_vehicles if v['vehicle_id'] in tracked_ids['ids']]

#         vehicle_count.set_text(f'{len(all_vehicles)} total · showing {len(display)}')

#         # clear old layers then redraw
#         for layer in current_layers:
#             m.remove_layer(layer)
#         current_layers.clear()

#         for v in display:
#             colour    = _colour(v)
#             speed_kmh = round(v['speed'] * 3.6, 1) if v['speed'] else 0
#             tooltip   = (
#                 f"Route {v['route_id'] or '?'} | "
#                 f"Vehicle {v['vehicle_id']} | "
#                 f"{speed_kmh} km/h | "
#                 f"{'⚠️ Stale' if v['is_stale'] else '✅ Moving'}"
#             )

#             # ghost dot
#             if v['prev_lat'] and v['prev_lon']:
#                 ghost = m.generic_layer(
#                     name='circleMarker',
#                     args=[
#                         [v['prev_lat'], v['prev_lon']],
#                         {'radius': 5, 'color': colour, 'fillColor': colour,
#                          'fillOpacity': 0.25, 'opacity': 0.25, 'weight': 1},
#                     ],
#                 )
#                 current_layers.append(ghost)

#             # current dot
#             dot = m.generic_layer(
#                 name='circleMarker',
#                 args=[
#                     [v['lat'], v['lon']],
#                     {'radius': 8, 'color': 'white', 'fillColor': colour,
#                      'fillOpacity': 0.95, 'opacity': 1, 'weight': 2},
#                 ],
#             )
#             dot.run_method('bindTooltip', tooltip, {'permanent': False, 'sticky': True})
#             current_layers.append(dot)

#     route_select.on('update:model-value',    lambda _: asyncio.ensure_future(refresh(resample=True)))
#     quadrant_select.on('update:model-value', lambda _: asyncio.ensure_future(refresh(resample=True)))
#     vehicle_select.on('update:model-value',  lambda _: asyncio.ensure_future(refresh()))
#     resample_btn.on('click',                 lambda _: asyncio.ensure_future(refresh(resample=True)))
#     ui.timer(30.0, refresh)
#     ui.timer(1.5, lambda: asyncio.ensure_future(refresh()), once=True)