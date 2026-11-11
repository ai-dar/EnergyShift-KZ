-- title: Казахстан и страны-аналоги: CO₂ на душу по десятилетиям (CTE)
WITH peers AS (
    SELECT country_id, name FROM countries
    WHERE name IN ('Kazakhstan', 'Russia', 'Uzbekistan', 'Azerbaijan', 'Turkmenistan', 'Kyrgyzstan',
                   'Australia', 'Canada', 'Norway', 'Saudi Arabia', 'Poland', 'China')
),
by_decade AS (
    SELECT p.name, (m.year / 10) * 10 AS decade,
           AVG(m.co2_per_capita) AS avg_pc, AVG(m.co2) AS avg_co2
    FROM peers p JOIN emissions_annual m ON m.country_id = p.country_id
    GROUP BY p.name, decade
)
SELECT name,
       ROUND(MAX(CASE WHEN decade = 1990 THEN avg_pc END), 2) AS pc_1990s,
       ROUND(MAX(CASE WHEN decade = 2000 THEN avg_pc END), 2) AS pc_2000s,
       ROUND(MAX(CASE WHEN decade = 2010 THEN avg_pc END), 2) AS pc_2010s,
       ROUND(MAX(CASE WHEN decade = 2020 THEN avg_pc END), 2) AS pc_2020s,
       ROUND(MAX(CASE WHEN decade = 2020 THEN avg_co2 END), 1) AS co2_2020s_mt
FROM by_decade
GROUP BY name
ORDER BY pc_2020s DESC;
