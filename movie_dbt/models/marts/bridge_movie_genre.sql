-- grain: one row per movie_id, genre_id
select
    movie_id,
    genre_id,
    genre_name
from {{ ref('stg_movie_genre') }}
