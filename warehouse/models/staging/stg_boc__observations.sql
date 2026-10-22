-- One row per series per date, renamed and joined to our own name for each series.
select
    o.series_id,
    c.measure,
    o.obs_date,
    o.value,
    o.first_loaded_at,
    o.last_changed_at
from {{ source('raw', 'boc_observations') }} as o
left join {{ ref('boc_series_catalog') }} as c
    on c.series_id = o.series_id
