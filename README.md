# Mapas de frete Sisfrete

Aplicacao local para visualizar demanda, transportadora mais barata e prazo medio por UF e municipio. As consultas usam os indices `quotations-*-2026.09` e filtram obrigatoriamente por `nf.cliente`.

## Requisitos

- Python 3.9 ou superior
- Acesso de rede ao cluster OpenSearch
- Credenciais Sisfrete

Nao ha dependencias externas de Python. O mapa usa Leaflet e as malhas geograficas carregadas por CDN.

## Configuracao

1. Copie `.env.example` para `.env`.
2. Preencha `SISFRETE_USER` e `SISFRETE_PASS`.
3. Ajuste `SISFRETE_URL` somente se estiver usando outro cluster.

O arquivo `.env` e ignorado pelo Git e nao deve ser compartilhado.

## Execucao

No diretorio deste projeto:

```powershell
python proxy.py
```

Abra no navegador:

```text
http://127.0.0.1:8000/mapas-frete.html
```

Tambem e possivel usar `http://127.0.0.1:8000/`.

Se a porta 8000 estiver ocupada, encerre a instancia anterior do proxy antes de iniciar uma nova. O proxy precisa ser reiniciado depois de qualquer alteracao no `.env` ou no `proxy.py`.

## Uso

1. Informe o codigo obrigatorio do cliente, correspondente a `nf.cliente`.
2. Escolha a data final dentro de setembro de 2026.
3. Escolha uma janela fixa de 7 ou 15 dias.
4. Clique em **Carregar mapa**.
5. Clique em uma UF para detalhar os municipios e use as abas para trocar a analise.

O cliente e o periodo sao aplicados a todas as consultas. O proxy tambem valida o filtro de cliente recebido antes de encaminhar buscas e contagens ao OpenSearch.

## Endpoints locais

- `GET /`, `/index.html` e `/mapas-frete.html`: interface do mapa
- `POST /os/quotations-*-2026.09/_search`: consultas de leitura
- `POST /os/quotations-*-2026.09/_count`: contagens de leitura
- `POST /os/quotations-*-2026.09/_msearch`: consultas agrupadas de leitura

O proxy bloqueia caminhos fora dos indices permitidos e nao expoe as credenciais ao navegador.
