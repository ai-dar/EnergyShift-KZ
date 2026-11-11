-- title: Казахстан: энергопотребление и выбросы по годам (JOIN трёх таблиц)
-- Соединяем справочник стран, энергобаланс и выбросы; считаем углеродоёмкость энергии.
SELECT c.name                                   AS country,
       e.year,
       ROUND(e.primary_energy_consumption, 1)   AS energy_twh,
       ROUND(m.co2, 1)                          AS co2_mt,
       ROUND(m.co2_per_capita, 2)               AS co2_per_capita,
       ROUND(e.fossil_share_energy, 1)          AS fossil_share_pct,
       ROUND(m.co2 * 1000.0 / e.primary_energy_consumption, 1) AS kt_co2_per_twh
FROM countries c
JOIN energy_annual    e ON e.country_id = c.country_id
JOIN emissions_annual m ON m.country_id = c.country_id AND m.year = e.year
WHERE c.name = 'Kazakhstan'
ORDER BY e.year;
