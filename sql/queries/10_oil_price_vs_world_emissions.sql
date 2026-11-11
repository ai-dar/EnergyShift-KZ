-- title: Мировые выбросы (сумма по странам) против цены нефти и температурной аномалии (JOIN с внешними факторами + LAG)
WITH world AS (
    SELECT year, SUM(co2) AS world_co2 FROM emissions_annual GROUP BY year
)
SELECT w.year, ROUND(w.world_co2, 0) AS world_co2_mt,
       ROUND(100.0 * (w.world_co2 / LAG(w.world_co2) OVER (ORDER BY w.year) - 1), 2) AS co2_growth_pct,
       ROUND(f.oil_price, 1) AS oil_price_usd,
       ROUND(100.0 * (f.oil_price / LAG(f.oil_price) OVER (ORDER BY w.year) - 1), 1) AS oil_price_change_pct,
       ROUND(f.temperature_anomaly, 3) AS temperature_anomaly
FROM world w
LEFT JOIN external_factors f ON f.year = w.year
ORDER BY w.year;
