-- title: Страны, чьи душевые выбросы в 2024 г. выше среднего по миру (подзапрос), и место Казахстана
SELECT c.name, c.continent, ROUND(m.co2_per_capita, 2) AS co2_per_capita,
       ROUND(m.co2_per_capita / (SELECT AVG(co2_per_capita) FROM emissions_annual WHERE year = 2024), 2) AS ratio_to_avg,
       (SELECT COUNT(*) FROM emissions_annual WHERE year = 2024
          AND co2_per_capita > (SELECT AVG(co2_per_capita) FROM emissions_annual WHERE year = 2024)) AS n_above_avg
FROM emissions_annual m
JOIN countries c ON c.country_id = m.country_id
WHERE m.year = 2024
  AND m.co2_per_capita > (SELECT AVG(co2_per_capita) FROM emissions_annual WHERE year = 2024)
ORDER BY m.co2_per_capita DESC;
