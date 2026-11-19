# ClipeiAki — Revisão de riscos jurídicos (pré-venda pública)

Data: 19/11/2026 · Versão dos documentos: 2026-11-19 · **Não é parecer jurídico.** Levantamento técnico para orientar a
validação por advogado(a) habilitado(a) antes da venda pública. Cada item indica a fonte oficial, o que já foi feito no
produto e o que falta.

Documentos publicados no app (rotas públicas): `/termos`, `/privacidade`, `/cancelamento`, `/conteudo`, `/cookies`,
`/regras-live-ia`, `/contato` — gerados por `python -m web.site_build` a partir de `web/legal_build.py`.

Referência de estrutura usada: Termos e Política do ViceScale (v2.3, 11/11/2026), consultados só para arquitetura de
informação. Nenhum texto, CNPJ, razão social ou dado de pagamento deles foi reaproveitado (há teste automatizado que
procura o CNPJ e a razão social do concorrente nas páginas). Pontos de atenção que identificamos no modelo deles e
evitamos: teto de responsabilidade de 12 meses, presunção de má-fé em chargeback com bloqueio por IP, aceite dos Termos
após a compra e mudança unilateral de preço "a qualquer momento".

## Bloqueios jurídicos para a venda pública (P0)

| # | Risco | Fonte | Situação no produto | O que falta |
|---|---|---|---|---|
| J1 | **Gravação de transmissões da Twitch por ferramenta automatizada (streamlink) fora da API oficial.** Os Termos da Twitch proíbem acessar o serviço por meios automatizados (robôs, scrapers), salvo pelas interfaces oferecidas para isso, e protegem o conteúdo das transmissões. | Twitch Terms of Service — https://legal.twitch.com/en/legal/terms-of-service/ (a página é renderizada por JavaScript; o texto da cláusula de *Prohibited Conduct* foi conferido em fontes secundárias, ex.: conductatlas.com — **confirmar o texto vigente**) | Conexão exige declaração "titular" ou "autorizado" (registrada com data). Regras do Live Monitor proíbem canais de terceiros sem autorização. Landing não mostra streamers. | Parecer sobre o uso do streamlink. Alternativa de menor risco recomendada: **ingest próprio** (o streamer adiciona o ClipeiAki como segundo destino RTMP/SRT no OBS) e **OAuth da Twitch** para provar a titularidade do canal. |
| J2 | **Identificação do fornecedor** ausente (razão social, CNPJ, endereço físico e eletrônico). | Decreto nº 7.962/2013, art. 2º, I e II — https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/decreto/d7962.htm | Todos os campos marcados `PENDENTE_DADO_EMPRESARIAL` nas 7 páginas e no rodapé da landing. | Preencher com os dados reais da Eclyss. |
| J3 | **Encarregado / canal do titular** não indicado. | LGPD, art. 41 — https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm; Res. CD/ANPD nº 2/2022, art. 11 (agente de pequeno porte pode dispensar o encarregado, mas mantém canal de comunicação) | Campo pendente na Política e em Contato. | Indicar encarregado ou declarar o enquadramento como pequeno porte e publicar o canal. |
| J4 | **Confirmação do aceite e do pedido** por e-mail e verificação de e-mail. | Decreto nº 7.962/2013, art. 4º, III e VI | Aceite registrado no banco (versão + data); **não há provedor de e-mail**: o plano pago só é aplicado a e-mail verificado, e a verificação ainda não existe (bloqueio P0 anterior mantido). | Contratar/ativar provedor de e-mail transacional (custo a aprovar). |
| J5 | **Sumário do contrato antes da contratação** e arrependimento com estorno imediato. | Decreto nº 7.962/2013, art. 4º, I e art. 5º, §3º; CDC art. 49, parágrafo único — https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm | Landing mostra preço, recorrência, franquias, cancelamento e 7 dias. Webhook corta o acesso no evento `refund`. | Validar com a Cakto o fluxo de estorno (cartão e Pix) e o sumário exibido no checkout da Cakto. |

## Riscos relevantes (P1)

| # | Risco | Fonte | Situação | Recomendação |
|---|---|---|---|---|
| J6 | Envio de frames e falas ao **Claude do cliente** (Anthropic, EUA) pelo MCP. Mudança de arquitetura: o ClipeiAki **não** usa API de IA; quem pede os dados é o assistente da conta do cliente, por iniciativa dele. | LGPD, art. 33 (hipótese da transferência a confirmar); Termos comerciais/consumidor da Anthropic aplicáveis à conta do cliente | API desligada por padrão (`LIVE_CLAUDE_ENABLED=0`); Política e Regras descrevem o fluxo; cada frame mostrado fica registrado com SHA-256; conexão revogável na conta. | Validar o enquadramento (o titular dos dados da conta é quem compartilha; pessoas que aparecem nas lives são terceiros). |
| J7 | Direitos autorais, de imagem e de voz de terceiros nos cortes; músicas protegidas. | Lei nº 9.610/1998, arts. 7º e 29 — https://www.planalto.gov.br/ccivil_03/leis/l9610.htm; Código Civil, art. 20; Constituição, art. 5º, X e XXVIII, "a" | Declaração de direitos, Política de Conteúdo com procedimento de denúncia, remoção proporcional e contestação. Nada é publicado pelo ClipeiAki. | Validar prazos do procedimento (5 dias úteis para análise; 10 dias para contestação). |
| J8 | Responsabilidade por conteúdo de terceiros hospedado. | Marco Civil da Internet, arts. 19 a 21 — https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12965.htm | Procedimento de denúncia; remoção imediata para conteúdo sexual envolvendo menores. | Validar redação. |
| J9 | Provedor de hospedagem não definido: local dos dados, criptografia em repouso, backup. | LGPD, arts. 37, 39 e 46 | Política declara a lacuna (sem criptografia em repouso própria e sem backup). | Escolher provedor, assinar DPA e atualizar a Política. |
| J10 | Chargeback e contestação: suspensão durante a disputa. | CDC, art. 51, IV | Redigido de forma proporcional (suspende só durante a análise; restabelece se a cobrança for mantida; encerramento só após análise). | Validar com o fluxo real de disputas da Cakto. |
| J11 | Comunicação de incidente de segurança. | Res. CD/ANPD nº 15/2024: 3 dias úteis para ANPD e titulares (prazo em dobro para pequeno porte); registro do incidente por 5 anos — https://www.in.gov.br/en/web/dou/-/resolucao-cd/anpd-n-15-de-24-de-abril-de-2024-556243024 | Prazo citado na Política. **Não há** plano de resposta nem registro de incidentes implementado (processo organizacional). | Criar plano de resposta e registro. |

