-- grain: one row per original_language code
select distinct
    original_language as language_code,
    case original_language
        when 'en' then 'English'
        when 'es' then 'Spanish'
        when 'ko' then 'Korean'
        when 'ja' then 'Japanese'
        when 'zh' then 'Chinese'
        when 'hi' then 'Hindi'
        when 'ta' then 'Tamil'
        when 'te' then 'Telugu'
        when 'de' then 'German'
        when 'pl' then 'Polish'
        when 'id' then 'Indonesian'
        when 'ro' then 'Romanian'
        when 'sv' then 'Swedish'
        else original_language
    end as language_name
from {{ ref('stg_movie') }}
where original_language is not null
