SELECT
    c.id,
    c.code,
    c.name,
    COALESCE(COUNT(l.id), 0) AS total_lekcii,
    COALESCE(COUNT(l.documentation), 0) AS so_dokumentacija,
    COALESCE(COUNT(l.id) - COUNT(l.documentation), 0) AS prazni,
    ROUND(AVG(LENGTH(l.documentation))) AS prosecna_dolzina,
    MIN(LENGTH(l.documentation)) AS min_dolzina
FROM courses c
LEFT JOIN lessons l ON l.course_id = c.id
GROUP BY c.id, c.code, c.name
ORDER BY prazni DESC, total_lekcii ASC, c.name ASC;
