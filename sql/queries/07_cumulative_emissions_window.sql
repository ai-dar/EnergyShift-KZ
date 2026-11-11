-- title: Накопленные выбросы с 1990 г. для стран Центральной Азии и СНГ (SUM OVER — running total)
SELECT c.name, m.year, ROUND(m.co2, 1) AS co2_mt,
       ROUND(SUM(m.co2) OVER (PARTITION BY c.name ORDER BY m.year
                              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 1) AS cumulative_since_1990,
       ROUND(100.0 * m.co2 / SUM(m.co2) OVER (PARTITION BY m.year), 2) AS share_in_group_pct
FROM emissions_annual m
JOIN countries c ON c.country_id = m.country_id
WHERE c.name IN ('Kazakhstan', 'Russia', 'Uzbekistan', 'Azerbaijan', 'Turkmenistan', 'Kyrgyzstan')
  AND m.year IN (1990, 2000, 2010, 2020, 2024)
ORDER BY c.name, m.year;
