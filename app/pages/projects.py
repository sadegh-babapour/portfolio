from nicegui import ui
from app.components.navbar import navbar
from app.components.navbar import with_layout
from random import random


@ui.page('/projects')
@with_layout
def projects():
    with ui.column().classes('mx-auto max-w-screen-xl p-8'):
        ui.label('Projects').classes('text-4xl mb-4')
        ui.label('Public Dashboards').classes('text-2xl mt-6')
        with ui.row().classes('gap-4'):
            with ui.card().style('width: 70vw; min-width: 300px; height: 50vh; min-height: 300px'):
            # style('min-height:400px'):
                ui.label('Sales Dashboard')
                
                options = {
                    'xAxis': {'type': 'value'},
                    'yAxis': {'type': 'category', 'data': ['A', 'B'], 'inverse': True},
                    'legend': {'textStyle': {'color': 'gray'}},
                    'series': [
                        {'type': 'bar', 'name': 'Alpha', 'data': [0.1, 0.2]},
                        {'type': 'bar', 'name': 'Beta', 'data': [0.3, 0.4]},
                    ],
                }

                          
                echart = ui.echart(options).classes('w-full')
                
                def update():
                    echart.options['series'][0]['data'][0] = random()
                    echart.update()

                ui.button('Update', on_click=update)
        
        
        
        
        
        
        
        ui.label('User-Only Projects').classes('text-2xl mt-6')
        with ui.row().classes('gap-4'):
            with ui.card().style('width: 70vw; min-width: 300px; height: 50vh; min-height: 300px'):
                ui.label('Internal Analytics Tool')
                
                options2 = {
  'angleAxis': {
    'type': 'category',
    'data': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  },
  'radiusAxis': {},
  'polar': {},
  'series': [
    {
      'type': 'bar',
      'data': [1, 2, 3, 4, 3, 5, 1],
      'coordinateSystem': 'polar',
      'name': 'A',
      'stack': 'a',
      'emphasis': {
        'focus': 'series'
      }
    },
    {
      'type': 'bar',
      'data': [2, 4, 6, 1, 3, 2, 1],
      'coordinateSystem': 'polar',
      'name': 'B',
      'stack': 'a',
      'emphasis': {
        'focus': 'series'
      }
    },
    {
      'type': 'bar',
      'data': [1, 2, 3, 4, 1, 2, 5],
      'coordinateSystem': 'polar',
      'name': 'C',
      'stack': 'a',
      'emphasis': {
        'focus': 'series'
      }
    }
  ],
  'legend': {
    'show': True,
    'data': ['A', 'B', 'C']
  }
}






        echart2 = ui.echart(options2).classes('w-full')




        ui.label('Experimental Projects').classes('text-2xl mt-6')
        with ui.row().classes('gap-4'):
            with ui.card():
                ui.label('Leaflet Travel Path')
                ui.image('https://dummyimage.com/600x400/444/ccc&text=Map+Path')
            with ui.card().style('width: 70vw; min-width: 300px; height: 70vh; min-height: 500px'):
                ui.label('Image Classifier')

                category = [
  '2025-08-01', '2025-08-02', '2025-08-03', '2025-08-04', '2025-08-05',
  '2025-08-06', '2025-08-07', '2025-08-08', '2025-08-09', '2025-08-10',
  '2025-08-11', '2025-08-12', '2025-08-13', '2025-08-14', '2025-08-15',
  '2025-08-16', '2025-08-17', '2025-08-18', '2025-08-19', '2025-08-20'
]

                bar_data = [
  45.23,  178.9,  12.4,  67.8,  190.1,
  88.3,   3.14,   150.2, 34.5,  123.4,
  56.7,   99.9,   10.1,  75.6,  142.3,
  61.2,   82.5,   7.8,   199.9, 18.2
]

                line_data = [
  120.5,  210.3,  78.2,  130.4,  180.6,
  145.7,  50.9,   180.1, 89.4,   160.8,
  100.2,  190.2,  60.6,  140.9,  165.0,
  123.7,  115.3,  98.6,   210.4,  70.9
]




                options3 = {
                    # 'height': '70%',
  'backgroundColor': '#0f375f',
  'tooltip': {
    'trigger': 'axis',
    'axisPointer': {
      'type': 'shadow'
    }
  },
  'legend': {
    'data': ['line', 'bar'],
    'textStyle': {
      'color': '#ccc'
    }
  },
  'xAxis': {
    'data': category,
    'axisLine': {
      'lineStyle': {
        'color': 'white'
      }
    }
  },
  'yAxis': {
    'splitLine': { 'show': True },
    'axisLine': {
      'lineStyle': {
        'color': 'white'
      }
    }
  },
  'series': [
    {
      'name': 'line',
      'type': 'line',
      'smooth': True,
      'showAllSymbol': True,
      'symbol': 'emptyCircle',
      'symbolSize': 15,
      'data': line_data
    },
    {
      'name': 'bar',
      'type': 'bar',
      'barWidth': 10,
      'itemStyle': {
        'borderRadius': 5,
        'color':'yellow'
      },
      'data': bar_data
    },
    {
      'name': 'line',
      'type': 'bar',
      'barGap': '-100%',
      'barWidth': 10,
      'itemStyle': {
        'color': 'green'
      },
      'z': -12,
      'data': line_data
    },
    {
      'name': 'dotted',
      'type': 'pictorialBar',
      'symbol': 'rect',
      'itemStyle': {
        'color': '#0f375f'
      },
      'symbolRepeat': True,
      'symbolSize': [12, 4],
      'symbolMargin': 1,
      'z': -10,
      'data': line_data
    }
  ]
}
                # echart3 = ui.echart(options3).classes('w-full').style(height='100%')
                echart3 = ui.echart(options3).style('height: 100%')