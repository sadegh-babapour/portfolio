# app/pages/dashboard.py
from nicegui import ui
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv
import os
from supabase import create_client, Client
from app.components.navbar import navbar
from app.components.navbar import with_layout
import json




# Load environment variables
if os.path.exists('.env'):
    load_dotenv()

# Database connection
def get_supabase_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    return create_client(url, key)

# # Data fetching functions
# def fetch_daily_stats():
#     supabase = get_supabase_client()
#     response = supabase.table('daily_stats').select("*").order('date', desc=True).limit(30).execute()
#     return response.data

# def fetch_membership_summary():
#     supabase = get_supabase_client()
#     response = supabase.table('membership_summary').select("*").order('period_date', desc=True).execute()
#     return response.data

# def fetch_revenue_summary():
#     supabase = get_supabase_client()
#     response = supabase.table('revenue_summary').select("*").order('date', desc=True).limit(30).execute()
#     return response.data

# def fetch_member_visits():
#     supabase = get_supabase_client()
#     response = supabase.table('member_visits').select("*").order('visit_date', desc=True).execute()
#     return response.data

def get_cached_dashboard_data():
    """
    Check if we have today's data cached in JSON, otherwise fetch from DB
    """
    cache_file = 'dashboard_cache.json'
    today = datetime.now().date().isoformat()
    
    # Try to read existing cache
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Check if cache is from today
            if cache_data.get('cache_date') == today:
                print(f"📁 Using cached data from {today}")
                return cache_data['data']
        except (json.JSONDecodeError, KeyError):
            print("⚠️ Cache file corrupted, fetching fresh data")
    
    # Cache doesn't exist or is old, fetch fresh data
    print("🔄 Fetching fresh data from database...")
    
    fresh_data = {
        'daily_stats': fetch_daily_stats(),
        'membership_summary': fetch_membership_summary(),
        'revenue_summary': fetch_revenue_summary(),
        'member_visits': fetch_member_visits()
    }
    
    # Save to cache file
    cache_content = {
        'cache_date': today,
        'last_updated': datetime.now().isoformat(),
        'data': fresh_data
    }
    
    try:
        with open(cache_file, 'w') as f:
            json.dump(cache_content, f, indent=2, default=str)
        print(f"💾 Data cached for {today}")
    except Exception as e:
        print(f"⚠️ Failed to save cache: {e}")
    
    return fresh_data

def get_cached_table_data(table_name):
    """Get specific table data from cache"""
    cached_data = get_cached_dashboard_data()
    return cached_data.get(table_name, [])


@ui.page('/dashboard')
@with_layout
def dashboard_page():
    ui.page_title("Theme Park Analytics Dashboard")
    
    with ui.header():
        ui.label("🎢 Theme Park Analytics Dashboard").classes('text-h4 text-white')
    
    with ui.column().classes('w-full max-w-7xl mx-auto p-4'):
        
        # Data tables section
        with ui.card().classes('w-full mb-6'):
            ui.label("📊 Data Tables").classes('text-h5 mb-4')
            
            with ui.tabs().classes('w-full') as tabs:
                daily_tab = ui.tab('Daily Stats')
                membership_tab = ui.tab('Membership')
                revenue_tab = ui.tab('Revenue')
                visits_tab = ui.tab('Member Visits')
            
            with ui.tab_panels(tabs, value=daily_tab).classes('w-full'):
                
                with ui.tab_panel(daily_tab):
                    # daily_data = fetch_daily_stats()
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
        
        # Charts section
        with ui.card().classes('w-full'):
            ui.label("📈 Analytics Charts").classes('text-h5 mb-4')
            
            # Row 1: Daily attendance and revenue
            with ui.row().classes('w-full gap-4 mb-4'):
                with ui.column().classes('flex-1'):
                    create_attendance_chart()
                with ui.column().classes('flex-1'):
                    create_revenue_chart()
            
            # Row 2: Membership trends and breakdown
            with ui.row().classes('w-full gap-4'):
                with ui.column().classes('flex-1'):
                    create_membership_chart()
                with ui.column().classes('flex-1'):
                    create_revenue_breakdown_chart()

