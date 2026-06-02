CREATE MATERIALIZED VIEW gold_votings AS
SELECT
    id,
    data,
    "dataHoraRegistro",
    "siglaOrgao",
    "proposicaoObjeto",
    descricao,
    aprovacao,
    loaded_at
FROM silver_votings
WHERE is_current = true;
