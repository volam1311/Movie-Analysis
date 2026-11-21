-- grain: one row per movie_id
-- join to dim_date on release_date_key = date_key
with genres as (
    select
        movie_id,
        count(*) as genre_count
    from {{ ref('stg_movie_genre') }}
    group by movie_id
)

select
    movies.movie_id,
    cast(strftime(movies.release_date, '%Y%m%d') as integer) as release_date_key,
    year(movies.release_date) as release_year,
    movies.title,
    movies.original_language,
    movies.status,
    movies.adult,
    movies.runtime,
    movies.budget,
    movies.revenue,
    movies.revenue - movies.budget as profit,  -- null if either side is unknown
    case
        when movies.budget is null or movies.revenue is null then null
        else round((movies.revenue - movies.budget)::double / movies.budget, 4)
    end as roi,
    movies.popularity,
    movies.vote_average,
    movies.vote_count,
    coalesce(genres.genre_count, 0) as genre_count
from {{ ref('stg_movie') }} as movies
left join genres
    on movies.movie_id = genres.movie_id
