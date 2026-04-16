# # app/pages/transit_map.py
# import asyncio
# import random
# from nicegui import ui
# from app.components.navbar import with_layout
# from app.services.db import fetch_latest_vehicles, fetch_route_ids
# from app.services import poller as poller_service

# QUADRANTS_FILTER = ['All', 'NE', 'NW', 'SE', 'SW']

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

# MAX_PER_QUADRANT = 5


# def _colour(v: dict) -> str:
#     if v['is_stale']:
#         return STALE_COLOUR
#     return QUADRANT_COLOURS.get(v['quadrant'], DEFAULT_COLOUR)


# def _sample_vehicles(vehicles: list[dict]) -> list[dict]:
#     """Return up to MAX_PER_QUADRANT vehicles per quadrant."""
#     buckets: dict[str, list] = {}
#     for v in vehicles:
#         q = v['quadrant'] or 'XX'
#         buckets.setdefault(q, []).append(v)
#     result = []
#     for q, group in buckets.items():
#         result.extend(random.sample(group, min(MAX_PER_QUADRANT, len(group))))
#     return result


# @ui.page('/transit')
# @with_layout
# def transit_map_page():
#     ui.page_title('Calgary Transit Live Map')

#     current_layers = []
#     dark_mode      = {'on': True}
#     countdown      = {'value': 30}

#     # ── header ─────────────────────────────────────────────────────
#     with ui.row().classes('w-full items-center gap-4 px-4 pt-4 flex-wrap'):
#         ui.label('🚌 Calgary Transit — Live Map').classes('text-2xl font-bold flex-1')
#         vehicle_count  = ui.label('').classes('text-grey')
#         countdown_label = ui.label('Next refresh: 30s').classes('text-grey text-sm')
#         map_toggle     = ui.button('☀️ Light map').props('flat').classes('ml-2')

#     # ── controls ───────────────────────────────────────────────────
#     with ui.row().classes('w-full items-center gap-4 px-4 pb-1 flex-wrap'):
#         quadrant_select = ui.select(
#             options=QUADRANTS_FILTER,
#             value='All',
#             label='Quadrant',
#         ).classes('w-28')

#         route_ids    = fetch_route_ids()
#         route_select = ui.select(
#             options=['All routes'] + route_ids,
#             value='All routes',
#             label='Route',
#         ).classes('w-36')

#         resample_btn = ui.button('🔀 Resample').props('flat')

#         # poller controls
#         with ui.row().classes('items-center gap-2 ml-auto'):
#             poller_status = ui.label('● Poller running').classes('text-green text-sm')

#             def pause_poller():
#                 poller_service.pause()
#                 poller_status.set_text('⏸ Poller paused')
#                 poller_status.classes(remove='text-green', add='text-orange')
#                 pause_btn.set_visibility(False)
#                 resume_btn.set_visibility(True)

#             def resume_poller():
#                 poller_service.resume()
#                 poller_status.set_text('● Poller running')
#                 poller_status.classes(remove='text-orange', add='text-green')
#                 pause_btn.set_visibility(True)
#                 resume_btn.set_visibility(False)

#             pause_btn  = ui.button('⏸ Pause', on_click=pause_poller).props('flat color=orange')
#             resume_btn = ui.button('▶ Resume', on_click=resume_poller).props('flat color=green')
#             resume_btn.set_visibility(False)

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
#             ui.label('Stale').classes('text-sm')
#         with ui.row().classes('items-center gap-1'):
#             ui.html('<span style="display:inline-block;width:12px;height:12px;'
#                     'border-radius:50%;background:#aaa;opacity:0.35"></span>')
#             ui.label('Ghost').classes('text-sm')

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
#         countdown['value'] = 30
#         loop = asyncio.get_event_loop()

#         route = route_select.value
#         quad  = quadrant_select.value

#         all_vehicles = await loop.run_in_executor(
#             None,
#             lambda: fetch_latest_vehicles(
#                 route_id=None if route == 'All routes' else route,
#                 quadrant=None if quad  == 'All'        else quad,
#             )
#         )

#         display = _sample_vehicles(all_vehicles)
#         vehicle_count.set_text(
#             f'{len(all_vehicles)} total · {len(display)} shown '
#             f'({MAX_PER_QUADRANT}/quadrant)'
#         )

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

#     # ── countdown tick ─────────────────────────────────────────────
#     def tick():
#         countdown['value'] = max(0, countdown['value'] - 1)
#         countdown_label.set_text(f'Next refresh: {countdown["value"]}s')

#     route_select.on('update:model-value',    lambda _: asyncio.ensure_future(refresh(resample=True)))
#     quadrant_select.on('update:model-value', lambda _: asyncio.ensure_future(refresh(resample=True)))
#     resample_btn.on('click',                 lambda _: asyncio.ensure_future(refresh(resample=True)))

