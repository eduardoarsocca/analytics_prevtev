# prevtev

Script Python para exportar dados do Firestore (incluindo subcolecoes) para arquivo JSON.

## Objetivo

Este projeto conecta no Firestore via Service Account, percorre uma colecao raiz e exporta:

- documentos da colecao raiz;
- subcolecoes de cada documento, de forma recursiva;
- tipos especiais normalizados para JSON (datetime, bytes, GeoPoint, referencias etc.).

## Estrutura do projeto

```text
.
├── main.py
├── pyproject.toml
├── requirements.txt
├── export/
│   └── export.json
└── scripts/
		└── Python/
				├── export.py
				└── read_json.ipynb
```

## Requisitos

- Python 3.12+
- Credenciais de Service Account com acesso ao Firestore

## Instalacao

Opcao 1: usando venv + pip

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Opcao 2: usando pyproject.toml

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
```

## Configuracao

Crie um arquivo `.env` na raiz do projeto com as variaveis abaixo.

### Variaveis obrigatorias

```env
PROJECT_ID=seu-projeto-gcp
PRIVATE_KEY_ID=sua-private-key-id
PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
CLIENT_EMAIL=service-account@seu-projeto.iam.gserviceaccount.com
CLIENT_ID=seu-client-id
```

### Variaveis opcionais

```env
TYPE=service_account
AUTH_URI=https://accounts.google.com/o/oauth2/auth
TOKEN_URI=https://oauth2.googleapis.com/token
AUTH_PROVIDER_X509_CERT_URL=https://www.googleapis.com/oauth2/v1/certs
CLIENT_X509_CERT_URL=https://www.googleapis.com/robot/v1/metadata/x509/...
UNIVERSE_DOMAIN=googleapis.com

# Nome da colecao raiz (somente o nome, sem barras)
ROOT_COLLECTION=usuarios

# Caminho de saida (relativo a raiz do projeto ou absoluto)
OUT_FILE=export/export.json

# Opcional: rest ou grpc (depende da versao da lib)
FIRESTORE_TRANSPORT=rest
```

## Como executar

Com ambiente virtual ativo:

```bash
python scripts/Python/export.py
```

Se `OUT_FILE` nao for definido, o script gera automaticamente:

```text
<ROOT_COLLECTION>-backup-YYYYMMDD.json
```

Exemplo:

```text
usuarios-backup-20260609.json
```

## Formato da saida

O JSON final segue esta ideia:

```json
{
	"usuarios": {
		"docId1": {
			"campo": "valor",
			"__collections__": {
				"subcolecaoA": {
					"subDoc1": {
						"campo": "valor"
					}
				}
			}
		}
	}
}
```

## Normalizacao de tipos

Durante a exportacao, o script converte automaticamente:

- `datetime` para ISO 8601
- `DocumentReference` para caminho (`colecao/doc/...`)
- `GeoPoint` para `{ "latitude": x, "longitude": y }`
- `bytes` para Base64
- `Decimal` para `float`
- `set/tuple` para lista

## Erros comuns

- `Missing <campo> in service account info (.env)`:
	campo obrigatorio ausente no `.env`.
- Erro de `token_uri` invalido:
	confira se `TOKEN_URI` nao tem virgula no final.
- `ROOT_COLLECTION deve ser apenas o NOME...`:
	use somente o nome da colecao (ex.: `usuarios`, sem `/usuarios` ou `usuarios/...`).

## Notebook auxiliar

O arquivo `scripts/Python/read_json.ipynb` pode ser usado para inspecionar o JSON exportado.
