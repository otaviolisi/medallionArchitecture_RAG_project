"""Silver transformation for the parties endpoint."""

from __future__ import annotations

import pandas as pd


def transform(records: list[dict]) -> pd.DataFrame:
    """Flatten bronze parties records into a clean tabular DataFrame.

    Args:
        records: list of {id, summary, detail} dicts from bronze JSON.

    Returns:
        Clean DataFrame ready for Postgres load.
    """
    df = pd.DataFrame(records).drop_duplicates(subset=["id"])

    detail_df = pd.json_normalize(df["detail"]).add_prefix("detail_")

    df_base = pd.concat(
        [df[["id"]].reset_index(drop=True), detail_df],
        axis=1,
    )

    return df_base[
        [
            "id",
            "detail_sigla",
            "detail_nome",
            "detail_uri",
            "detail_status.data",
            "detail_status.idLegislatura",
            "detail_status.situacao",
            "detail_status.totalPosse",
            "detail_status.totalMembros",
            "detail_status.uriMembros",
            "detail_status.lider.uri",
            "detail_status.lider.nome",
            "detail_status.lider.siglaPartido",
            "detail_status.lider.uriPartido",
            "detail_status.lider.uf",
            "detail_status.lider.idLegislatura",
            "detail_status.lider.urlFoto",
            "detail_numeroEleitoral",
            "detail_urlLogo",
            "detail_urlWebSite",
            "detail_urlFacebook",
        ]
    ].rename(
        columns={
            "id": "id",
            "detail_sigla": "sigla",
            "detail_nome": "nome",
            "detail_uri": "uri",
            "detail_status.data": "statusData",
            "detail_status.idLegislatura": "statusIdLegislatura",
            "detail_status.situacao": "statusSituacao",
            "detail_status.totalPosse": "statusTotalPosse",
            "detail_status.totalMembros": "statusTotalMembros",
            "detail_status.uriMembros": "statusUriMembros",
            "detail_status.lider.uri": "liderUri",
            "detail_status.lider.nome": "liderNome",
            "detail_status.lider.siglaPartido": "liderSiglaPartido",
            "detail_status.lider.uriPartido": "liderUriPartido",
            "detail_status.lider.uf": "liderUf",
            "detail_status.lider.idLegislatura": "liderIdLegislatura",
            "detail_status.lider.urlFoto": "liderUrlFoto",
            "detail_numeroEleitoral": "numeroEleitoral",
            "detail_urlLogo": "urlLogo",
            "detail_urlWebSite": "urlWebSite",
            "detail_urlFacebook": "urlFacebook",
        }
    )
