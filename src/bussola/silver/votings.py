"""Silver transformation for the votings endpoint.

Bronze records are already flat (no summary/detail wrapper), so the
transform is minimal: type casting and column selection only.
"""

from __future__ import annotations

import pandas as pd


def transform(records: list[dict]) -> pd.DataFrame:
    """Clean and type-cast bronze votings records.

    Args:
        records: flat list of voting dicts from a bronze delta file.

    Returns:
        Clean DataFrame ready for Postgres load.
    """
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records).drop_duplicates(subset=["id"])

    df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.date
    df["dataHoraRegistro"] = pd.to_datetime(df["dataHoraRegistro"], errors="coerce")
    df["aprovacao"] = df["aprovacao"].astype("Int64")

    return df[
        [
            "id",
            "uri",
            "data",
            "dataHoraRegistro",
            "siglaOrgao",
            "uriOrgao",
            "uriEvento",
            "proposicaoObjeto",
            "uriProposicaoObjeto",
            "descricao",
            "aprovacao",
        ]
    ]
