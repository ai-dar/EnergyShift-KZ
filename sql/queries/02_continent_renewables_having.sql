-- title: Средняя доля ВИЭ и CO₂ на душу по континентам, 2015–2024 (GROUP BY + HAVING)
-- Оставляем континенты, где не менее 3 стран с данными об энергобалансе.
SELECT c.continent,
       COUNT(DISTINCT c.country_id)              AS n_countries,
       ROUND(AVG(e.renewables_share_energy), 2)  AS avg_renewables_share,
       ROUND(AVG(e.fossil_share_energy), 2)      AS avg_fossil_share,
       ROUND(AVG(m.co2_per_capita), 2)           AS avg_co2_per_capita
FROM countries c
JOIN energy_annual    e ON e.country_id = c.country_id
JOIN emissions_annual m ON m.country_id = c.country_id AND m.year = e.year
WHERE e.year BETWEEN 2015 AND 2024 AND e.renewables_share_energy IS NOT NULL
GROUP BY c.continent
HAVING COUNT(DISTINCT c.country_id) >= 3
ORDER BY avg_renewables_share DESC;
