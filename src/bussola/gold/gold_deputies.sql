CREATE materialized VIEW gold_deputies as
WITH social_parsed AS (
    SELECT
        d.id,
        MAX(CASE 
            WHEN url ILIKE '%twitter.com%' OR url ILIKE '%x.com%' 
            THEN url 
        END) AS twitter,
        MAX(CASE 
            WHEN url ILIKE '%facebook.com%' 
            THEN url 
        END) AS facebook,
        MAX(CASE 
            WHEN url ILIKE '%instagram.com%' 
            THEN url 
        END) AS instagram
    FROM silver_deputies d
    LEFT JOIN LATERAL jsonb_array_elements_text(
        CASE
            WHEN d."redeSocial" IS NOT NULL
                AND d."redeSocial" NOT IN ('null', '[]', '')
            THEN d."redeSocial"::jsonb
            ELSE '[]'::jsonb
        END
    ) AS t(url) ON true
    WHERE d.is_current = true
    GROUP BY d.id
)
SELECT
    d.id,
    d."nomeCivil",
    d."nomeEleitoral",
    d.partido,
    d.estado,
    d.email,
    d.situacao,
    d."condicaoEleitoral",
    d.escolaridade,
    d."dataNascimento",
    d."ufNascimento",
    d."municipioNascimento",
    d.sexo,
    d."idLegislatura",
    s.twitter,
    s.facebook,
    s.instagram,
    d.loaded_at
FROM silver_deputies d
LEFT JOIN social_parsed s ON d.id = s.id
WHERE d.is_current = true;

