# app/pages/dashboard.py
# Reads from local dashboard_cache.json — no live DB connection needed here.
# The cache was populated from the old Supabase data and serves as a static demo.

from nicegui import ui
from datetime import datetime
import json
import os
from app.components.navbar import with_layout


CACHE_FILE = 'dashboard_cache.json'


def get_cached_table_data(table_name: str) -> list:
    """Load a specific table from the local JSON cache. Returns [] if missing."""
    if not os.path.exists(CACHE_FILE):
        return []
    try:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        return cache.get('data', {}).get(table_name, [])
    except (json.JSONDecodeError, KeyError):
        return []


@ui.page('/dashboard')
@with_layout
def dashboard_page():
    ui.page_title('Theme Park Analytics Dashboard')

    with ui.column().classes('w-full max-w-7xl mx-auto p-4'):

        with ui.card().classes('w-full mb-6'):
            ui.label('📊 Data Tables').classes('text-h5 mb-4')

            with ui.tabs().classes('w-full') as tabs:
                daily_tab = ui.tab('Daily Stats')
                membership_tab = ui.tab('Membership')
                revenue_tab = ui.tab('Revenue')
                visits_tab = ui.tab('Member Visits')

            with ui.tab_panels(tabs, value=daily_tab).classes('w-full'):

                with ui.tab_panel(daily_tab):
                    daily_data = get_cached_table_data('daily_stats')
                    if daily_data:
                        columns = [
                            {'name': 'date', 'label': 'Date', 'field': 'date', 'align': 'left'},
                            {'name': 'total_attendance', 'label': 'Total Attendance', 'field': 'total_attendance', 'align': 'right'},
                            {'name': 'general_admissions', 'label': 'General', 'field': 'general_admissions', 'align': 'right'},
                            {'name': 'member_admissions', 'label': 'Members', 'field': 'member_admissions', 'align': 'right'},
                            {'name': 'daily_revenue', 'label': 'Revenue ($)', 'field': 'daily_revenue', 'align': 'right'},
                            {'name': 'weather_condition', 'label': 'Weather', 'field': 'weather_condition', 'align': 'center'},
                        ]
                        ui.table(columns=columns, rows=daily_data).classes('w-full')
                    else:
                        ui.label('No data available.').classes('text-grey')

                with ui.tab_panel(membership_tab):
                    membership_data = get_cached_table_data('membership_summary')
                    if membership_data:
                        columns = [
                            {'name': 'period_date', 'label': 'Date', 'field': 'period_date', 'align': 'left'},
                            {'name': 'membership_type', 'label': 'Type', 'field': 'membership_type', 'align': 'center'},
                            {'name': 'new_memberships', 'label': 'New', 'field': 'new_memberships', 'align': 'right'},
                            {'name': 'renewals', 'label': 'Renewals', 'field': 'renewals', 'align': 'right'},
                            {'name': 'expirations', 'label': 'Expired', 'field': 'expirations', 'align': 'right'},
                            {'name': 'active_members', 'label': 'Active', 'field': 'active_members', 'align': 'right'},
                        ]
                        ui.table(columns=columns, rows=membership_data).classes('w-full')
                    else:
                        ui.label('No data available.').classes('text-grey')

                with ui.tab_panel(revenue_tab):
                    revenue_data = get_cached_table_data('revenue_summary')
                    if revenue_data:
                        columns = [
                            {'name': 'date', 'label': 'Date', 'field': 'date', 'align': 'left'},
                            {'name': 'admission_revenue', 'label': 'Admissions', 'field': 'admission_revenue', 'align': 'right'},
                            {'name': 'membership_revenue', 'label': 'Memberships', 'field': 'membership_revenue', 'align': 'right'},
                            {'name': 'food_beverage_revenue', 'label': 'F&B', 'field': 'food_beverage_revenue', 'align': 'right'},
                            {'name': 'total_revenue', 'label': 'Total', 'field': 'total_revenue', 'align': 'right'},
                        ]
                        ui.table(columns=columns, rows=revenue_data).classes('w-full')
                    else:
                        ui.label('No data available.').classes('text-grey')

                with ui.tab_panel(visits_tab):
                    visits_data = get_cached_table_data('member_visits')
                    if visits_data:
                        columns = [
                            {'name': 'visit_date', 'label': 'Date', 'field': 'visit_date', 'align': 'left'},
                            {'name': 'member_type', 'label': 'Type', 'field': 'member_type', 'align': 'center'},
                            {'name': 'visit_count', 'label': 'Visits', 'field': 'visit_count', 'align': 'right'},
                            {'name': 'avg_visit_duration', 'label': 'Avg Duration (hrs)', 'field': 'avg_visit_duration', 'align': 'right'},
                            {'name': 'guest_count', 'label': 'Guests', 'field': 'guest_count', 'align': 'right'},
                        ]
                        ui.table(columns=columns, rows=visits_data).classes('w-full')
                    else:
                        ui.label('No data available.').classes('text-grey')

        with ui.card().classes('w-full'):
            ui.label('📈 Analytics Charts').classes('text-h5 mb-4')

            with ui.row().classes('w-full gap-4 mb-4'):
                with ui.column().classes('flex-1'):
                    _attendance_chart()
                with ui.column().classes('flex-1'):
                    _revenue_chart()

            with ui.row().classes('w-full gap-4'):
                with ui.column().classes('flex-1'):
                    _membership_chart()
                with ui.column().classes('flex-1'):
                    _revenue_breakdown_chart()