#     ui.timer(1.0, tick)
#     ui.timer(30.0, refresh)
#     ui.timer(1.5, lambda: asyncio.ensure_future(refresh()), once=True)
# app/pages/transit_map.py
import asyncio
import random
from nicegui import ui
from app.components.navbar import with_layout
from app.services.db import fetch_latest_vehicles, fetch_route_ids
from app.services import poller as poller_service
from app.services import schedule

QUADRANTS_FILTER = ['All', 'NE', 'NW', 'SE', 'SW']

QUADRANT_COLOURS = {
    'NE': '#4A90D9',
    'NW': '#A78BFA',
    'SE': '#34D399',
    'SW': '#FB923C',
}
STALE_COLOUR   = '#F87171'
DEFAULT_COLOUR = '#4A90D9'

TILE_DARK  = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
TILE_LIGHT = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'
TILE_ATTRIBUTION = '© OpenStreetMap contributors © CARTO'

MAX_PER_QUADRANT = 5


def _colour(v: dict) -> str:
    if v['is_stale']:
        return STALE_COLOUR
    return QUADRANT_COLOURS.get(v['quadrant'], DEFAULT_COLOUR)


def _sample_vehicles(vehicles: list[dict]) -> list[dict]:
    buckets: dict[str, list] = {}
    for v in vehicles:
        q = v['quadrant'] or 'XX'
        buckets.setdefault(q, []).append(v)
    result = []
    for group in buckets.values():
        result.extend(random.sample(group, min(MAX_PER_QUADRANT, len(group))))
    return result


