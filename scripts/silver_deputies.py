import pandas as pd

df=pd.read_json(r"E:\Projeto_medalion\AI_DE_politics_Brazil\medallionArchitecture_RAG_project\data\bronze\deputies\snapshot_2026-05-18.json")
df_remove_duplicates=df.drop_duplicates(subset=['id'])

detail_df = pd.json_normalize(
    df_remove_duplicates["detail"]).add_prefix("detail_")

summary_df=pd.json_normalize(
    df_remove_duplicates["summary"]).add_prefix("summary_")


df_base=pd.concat(
    [
        df_remove_duplicates[["id"]].reset_index(drop=True),
        detail_df,
        summary_df
    ],
    axis=1
)
df_final = df_base[
    [
    'id',
    'detail_id',
    'detail_uri',
    'detail_nomeCivil',
    'detail_cpf',
    'detail_sexo',
    'detail_urlWebsite',
    'detail_redeSocial',
    'detail_dataNascimento',
    'detail_dataFalecimento',
    'detail_ufNascimento',
    'detail_municipioNascimento',
    'detail_escolaridade',
    'detail_ultimoStatus.id',
    'detail_ultimoStatus.uri',
    'detail_ultimoStatus.nome',
    'detail_ultimoStatus.siglaPartido',
    'detail_ultimoStatus.uriPartido',
    'detail_ultimoStatus.siglaUf',
    'detail_ultimoStatus.idLegislatura',
    'detail_ultimoStatus.urlFoto',
    'detail_ultimoStatus.email',
    'detail_ultimoStatus.data',
    'detail_ultimoStatus.nomeEleitoral',
    'detail_ultimoStatus.gabinete.nome',
    'detail_ultimoStatus.gabinete.predio',
    'detail_ultimoStatus.gabinete.sala',
    'detail_ultimoStatus.gabinete.andar',
    'detail_ultimoStatus.gabinete.telefone',
    'detail_ultimoStatus.gabinete.email',
    'detail_ultimoStatus.situacao',
    'detail_ultimoStatus.condicaoEleitoral',
    'detail_ultimoStatus.descricaoStatus',
    'summary_id',
    'summary_uri',
    'summary_nome',
    'summary_siglaPartido',
    'summary_uriPartido',
    'summary_siglaUf',
    'summary_idLegislatura',
    'summary_urlFoto',
    'summary_email'
    ]
].rename(columns={
    "id": "deputado_id",

    "detail_id": "id",
    "detail_uri": "uri",
    "detail_nomeCivil": "nomeCivil",
    "detail_cpf": "cpf",
    "detail_sexo": "sexo",
    "detail_urlWebsite": "urlWebsite",
    "detail_redeSocial": "redeSocial",
    "detail_dataNascimento": "dataNascimento",
    "detail_dataFalecimento": "dataFalecimento",
    "detail_ufNascimento": "ufNascimento",
    "detail_municipioNascimento": "municipioNascimento",
    "detail_escolaridade": "escolaridade",

    "detail_ultimoStatus.id": "ultimoStatusId",
    "detail_ultimoStatus.uri": "ultimoStatusUri",
    "detail_ultimoStatus.nome": "ultimoStatusNome",
    "detail_ultimoStatus.siglaPartido": "partido",
    "detail_ultimoStatus.uriPartido": "uriPartido",
    "detail_ultimoStatus.siglaUf": "estado",
    "detail_ultimoStatus.idLegislatura": "idLegislatura",
    "detail_ultimoStatus.urlFoto": "urlFoto",
    "detail_ultimoStatus.email": "email",
    "detail_ultimoStatus.data": "dataStatus",
    "detail_ultimoStatus.nomeEleitoral": "nomeEleitoral",

    "detail_ultimoStatus.gabinete.nome": "gabineteNome",
    "detail_ultimoStatus.gabinete.predio": "gabinetePredio",
    "detail_ultimoStatus.gabinete.sala": "gabineteSala",
    "detail_ultimoStatus.gabinete.andar": "gabineteAndar",
    "detail_ultimoStatus.gabinete.telefone": "gabineteTelefone",
    "detail_ultimoStatus.gabinete.email": "gabineteEmail",

    "detail_ultimoStatus.situacao": "situacao",
    "detail_ultimoStatus.condicaoEleitoral": "condicaoEleitoral",
    "detail_ultimoStatus.descricaoStatus": "descricaoStatus",

    "summary_id": "resumoId",
    "summary_uri": "resumoUri",
    "summary_nome": "resumoNome",
    "summary_siglaPartido": "resumoPartido",
    "summary_uriPartido": "resumoUriPartido",
    "summary_siglaUf": "resumoEstado",
    "summary_idLegislatura": "resumoIdLegislatura",
    "summary_urlFoto": "resumoUrlFoto",
    "summary_email": "resumoEmail"
})

print(df_final.head(10))

