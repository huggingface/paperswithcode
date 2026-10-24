-- ICPR 2024 and ICPR 2026 conference editions (user submissions 1734 and 1736).
-- Dates and venues from https://icpr2024.org/ and https://icpr2026.org/.
-- Hero images are imported separately with backend/database/import_entity_image.py.

INSERT INTO conferences (
    name, slug, short_name, year, url,
    start_date, end_date, venue, location,
    description, image_url, image_credit, hf_url
)
VALUES
(
    'ICPR 2024',
    'icpr-2024',
    'ICPR',
    2024,
    'https://icpr2024.org/',
    '2024-12-01',
    '2024-12-05',
    'Biswa Bangla Convention Centre',
    'Kolkata, India',
    'ICPR (International Conference on Pattern Recognition), the flagship conference of the International Association for Pattern Recognition (IAPR), covers pattern recognition, computer vision, machine learning, document analysis, biometrics, and signal and speech processing. Browse ICPR 2024 papers with code, tasks, and evaluations where available.',
    NULL,
    '[ICPR 2024](https://icpr2024.org/)',
    NULL
),
(
    'ICPR 2026',
    'icpr-2026',
    'ICPR',
    2026,
    'https://icpr2026.org/',
    '2026-08-17',
    '2026-08-22',
    'Lyon Convention Centre',
    'Lyon, France',
    'ICPR (International Conference on Pattern Recognition), the flagship conference of the International Association for Pattern Recognition (IAPR), covers pattern recognition, computer vision, machine learning, document analysis, biometrics, and signal and speech processing. Browse ICPR 2026 papers with code, tasks, and evaluations where available.',
    NULL,
    '[ICPR 2026](https://icpr2026.org/)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    short_name = EXCLUDED.short_name,
    year = EXCLUDED.year,
    url = EXCLUDED.url,
    start_date = EXCLUDED.start_date,
    end_date = EXCLUDED.end_date,
    venue = EXCLUDED.venue,
    location = EXCLUDED.location,
    description = EXCLUDED.description,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    hf_url = EXCLUDED.hf_url,
    updated_at = CURRENT_TIMESTAMP;
