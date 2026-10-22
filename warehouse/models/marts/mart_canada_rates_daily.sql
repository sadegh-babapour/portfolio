-- Grain: one row per date, one column per measure (a pivot by conditional aggregation).
-- What a dashboard reads. A missing value stays null: it is not carried forward.
with daily as (
    select
        obs_date,
        max(value) filter (where measure = 'policy_rate') as policy_rate,
        max(value) filter (where measure = 'corra') as corra,
        max(value) filter (where measure = 'gov_2y') as gov_2y,
        max(value) filter (where measure = 'gov_5y') as gov_5y,
        max(value) filter (where measure = 'gov_10y') as gov_10y,
        max(value) filter (where measure = 'usd_cad') as usd_cad
    from {{ ref('fct_rates_daily') }}
    group by obs_date
)

select
    *,
    -- The yield curve's slope in basis points. Below zero ("inverted") has often come
    -- before recessions, which is why markets watch it.
    round((gov_10y - gov_2y) * 100) as spread_10y_2y_bps,
    gov_10y < gov_2y as curve_inverted
from daily
