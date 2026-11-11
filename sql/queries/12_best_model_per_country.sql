-- title: Лучшая модель прогноза по каждой стране из таблицы model_metrics (ROW_NUMBER) и выигрыш у Naive
WITH ranked AS (
    SELECT c.name, mm.frequency, mm.model, mm.mase, mm.mape, mm.train_time_s,
           ROW_NUMBER() OVER (PARTITION BY c.name, mm.frequency ORDER BY mm.mase) AS rn,
           MAX(CASE WHEN mm.model = 'Naive' THEN mm.mase END) OVER (PARTITION BY c.name, mm.frequency) AS naive_mase
    FROM model_metrics mm
    JOIN countries c ON c.country_id = mm.country_id
    WHERE mm.target = 'co2' AND mm.mase IS NOT NULL
)
SELECT name, frequency, model AS best_model, ROUND(mase, 3) AS best_mase, ROUND(mape, 2) AS best_mape,
       ROUND(naive_mase, 3) AS naive_mase, ROUND(100.0 * (1 - mase / naive_mase), 1) AS gain_vs_naive_pct,
       ROUND(train_time_s, 3) AS train_time_s
FROM ranked
WHERE rn = 1
ORDER BY gain_vs_naive_pct DESC;
