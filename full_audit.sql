-- Per-course lesson/documentation coverage, including how much of that
-- documentation is real, source-grounded content vs. the model's own
-- general knowledge (Lesson.generation_method, migration d8f3a1c9b274 -
-- see gemini_generator.py's --generate-without-source/--force-general-
-- knowledge). Before this column existed, this audit (and the app itself)
-- had no way to tell the two apart except by re-reading each lesson's
-- markdown disclaimer text.
SELECT
    c.id,
    c.code,
    c.name,
    COALESCE(COUNT(l.id), 0) AS total_lekcii,
    COALESCE(COUNT(l.documentation), 0) AS so_dokumentacija,
    COALESCE(COUNT(l.id) - COUNT(l.documentation), 0) AS prazni,
    COALESCE(COUNT(l.documentation) FILTER (WHERE l.generation_method = 'general_knowledge'), 0) AS bez_izvor_ai_znaenje,
    ROUND(AVG(LENGTH(l.documentation))) AS prosecna_dolzina,
    MIN(LENGTH(l.documentation)) AS min_dolzina
FROM courses c
LEFT JOIN lessons l ON l.course_id = c.id
GROUP BY c.id, c.code, c.name
ORDER BY bez_izvor_ai_znaenje DESC, prazni DESC, total_lekcii ASC, c.name ASC;
