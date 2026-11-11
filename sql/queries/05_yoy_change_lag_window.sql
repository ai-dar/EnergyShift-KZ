-- title: Годовой прирост выбросов Казахстана и 3-летнее скользящее среднее (LAG, AVG OVER)
SELECT c.name, m.year, ROUND(m.co2, 1) AS co2_mt,
       ROUND(m.co2 - LAG(m.co2) OVER (PARTITION BY c.name ORDER BY m.year), 1)         AS yoy_change_mt,
       ROUND(100.0 * (m.co2 / LAG(m.co2) OVER (PARTITION BY c.name ORDER BY m.year) - 1), 2) AS yoy_change_pct,
       ROUND(AVG(m.co2) OVER (PARTITION BY c.name ORDER BY m.year ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1) AS ma_3y
FROM emissions_annual m
JOIN countries c ON c.country_id = m.country_id
WHERE c.name IN ('Kazakhstan', 'Uzbekistan')
ORDER BY c.name, m.year;
