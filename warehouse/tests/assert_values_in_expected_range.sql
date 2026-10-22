-- Every value inside the range its catalog row allows. A returned row fails the build:
-- a policy rate of 45% or USD/CAD of 0.02 is a loading bug, not news.
select f.series_id, f.obs_date, f.value, c.min_expected, c.max_expected
from {{ ref('fct_rates_daily') }} as f
join {{ ref('boc_series_catalog') }} as c
    on c.series_id = f.series_id
where f.value < c.min_expected
   or f.value > c.max_expected