def _attendance_chart():
    data = get_cached_table_data('daily_stats')
    ui.echart({
        'title': {'text': 'Daily Attendance Trend', 'left': 'center'},
        'tooltip': {'trigger': 'axis'},
        'xAxis': {'type': 'category', 'data': [d['date'] for d in data]},
        'yAxis': {'type': 'value'},
        'series': [{'name': 'Attendance', 'type': 'line', 'smooth': True,
                    'data': [d['total_attendance'] for d in data],
                    'itemStyle': {'color': '#1f77b4'}}],
    }).classes('w-full h-80')


def _revenue_chart():
    data = get_cached_table_data('revenue_summary')
    ui.echart({
        'title': {'text': 'Daily Revenue Trend', 'left': 'center'},
        'tooltip': {'trigger': 'axis'},
        'xAxis': {'type': 'category', 'data': [d['date'] for d in data]},
        'yAxis': {'type': 'value'},
        'series': [{'name': 'Revenue', 'type': 'bar',
                    'data': [float(d['total_revenue']) for d in data],
                    'itemStyle': {'color': '#2ca02c'}}],
    }).classes('w-full h-80')


def _membership_chart():
    data = get_cached_table_data('membership_summary')
    dates = sorted(set(d['period_date'] for d in data))
    new_data = [sum(d['new_memberships'] for d in data if d['period_date'] == dt) for dt in dates]
    renewal_data = [sum(d['renewals'] for d in data if d['period_date'] == dt) for dt in dates]
    ui.echart({
        'title': {'text': 'Membership Activities', 'left': 'center'},
        'tooltip': {'trigger': 'axis'},
        'legend': {'data': ['New', 'Renewals'], 'bottom': 0},
        'xAxis': {'type': 'category', 'data': dates},
        'yAxis': {'type': 'value'},
        'series': [
            {'name': 'New', 'type': 'bar', 'data': new_data, 'itemStyle': {'color': '#ff7f0e'}},
            {'name': 'Renewals', 'type': 'bar', 'data': renewal_data, 'itemStyle': {'color': '#d62728'}},
        ],
    }).classes('w-full h-80')


def _revenue_breakdown_chart():
    data = get_cached_table_data('revenue_summary')
    ui.echart({
        'title': {'text': 'Revenue Breakdown', 'left': 'center'},
        'tooltip': {'trigger': 'item'},
        'series': [{'name': 'Revenue', 'type': 'pie', 'radius': '50%', 'data': [
            {'value': sum(float(d['admission_revenue']) for d in data), 'name': 'Admissions'},
            {'value': sum(float(d['membership_revenue']) for d in data), 'name': 'Memberships'},
            {'value': sum(float(d['food_beverage_revenue']) for d in data), 'name': 'Food & Beverage'},
            {'value': sum(float(d['merchandise_revenue']) for d in data), 'name': 'Merchandise'},
        ]}],
    }).classes('w-full h-80')