## Pontos de atenção (P2)

| # | Tema | Fonte | Situação |
|---|---|---|---|
| J23 | Conector OAuth: risco de *consent phishing* (um cliente malicioso se passar por "Claude"). | Boas práticas OAuth 2.1 / especificação de autorização do MCP | Registro dinâmico aceita só retorno HTTPS (ou localhost); consentimento sempre explícito mostrando o domínio de retorno e alerta quando não é domínio do Claude; código de uso único (5 min) com PKCE; access 1 h, refresh com rotação; desconexão na conta; tokens só em hash. | Revisar textos da tela de consentimento. |
| J12 | Cláusulas abusivas (exoneração de responsabilidade, alteração unilateral de preço/conteúdo, cancelamento unilateral). | CDC, art. 51, I, X, XI e XIII | Termos não limitam responsabilidade a valor; preço/franquia só mudam na renovação, com 30 dias de aviso e cancelamento sem multa; suspensão por violação é proporcional e com direito de resposta. **Validar.** |
| J13 | Contrato de adesão: legibilidade e destaque das cláusulas limitativas. | CDC, art. 54, §§3º e 4º | Corpo 17 px (≥ 12 pt), cláusulas limitativas em bloco destacado (`.destaque`). |
| J14 | Registros de acesso por 6 meses. | Marco Civil, art. 15 | **Implementado**: IP + data/hora de login e cadastro em `access_logs`, apagados após 183 dias, preservados após a exclusão da conta. Validar se o escopo (login/cadastro) basta. |
| J15 | Aceite versionado e minimização. | LGPD, arts. 6º, III, 7º, V e VI | **Implementado**: tabela `terms_acceptances` (conta, versão dos Termos e da Política, data, contexto) sem IP/UA; nova versão bloqueia ações contratuais (HTTP 428) até o reaceite. |
| J16 | Direitos do titular. | LGPD, arts. 18 e 19 | **Implementado**: exportação JSON e exclusão da conta (com senha). Correção parcial (nome/@). |
| J17 | Cookies e conteúdo de terceiros. | Guia orientativo de cookies da ANPD (2022) | Só cookie essencial de sessão + `localStorage` de preferências; player da Twitch carregado apenas na página de inspeção (cookies da Twitch). Considerar "clique para carregar" o player. |
| J18 | Menores de idade nos vídeos e como usuários. | LGPD, art. 14; ECA (Lei nº 8.069/1990) | Serviço 18+. Conteúdo de terceiros pode conter menores: tratado na Política de Conteúdo. Validar. |
| J19 | Uso de marcas de terceiros (Twitch, GTA, Claude) e da marca ClipeiAki. | Lei nº 9.279/1996 (propriedade industrial) | Aviso de não afiliação na landing e nos documentos. **Não verificamos** registro da marca "ClipeiAki" no INPI. |
| J20 | Decisões automatizadas. | LGPD, art. 20 | A IA escolhe trechos de vídeo, não decide sobre pessoas; o usuário revisa tudo. Risco baixo. |
| J21 | Retenção de vídeos e cortes sem prazo. | LGPD, arts. 15 e 16 | Ficam até o usuário apagar (declarado na Política). Recomendável definir expiração automática. |
| J22 | Emissão de nota fiscal e obrigações fiscais da assinatura. | Legislação municipal (ISS) | Fora do escopo técnico; confirmar com contador se a Cakto emite ou se a Eclyss emite. |

## Alinhamento código × política (lacunas registradas, nada inventado)

| A Política diz | Código |
|---|---|
| Blocos brutos apagados após ~10 min e ao encerrar | `agent.retention()` e `agent.finalize()` (testado: `test_live.py`) |
| Preview apagado ao encerrar | `agent.finalize()`/`fail_safe()` apagam `preview*.jpg` |
| Frames enviados à IA guardados com SHA-256 até excluir a conta | `live_frames` + cascata na exclusão |
| Pagamento: sem CPF/telefone/endereço | `billing.minimal()` guarda só ids, valores, datas e situação |
| Senha scrypt, tokens só em hash, escopos, validade, limite de requisições | `auth.py`, `tokens.py`, `mcp_server.principal()` |
| Registros de acesso 6 meses | `db.log_access()` (purga a cada gravação) |
| **Não** há criptografia em repouso nem backup | Declarado como lacuna (depende da hospedagem) |
| **Não** há expiração automática de vídeos | Declarado como lacuna |
| **Não** há e-mail transacional | Declarado como bloqueio (J4) |
