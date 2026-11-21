-- grain: one row per movie_id
select
    id as movie_id,
    title,
    original_title,
    original_language,
    overview,
    status,
    adult,
    release_date,
    case when runtime is null or runtime = 0 then null else runtime end as runtime,
    case when budget is null or budget = 0 then null else budget end as budget,
    case when revenue is null or revenue = 0 then null else revenue end as revenue,
    popularity,
    vote_average,
    vote_count,
    loaded_at as ingested_at
from {{ source('tmdb', 'movie_detail') }}