@ui.page('/transit')
@with_layout
def transit_map_page():
    ui.page_title('Calgary Transit Live Map')

    # record that someone is viewing the page
    schedule.record_activity()

    current_layers = []
    dark_mode      = {'on': True}
    countdown      = {'value': 30}

    # ── header ─────────────────────────────────────────────────────
    with ui.row().classes('w-full items-center gap-4 px-4 pt-4 flex-wrap'):
        ui.label('🚌 Calgary Transit — Live Map').classes('text-2xl font-bold flex-1')
        vehicle_count   = ui.label('').classes('text-grey')
        countdown_label = ui.label('Next refresh: 30s').classes('text-grey text-sm')
        map_toggle      = ui.button('☀️ Light map').props('flat').classes('ml-2')

    # ── controls ───────────────────────────────────────────────────
    with ui.row().classes('w-full items-center gap-4 px-4 pb-1 flex-wrap'):
        quadrant_select = ui.select(
            options=QUADRANTS_FILTER,
            value='All',
            label='Quadrant',
        ).classes('w-28')

        route_ids    = fetch_route_ids()
        route_select = ui.select(
            options=['All routes'] + route_ids,
            value='All routes',
            label='Route',
        ).classes('w-36')

        resample_btn = ui.button('🔀 Resample').props('flat')

        # ── poller controls ────────────────────────────────────────
        with ui.row().classes('items-center gap-2 ml-auto'):
            in_hours = schedule.is_operating_hours()
            if in_hours:
                status_text  = '● Poller running'
                status_class = 'text-green'
            else:
                status_text  = '⏸ Outside hours (09:00–18:00 MST)'
                status_class = 'text-orange'

            poller_status = ui.label(status_text).classes(f'text-sm {status_class}')

            def pause_poller():
                poller_service.pause()
                poller_status.set_text('⏸ Poller paused')
                poller_status.classes(remove='text-green text-yellow', add='text-orange')
                pause_btn.set_visibility(False)
                resume_btn.set_visibility(True)

            def resume_poller():
                poller_service.resume()
                if schedule.is_operating_hours():
                    poller_status.set_text('● Poller running')
                    poller_status.classes(remove='text-orange text-yellow', add='text-green')
                else:
                    poller_status.set_text('▶ Manual override — pauses after 10min inactivity')
                    poller_status.classes(remove='text-orange text-green', add='text-yellow')
                pause_btn.set_visibility(True)
                resume_btn.set_visibility(False)

            pause_btn  = ui.button('⏸ Pause',  on_click=pause_poller).props('flat color=orange')
            resume_btn = ui.button('▶ Resume', on_click=resume_poller).props('flat color=green')

            # show correct initial button state
            if not in_hours or not schedule.should_poll():
                pause_btn.set_visibility(False)
            else:
                resume_btn.set_visibility(False)

    # ── legend ─────────────────────────────────────────────────────
    with ui.row().classes('gap-4 px-4 pb-2 items-center flex-wrap'):
        for quad, colour in QUADRANT_COLOURS.items():
            with ui.row().classes('items-center gap-1'):
                ui.html(f'<span style="display:inline-block;width:12px;height:12px;'
                        f'border-radius:50%;background:{colour}"></span>')
                ui.label(quad).classes('text-sm')
        with ui.row().classes('items-center gap-1'):
            ui.html(f'<span style="display:inline-block;width:12px;height:12px;'
                    f'border-radius:50%;background:{STALE_COLOUR}"></span>')
            ui.label('Stale').classes('text-sm')
        with ui.row().classes('items-center gap-1'):
            ui.html('<span style="display:inline-block;width:12px;height:12px;'
                    'border-radius:50%;background:#aaa;opacity:0.35"></span>')
            ui.label('Ghost').classes('text-sm')

    # ── map ────────────────────────────────────────────────────────
    m = ui.leaflet(
        center=(51.0447, -114.0719),
        zoom=11,
    ).classes('w-full').style('height:620px')

    m.clear_layers()
    tile_layer_state = {
        'layer': m.tile_layer(
            url_template=TILE_DARK,
            options={'attribution': TILE_ATTRIBUTION, 'maxZoom': 19, 'subdomains': 'abcd'},
        )
    }

    # ── tile toggle ────────────────────────────────────────────────
    def toggle_map_style():
        if tile_layer_state['layer']:
            m.remove_layer(tile_layer_state['layer'])
        if dark_mode['on']:
            tile_layer_state['layer'] = m.tile_layer(
                url_template=TILE_LIGHT,
                options={'attribution': TILE_ATTRIBUTION, 'maxZoom': 19, 'subdomains': 'abcd'},
            )
            dark_mode['on'] = False
            map_toggle.set_text('🌙 Dark map')
        else:
            tile_layer_state['layer'] = m.tile_layer(
                url_template=TILE_DARK,
                options={'attribution': TILE_ATTRIBUTION, 'maxZoom': 19, 'subdomains': 'abcd'},
            )
            dark_mode['on'] = True
            map_toggle.set_text('☀️ Light map')

    map_toggle.on('click', lambda _: toggle_map_style())

    # ── refresh ────────────────────────────────────────────────────
    async def refresh(resample: bool = False):
        countdown['value'] = 30
        schedule.record_activity()
        loop = asyncio.get_event_loop()

        route = route_select.value
        quad  = quadrant_select.value

        all_vehicles = await loop.run_in_executor(
            None,
            lambda: fetch_latest_vehicles(
                route_id=None if route == 'All routes' else route,
                quadrant=None if quad  == 'All'        else quad,
            )
        )

        display = _sample_vehicles(all_vehicles)
        vehicle_count.set_text(
            f'{len(all_vehicles)} total · {len(display)} shown '
            f'({MAX_PER_QUADRANT}/quadrant)'
        )

        for layer in current_layers:
            m.remove_layer(layer)
        current_layers.clear()

        for v in display:
            colour    = _colour(v)
            speed_kmh = round(v['speed'] * 3.6, 1) if v['speed'] else 0
            tooltip   = (
                f"Route {v['route_id'] or '?'} | "
                f"Vehicle {v['vehicle_id']} | "
                f"{speed_kmh} km/h | "
                f"{'⚠️ Stale' if v['is_stale'] else '✅ Moving'}"
            )

            if v['prev_lat'] and v['prev_lon']:
                ghost = m.generic_layer(
                    name='circleMarker',
                    args=[
                        [v['prev_lat'], v['prev_lon']],
                        {'radius': 5, 'color': colour, 'fillColor': colour,
                         'fillOpacity': 0.25, 'opacity': 0.25, 'weight': 1},
                    ],
                )
                current_layers.append(ghost)

            dot = m.generic_layer(
                name='circleMarker',
                args=[
                    [v['lat'], v['lon']],
                    {'radius': 8, 'color': 'white', 'fillColor': colour,
                     'fillOpacity': 0.95, 'opacity': 1, 'weight': 2},
                ],
            )
            dot.run_method('bindTooltip', tooltip, {'permanent': False, 'sticky': True})
            current_layers.append(dot)

    # ── countdown tick ─────────────────────────────────────────────
    def tick():
        countdown['value'] = max(0, countdown['value'] - 1)
        countdown_label.set_text(f'Next refresh: {countdown["value"]}s')

    route_select.on('update:model-value',    lambda _: asyncio.ensure_future(refresh(resample=True)))
    quadrant_select.on('update:model-value', lambda _: asyncio.ensure_future(refresh(resample=True)))
    resample_btn.on('click',                 lambda _: asyncio.ensure_future(refresh(resample=True)))

    ui.timer(1.0, tick)
    ui.timer(30.0, refresh)
    ui.timer(1.5, lambda: asyncio.ensure_future(refresh()), once=True)