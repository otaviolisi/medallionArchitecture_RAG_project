CREATE MATERIALIZED VIEW gold_propositions AS
SELECT
    id,
    "siglaTipo",
    "codTipo",
    numero,
    ano,
    ementa,
    "dataApresentacao",
    "statusDataHora",
    "statusSequencia",
    "statusSiglaOrgao",
    "statusRegime",
    "statusDescricaoTramitacao",
    "statusCodTipoTramitacao",
    "statusDescricaoSituacao",
    "statusCodSituacao",
    "statusDespacho",
    "statusAmbito",
    "statusApreciacao",
    "descricaoTipo",
    "ementaDetalhada",
    "tema_classificado",
    "resumo_executivo",
    keywords,
    loaded_at
FROM silver_propositions
WHERE is_current = true;