def create_attendance_chart():
    """Daily Attendance Trend"""
    daily_data = get_cached_table_data('daily_stats')
    
    dates = [item['date'] for item in daily_data]
    attendance = [item['total_attendance'] for item in daily_data]
    
    chart_options = {
        'title': {'text': 'Daily Attendance Trend', 'left': 'center'},
        'tooltip': {'trigger': 'axis'},
        'xAxis': {
            'type': 'category',
            'data': dates
        },
        'yAxis': {'type': 'value'},
        'series': [{
            'name': 'Attendance',
            'type': 'line',
            'data': attendance,
            'smooth': True,
            'itemStyle': {'color': '#1f77b4'}
        }]
    }
    
    ui.echart(chart_options).classes('w-full h-80')

def create_revenue_chart():
    """Daily Revenue Trend"""
    revenue_data = get_cached_table_data('revenue_summary')
    
    dates = [item['date'] for item in revenue_data]
    revenue = [float(item['total_revenue']) for item in revenue_data]
    
    chart_options = {
        'title': {'text': 'Daily Revenue Trend', 'left': 'center'},
        'tooltip': {'trigger': 'axis', 'formatter': '{b}: ${c:,.2f}'},
        'xAxis': {
            'type': 'category',
            'data': dates
        },
        'yAxis': {'type': 'value'},
        'series': [{
            'name': 'Revenue',
            'type': 'bar',
            'data': revenue,
            'itemStyle': {'color': '#2ca02c'}
        }]
    }
    
    ui.echart(chart_options).classes('w-full h-80')

def create_membership_chart():
    """Membership Activities"""
    membership_data = get_cached_table_data('membership_summary')
    
    # Aggregate by date
    dates = list(set([item['period_date'] for item in membership_data]))
    dates.sort()
    
    new_data = []
    renewal_data = []
    
    for date in dates:
        new_total = sum([item['new_memberships'] for item in membership_data if item['period_date'] == date])
        renewal_total = sum([item['renewals'] for item in membership_data if item['period_date'] == date])
        new_data.append(new_total)
        renewal_data.append(renewal_total)
    
    chart_options = {
        'title': {'text': 'Membership Activities', 'left': 'center'},
        'tooltip': {'trigger': 'axis'},
        'legend': {'data': ['New', 'Renewals'], 'bottom': 0},
        'xAxis': {
            'type': 'category',
            'data': dates
        },
        'yAxis': {'type': 'value'},
        'series': [
            {
                'name': 'New',
                'type': 'bar',
                'data': new_data,
                'itemStyle': {'color': '#ff7f0e'}
            },
            {
                'name': 'Renewals',
                'type': 'bar',
                'data': renewal_data,
                'itemStyle': {'color': '#d62728'}
            }
        ]
    }
    
    ui.echart(chart_options).classes('w-full h-80')

def create_revenue_breakdown_chart():
    """Revenue Breakdown Pie Chart"""
    revenue_data = get_cached_table_data('revenue_summary')
    
    # Calculate totals
    admission_total = sum([float(item['admission_revenue']) for item in revenue_data])
    membership_total = sum([float(item['membership_revenue']) for item in revenue_data])
    fb_total = sum([float(item['food_beverage_revenue']) for item in revenue_data])
    merch_total = sum([float(item['merchandise_revenue']) for item in revenue_data])
    
    chart_options = {
        'title': {'text': 'Revenue Breakdown', 'left': 'center'},
        'tooltip': {'trigger': 'item', 'formatter': '{a} <br/>{b}: ${c:,.2f} ({d}%)'},
        'series': [{
            'name': 'Revenue',
            'type': 'pie',
            'radius': '50%',
            'data': [
                {'value': admission_total, 'name': 'Admissions'},
                {'value': membership_total, 'name': 'Memberships'},
                {'value': fb_total, 'name': 'Food & Beverage'},
                {'value': merch_total, 'name': 'Merchandise'}
            ],
            'emphasis': {
                'itemStyle': {
                    'shadowBlur': 10,
                    'shadowOffsetX': 0,
                    'shadowColor': 'rgba(0, 0, 0, 0.5)'
                }
            }
        }]
    }
    
    ui.echart(chart_options).classes('w-full h-80')