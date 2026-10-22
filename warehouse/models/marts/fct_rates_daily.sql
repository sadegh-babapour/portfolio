-- Grain: one row per series per date that has a value.
-- change_from_previous compares with the series' previous published day (a window
-- function), so a Monday compares with the Friday before it.
select
    series_id,
    measure,
    obs_date,
    value,
    value - lag(value) over (partition by series_id order by obs_date) as change_from_previous,
    last_changed_at
from {{ ref('stg_boc__observations') }}
