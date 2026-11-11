-- title: Скорость энергоперехода: изменение доли ископаемых источников 2000→2024 (CTE + FIRST_VALUE/LAST_VALUE)
WITH series AS (
    SELECT c.name, e.year, e.fossil_share_energy, e.low_carbon_share_energy,
           FIRST_VALUE(e.fossil_share_energy) OVER (PARTITION BY c.name ORDER BY e.year) AS fossil_2000,
           LAST_VALUE(e.fossil_share_energy)  OVER (PARTITION BY c.name ORDER BY e.year
               ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS fossil_2024,
           FIRST_VALUE(e.low_carbon_share_energy) OVER (PARTITION BY c.name ORDER BY e.year) AS low_carbon_2000,
           LAST_VALUE(e.low_carbon_share_energy)  OVER (PARTITION BY c.name ORDER BY e.year
               ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS low_carbon_2024
    FROM energy_annual e JOIN countries c ON c.country_id = e.country_id
    WHERE e.year IN (2000, 2024) AND e.fossil_share_energy IS NOT NULL
),
ranked AS (
    SELECT name, ROUND(fossil_2000, 1) AS fossil_2000, ROUND(fossil_2024, 1) AS fossil_2024,
           ROUND(fossil_2024 - fossil_2000, 1) AS fossil_change_pp,
           ROUND(low_carbon_2024 - low_carbon_2000, 1) AS low_carbon_change_pp,
           RANK() OVER (ORDER BY fossil_2024 - fossil_2000) AS transition_rank,
           COUNT(*) OVER () AS n_countries
    FROM series
    WHERE year = 2024
)
SELECT * FROM ranked
WHERE transition_rank <= 20 OR name IN ('Kazakhstan', 'Russia', 'Uzbekistan', 'China')
ORDER BY transition_rank;
