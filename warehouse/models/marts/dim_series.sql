-- One row per series: the Bank's description plus our name, category and display label.
select
    c.series_id,
    c.measure,
    c.category,
    c.display_name,
    s.label as source_label,
    s.description as source_description,
    s.unit,
    s.frequency
from {{ ref('boc_series_catalog') }} as c
left join {{ source('raw', 'boc_series') }} as s
    on s.series_id = c.series_id
