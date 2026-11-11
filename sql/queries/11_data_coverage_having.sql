-- title: Полнота данных: страны с полным рядом 1990–2024 по CO₂ и энергобалансу (HAVING COUNT)
SELECT c.continent,
       COUNT(*) AS n_countries_full_coverage,
       GROUP_CONCAT(c.name, ', ') AS examples
FROM countries c
JOIN (
    SELECT m.country_id
    FROM emissions_annual m
    JOIN energy_annual e ON e.country_id = m.country_id AND e.year = m.year
    WHERE m.co2 IS NOT NULL AND e.primary_energy_consumption IS NOT NULL
    GROUP BY m.country_id
    HAVING COUNT(DISTINCT m.year) = 35
) cov ON cov.country_id = c.country_id
GROUP BY c.continent
ORDER BY n_countries_full_coverage DESC;
