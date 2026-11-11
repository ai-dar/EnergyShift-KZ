-- title: Сезонность электроэнергетики Казахстана: средняя выработка и выбросы по месяцам (strftime + GROUP BY)
SELECT CAST(strftime('%m', em.date) AS INTEGER)   AS month,
       COUNT(*)                                     AS n_years,
       ROUND(AVG(em.generation_twh), 2)             AS avg_generation_twh,
       ROUND(AVG(em.emissions_mtco2), 2)            AS avg_emissions_mt,
       ROUND(AVG(em.intensity_gco2_kwh), 0)         AS avg_intensity,
       ROUND(MIN(em.emissions_mtco2), 2)            AS min_emissions,
       ROUND(MAX(em.emissions_mtco2), 2)            AS max_emissions
FROM electricity_monthly em
JOIN countries c ON c.country_id = em.country_id
WHERE c.name = 'Kazakhstan' AND em.source = 'Total generation'
GROUP BY month
ORDER BY month;
