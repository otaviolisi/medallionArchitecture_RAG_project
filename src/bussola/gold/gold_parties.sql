CREATE MATERIALIZED VIEW gold_parties AS
SELECT
    id,
    sigla,
    nome,
    "statusData",
    "statusIdLegislatura",
    "statusSituacao",
    "statusTotalPosse",
    "statusTotalMembros",
    "liderNome",
    "liderSiglaPartido",
    "liderUriPartido",
    "liderUf",
    "liderIdLegislatura",
    "urlWebSite",
    "urlFacebook",
    loaded_at
FROM silver_parties;
