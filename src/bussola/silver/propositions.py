"""Silver transformation for the propositions endpoint."""

from __future__ import annotations

import pandas as pd


def transform(records: list[dict]) -> pd.DataFrame:
    """Flatten bronze propositions records into a clean tabular DataFrame.

    Args:
        records: list of {id, summary, detail} dicts from bronze delta JSON.

    Returns:
        Clean DataFrame ready for Postgres load.
    """
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records).drop_duplicates(subset=["id"])

    detail_df = pd.json_normalize(df["detail"]).add_prefix("detail_")

    df_base = pd.concat(
        [df[["id"]].reset_index(drop=True), detail_df],
        axis=1,
    )

    df_final = df_base[
        [
            "id",
            "detail_uri",
            "detail_siglaTipo",
            "detail_codTipo",
            "detail_numero",
            "detail_ano",
            "detail_ementa",
            "detail_dataApresentacao",
            "detail_uriOrgaoNumerador",
            "detail_statusProposicao.dataHora",
            "detail_statusProposicao.sequencia",
            "detail_statusProposicao.siglaOrgao",
            "detail_statusProposicao.uriOrgao",
            "detail_statusProposicao.uriUltimoRelator",
            "detail_statusProposicao.regime",
            "detail_statusProposicao.descricaoTramitacao",
            "detail_statusProposicao.codTipoTramitacao",
            "detail_statusProposicao.descricaoSituacao",
            "detail_statusProposicao.codSituacao",
            "detail_statusProposicao.despacho",
            "detail_statusProposicao.url",
            "detail_statusProposicao.ambito",
            "detail_statusProposicao.apreciacao",
            "detail_uriAutores",
            "detail_descricaoTipo",
            "detail_ementaDetalhada",
            "detail_keywords",
            "detail_uriPropPrincipal",
            "detail_uriPropAnterior",
            "detail_uriPropPosterior",
            "detail_urlInteiroTeor",
            "detail_urnFinal",
        ]
    ].rename(
        columns={
            "id": "id",
            "detail_uri": "uri",
            "detail_siglaTipo": "siglaTipo",
            "detail_codTipo": "codTipo",
            "detail_numero": "numero",
            "detail_ano": "ano",
            "detail_ementa": "ementa",
            "detail_dataApresentacao": "dataApresentacao",
            "detail_uriOrgaoNumerador": "uriOrgaoNumerador",
            "detail_statusProposicao.dataHora": "statusDataHora",
            "detail_statusProposicao.sequencia": "statusSequencia",
            "detail_statusProposicao.siglaOrgao": "statusSiglaOrgao",
            "detail_statusProposicao.uriOrgao": "statusUriOrgao",
            "detail_statusProposicao.uriUltimoRelator": "statusUriUltimoRelator",
            "detail_statusProposicao.regime": "statusRegime",
            "detail_statusProposicao.descricaoTramitacao": "statusDescricaoTramitacao",
            "detail_statusProposicao.codTipoTramitacao": "statusCodTipoTramitacao",
            "detail_statusProposicao.descricaoSituacao": "statusDescricaoSituacao",
            "detail_statusProposicao.codSituacao": "statusCodSituacao",
            "detail_statusProposicao.despacho": "statusDespacho",
            "detail_statusProposicao.url": "statusUrl",
            "detail_statusProposicao.ambito": "statusAmbito",
            "detail_statusProposicao.apreciacao": "statusApreciacao",
            "detail_uriAutores": "uriAutores",
            "detail_descricaoTipo": "descricaoTipo",
            "detail_ementaDetalhada": "ementaDetalhada",
            "detail_keywords": "keywords",
            "detail_uriPropPrincipal": "uriPropPrincipal",
            "detail_uriPropAnterior": "uriPropAnterior",
            "detail_uriPropPosterior": "uriPropPosterior",
            "detail_urlInteiroTeor": "urlInteiroTeor",
            "detail_urnFinal": "urnFinal",
        }
    )

    df_final["dataApresentacao"] = pd.to_datetime(
        df_final["dataApresentacao"], errors="coerce"
    )
    df_final["statusDataHora"] = pd.to_datetime(
        df_final["statusDataHora"], errors="coerce"
    )

    return df_final
