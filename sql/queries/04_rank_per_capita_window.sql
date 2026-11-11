-- title: Рейтинг стран по CO₂ на душу в 2024 г. (оконная функция RANK), страны с населением ≥ 1 млн
WITH ranked AS (
    SELECT c.name, c.continent, m.co2_per_capita, m.co2, e.population,
           RANK() OVER (ORDER BY m.co2_per_capita DESC) AS rank_world,
           RANK() OVER (PARTITION BY c.continent ORDER BY m.co2_per_capita DESC) AS rank_continent,
           COUNT(*) OVER () AS n_total
    FROM emissions_annual m
    JOIN energy_annual e ON e.country_id = m.country_id AND e.year = m.year
    JOIN countries c ON c.country_id = m.country_id
    WHERE m.year = 2024 AND e.population >= 1000000 AND m.co2_per_capita IS NOT NULL
)
SELECT name, continent, ROUND(co2_per_capita, 2) AS co2_per_capita, ROUND(co2, 1) AS co2_mt,
       rank_world, rank_continent, n_total
FROM ranked
WHERE rank_world <= 15 OR name = 'Kazakhstan'
ORDER BY rank_world;
