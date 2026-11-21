-- grain: one row per (movie_id, genre_id)
select distinct
    m.id as movie_id,
    g.genre.id as genre_id,
    g.genre.name as genre_name
from {{ source('tmdb', 'movie_detail') }} as m,
    unnest(m.genres) as g(genre)
