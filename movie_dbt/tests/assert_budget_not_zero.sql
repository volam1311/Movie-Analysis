select movie_id
from {{ ref('stg_movie') }}
where budget = 0 or revenue = 0
