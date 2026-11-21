-- grain: one row per calendar day
-- range: Jan 1 of the earliest release year through Dec 31 of the latest release year
with bounds as (
    select
        date_trunc('year', min(release_date))::date as start_date,
        (date_trunc('year', max(release_date)) + interval 1 year - interval 1 day)::date as end_date
    from {{ ref('stg_movie') }}
),

spine as (
    select unnest(generate_series(start_date, end_date, interval 1 day))::date as date_day
    from bounds
)

select
    cast(strftime(date_day, '%Y%m%d') as integer) as date_key,
    date_day,
    year(date_day) as year,
    quarter(date_day) as quarter,
    month(date_day) as month,
    monthname(date_day) as month_name,
    day(date_day) as day_of_month,
    isodow(date_day) as day_of_week,  -- 1 = Monday ... 7 = Sunday
    dayname(date_day) as day_name,
    isodow(date_day) in (6, 7) as is_weekend,
    (year(date_day) // 10) * 10 as decade
from spine
