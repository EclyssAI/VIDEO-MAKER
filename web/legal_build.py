"""Gera as páginas jurídicas públicas (web/static/legal/*.html) a partir de uma fonte única.
Uso: python -m web.legal_build

Regras de redação seguidas:
- texto original do ClipeiAki (a estrutura do concorrente foi só referência de organização);
- descreve SOMENTE o que o sistema implementa hoje; o que não existe aparece como "não disponível" ou como lacuna;
- dados da empresa ausentes ficam marcados como PENDENTE_DADO_EMPRESARIAL (nunca inventados);
- nenhuma cláusula afasta direitos do consumidor (CDC arts. 6º, 25, 49, 51) — limitações só "nos limites da lei";
- cláusulas que limitam direitos aparecem em destaque (CDC art. 54, §4º).
A versão (data de vigência) vem de web/legal.py e é a mesma registrada no aceite."""
import html, pathlib
from .legal import TERMS_VERSION, PRIVACY_VERSION, DOCS

OUT = pathlib.Path(__file__).resolve().parent / "static/legal"
P = "PENDENTE_DADO_EMPRESARIAL"
EMP = f'<mark class="pend">{P}</mark>'
VERSIONS = {"termos": TERMS_VERSION, "privacidade": PRIVACY_VERSION}
DEFAULT_VERSION = TERMS_VERSION


def fornecedor():
    return f"""<dl class="ident">
  <dt>Fornecedor</dt><dd>Eclyss — razão social: {EMP}</dd>
  <dt>CNPJ</dt><dd>{EMP}</dd>
  <dt>Endereço físico</dt><dd>{EMP}</dd>
  <dt>E-mail de atendimento</dt><dd>{EMP} (canal oficial de suporte, cancelamento e privacidade)</dd>
  <dt>Encarregado de dados (DPO)</dt><dd>{EMP} — nome e e-mail do encarregado ou, se a Eclyss for agente de pequeno porte e optar por não indicar encarregado (Res. CD/ANPD nº 2/2022, art. 11), o canal de comunicação com o titular</dd>
</dl>"""


def plans_table():
    import yaml
    P = yaml.safe_load((pathlib.Path(__file__).resolve().parent.parent / "config/plans.yaml").read_text())["plans"]
    c, t = P["creator"], P["studio"]; brl = lambda v: f"R$ {v:.2f}".replace(".", ",")
    rows = [("Preço (recorrência mensal)", f"{brl(c['price_brl'])}/mês", f"{brl(t['price_brl'])}/mês"),
            ("Transmissões monitoradas ao mesmo tempo", f"até {c['live_slots']}", f"até {t['live_slots']}"),
            ("Horas de monitoramento por mês", f"{c['live_hours_per_month']} h", f"{t['live_hours_per_month']} h"),
            ("Cortes de live por mês", str(c["live_clips_per_month"]), str(t["live_clips_per_month"])),
            ("Análise dos momentos pelo Claude do próprio usuário (MCP)", "incluída (usa o plano do Claude do usuário)", "incluída (usa o plano do Claude do usuário)"),
            ("Duração máxima de cada sessão de monitoramento", f"{c['live_max_minutes'] / 60:g} h", f"{t['live_max_minutes'] / 60:g} h"),
            ("Projetos por envio de arquivo por mês", f"{c['projects_per_month']} (até {c['minutes_per_month']} min)", f"{t['projects_per_month']} (até {t['minutes_per_month']:,} min)".replace(",", ".")),
            ("Duração e tamanho máximos por vídeo enviado", f"{c['max_video_minutes']} min · {c['max_upload_mb'] // 1024} GB", f"{t['max_video_minutes']} min · {t['max_upload_mb'] // 1024} GB"),
            ("Cortes sugeridos por vídeo enviado", f"até {c['clips_per_project']}", f"até {t['clips_per_project']}"),
            ("Efeitos premium (SFX, zoom no pico)", "incluídos" if c["premium_assets"] else "—", "incluídos" if t["premium_assets"] else "—")]
    body = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{d}</td></tr>" for a, b, d in rows)
    return f'<table class="tbl"><thead><tr><th>Item</th><th>{c["label"]}</th><th>{t["label"]}</th></tr></thead><tbody>{body}</tbody></table>'


DOC = {}

DOC["termos"] = ("Termos de Uso", f"""
<p class="lead">Estes Termos regulam o uso do <strong>ClipeiAki</strong>, serviço on-line da Eclyss que transforma vídeos longos e
transmissões ao vivo em cortes verticais para revisão e download. Ao criar a conta você declara ter lido e aceitado estes Termos e a
<a href="/privacidade">Política de Privacidade</a>. O aceite fica registrado com a data e a versão do documento.</p>

<h2 id="t1">1. Quem fornece o serviço</h2>
{fornecedor()}

<h2 id="t2">2. O que o ClipeiAki faz hoje</h2>
<p>Funcionalidades <strong>disponíveis</strong>:</p>
<ul>
  <li><strong>Projetos por envio de arquivo</strong>: você envia um vídeo (MP4, MOV, MKV, WEBM ou TS); o sistema mede o áudio, transcreve a fala,
  sugere trechos e renderiza cortes verticais 1080×1920 a 30 fps com legenda, enquadramento de webcam e moldura.</li>
  <li><strong>Revisão</strong>: preview de cada corte, edição de título, descrição, hashtags e legendas, nova renderização, aprovação ou descarte.
  O download só é liberado após a sua aprovação.</li>
  <li><strong>Biblioteca</strong>: histórico dos cortes aprovados, com download e texto do post.</li>
  <li><strong>Live Monitor</strong>: monitoramento de transmissões da <strong>Twitch</strong> conectadas por você, gravadas no servidor em blocos de 10 segundos,
  com detecção local de momentos (picos de áudio, mudanças de imagem e palavras de reação), preview do último frame gravado e criação de cortes.
  A quantidade de transmissões simultâneas, as horas e os cortes por mês dependem do plano (seção 4).</li>
  <li><strong>Integração MCP</strong>: conecte o seu Claude (claude.ai, Claude Desktop ou Claude Code) por OAuth ou token pessoal para acompanhar as
  transmissões, ver as evidências dos momentos e decidir, criar e aprovar cortes por chat, com permissões por escopo.</li>
</ul>
<p><strong>Análise por IA</strong>: o ClipeiAki não contrata nem usa API de IA para analisar seus vídeos. A análise contextual dos momentos
é feita, se você quiser, pelo <strong>seu próprio Claude</strong> (Anthropic), conectado ao ClipeiAki por MCP com a sua autorização
(conector OAuth). O uso desse assistente é regido pelo seu contrato com a Anthropic e conta no seu plano do Claude.</p>
<p>Funcionalidades <strong>não disponíveis</strong>: postagem automática em redes sociais (não oferecida); monitoramento de YouTube, Kick ou
outras plataformas (em desenvolvimento).
<strong>Não oferecemos monitoramento ilimitado nem 24 horas por dia</strong>: cada sessão tem duração máxima e há franquia mensal.</p>

<h2 id="t3">3. Conta</h2>
<ul>
  <li>Você precisa ter <strong>18 anos ou mais</strong> e capacidade civil para contratar.</li>
  <li>Os dados informados devem ser verdadeiros. A senha é pessoal; avise o suporte se suspeitar de acesso indevido.</li>
  <li>Tokens de API dão acesso à sua conta conforme os escopos escolhidos. Guarde-os com cuidado; você pode revogá-los a qualquer momento.
  Ações feitas com o seu token são consideradas feitas por você.</li>
</ul>

<h2 id="t4">4. Planos, preços e franquias</h2>
{plans_table()}
<p>Os limites acima são aplicados automaticamente pelo sistema e exibidos no painel com o consumo do mês. Franquias não usadas
<strong>não acumulam</strong> para o mês seguinte. O valor cobrado é o exibido no checkout no momento da compra.</p>
<p class="destaque"><strong>Alteração de preço ou de franquia</strong>: será comunicada por e-mail e no painel com pelo menos 30 dias de antecedência e
só vale a partir da renovação seguinte. Se não concordar, você pode cancelar antes da renovação, sem multa. Nada muda no período já pago.</p>

<h2 id="t5">5. Pagamento pela Cakto</h2>
<p>Os pagamentos são processados pela <strong>Cakto</strong>, intermediadora contratada pela Eclyss. Os dados de pagamento (cartão, Pix, CPF, endereço de
cobrança) são informados diretamente no checkout da Cakto e tratados por ela. O ClipeiAki recebe da Cakto apenas o necessário para liberar
o acesso: e-mail do comprador, oferta contratada, situação do pagamento e datas. A assinatura é renovada mensalmente até o cancelamento.</p>
<p>O acesso pago é liberado para a conta do ClipeiAki com o <strong>mesmo e-mail</strong> usado na compra e com e-mail verificado.</p>

<h2 id="t6">6. Cancelamento, arrependimento, reembolso e chargeback</h2>
<p>Regras completas na <a href="/cancelamento">Política de Cancelamento, Arrependimento e Reembolso</a>. Em resumo:</p>
<ul>
  <li><strong>Arrependimento</strong>: até 7 dias da contratação, com devolução integral (CDC, art. 49).</li>
  <li><strong>Cancelamento</strong>: a qualquer momento, sem multa; o acesso continua até o fim do período já pago.</li>
  <li><strong>Falha do serviço</strong>: se o serviço não funcionar como contratado, você pode pedir correção, abatimento proporcional ou restituição (CDC, art. 20).</li>
  <li><strong>Chargeback</strong>: durante a contestação o acesso pago fica suspenso; ele volta se a contestação for resolvida a favor da manutenção da assinatura.</li>
</ul>

<h2 id="t7">7. Seu conteúdo e direitos de terceiros</h2>
<p>Você continua dono do que envia e dos cortes gerados. Para processar, armazenar e exibir os arquivos para você, concede à Eclyss uma licença
limitada, não exclusiva e gratuita, <strong>apenas para operar o serviço</strong> durante o tempo em que o conteúdo estiver na sua conta.
Não usamos seu conteúdo para publicidade nem para treinar modelos de IA próprios.</p>
<p>Você declara ter os direitos necessários sobre vídeos, imagens, vozes e músicas que envia ou monitora. Regras e procedimento de denúncia
estão na <a href="/conteudo">Política de Conteúdo e Direitos de Terceiros</a>.</p>

<h2 id="t8">8. Live Monitor, IA e integrações</h2>
<p>Ao conectar uma transmissão você declara ser o titular do canal ou ter autorização do titular. O uso deve respeitar as regras da plataforma
de origem. Ao conectar o seu Claude via MCP, você autoriza que ele receba, a pedido dele, os frames, a transcrição e os dados dos momentos das
suas transmissões, e que crie e aprove cortes conforme os escopos autorizados; você pode desconectar a qualquer momento. Detalhes, limites técnicos e limitações da identificação automática estão nas
<a href="/regras-live-ia">Regras do Live Monitor, da IA e das Integrações</a>.</p>
<p class="destaque"><strong>A identificação automática de momentos pode errar</strong>: pode deixar de detectar um momento relevante, sugerir trechos sem
interesse ou cortar no ponto errado. Por isso todo corte passa pela sua revisão antes do download. O ClipeiAki não garante visualizações,
alcance, monetização ou viralização.</p>

<h2 id="t9">9. Condutas proibidas</h2>
<ul>
  <li>Monitorar, gravar ou cortar transmissões de terceiros sem autorização do titular.</li>
  <li>Enviar conteúdo ilícito, que viole direitos autorais, de imagem ou de voz, ou que envolva exploração de menores, violência real ou discurso de ódio.</li>
  <li>Tentar acessar dados de outras contas, contornar limites do plano, sobrecarregar o serviço, fazer engenharia reversa para fins de ataque ou revender o acesso.</li>
  <li>Compartilhar a conta ou tokens com terceiros não autorizados.</li>
</ul>
<p>Em caso de violação, podemos, <strong>de forma proporcional à gravidade</strong>: remover o conteúdo, suspender o Live Monitor ou tokens, suspender a conta
ou encerrá-la nos casos graves ou de reincidência. Você será informado do motivo e poderá contestar pelo canal de suporte, salvo quando a lei
ou ordem judicial impedir. Em caso de encerramento por violação, valores de períodos não usados serão tratados conforme a lei.</p>

<h2 id="t10">10. Disponibilidade e serviços de terceiros</h2>
<p>Trabalhamos para manter o serviço disponível, mas pode haver interrupções para manutenção, por falhas de infraestrutura ou por mudanças em
serviços de terceiros (Twitch, Cakto, provedores de hospedagem e o Claude da sua conta). Se uma plataforma de origem mudar ou bloquear o acesso às transmissões,
o Live Monitor pode ficar indisponível para aquela plataforma; nesse caso avisaremos no painel e, se a indisponibilidade comprometer o que foi
contratado, você terá direito às medidas da seção 6.</p>

<h2 id="t11">11. Responsabilidade</h2>
<p class="destaque">A Eclyss responde pelos danos causados por falhas do serviço nos termos do Código de Defesa do Consumidor. Nada nestes Termos afasta
direitos que a lei garante ao consumidor. Não respondemos por conteúdo enviado ou monitorado por você sem os direitos necessários, por decisões
de terceiros (como remoção de vídeos pelas redes sociais) nem por resultados de audiência, salvo quando decorrerem de falha nossa.</p>

<h2 id="t12">12. Encerramento pelo usuário e exclusão de dados</h2>
<p>Você pode excluir a conta a qualquer momento em <em>Conta e plano → Seus dados</em>. A exclusão apaga projetos, cortes, transmissões conectadas,
tokens e arquivos. Assinaturas devem ser canceladas na Cakto para interromper a cobrança. Veja <a href="/contato">Contato, Suporte e Exclusão de Dados</a>.</p>

<h2 id="t13">13. Não afiliação</h2>
<p>O ClipeiAki não é afiliado, patrocinado ou endossado pela Twitch Interactive, Amazon, YouTube/Google, TikTok/ByteDance, Instagram/Meta,
Anthropic, Rockstar Games ou Take-Two Interactive. Marcas citadas pertencem aos seus titulares e são usadas apenas para identificar plataformas
compatíveis ou conteúdos de jogos.</p>

<h2 id="t14">14. Alterações destes Termos</h2>
<p>Alterações relevantes ganham nova versão e data. Você será avisado no painel e, para continuar usando recursos que dependem do contrato,
precisará aceitar a nova versão; se não concordar, pode cancelar sem multa. Versões anteriores ficam disponíveis mediante solicitação ao suporte.</p>

<h2 id="t15">15. Lei aplicável e foro</h2>
<p>Aplica-se a lei brasileira. Fica eleito o foro do domicílio do consumidor (CDC, art. 101, I). Antes de recorrer ao Judiciário, você pode
procurar o suporte ou a plataforma consumidor.gov.br.</p>
""")

DOC["privacidade"] = ("Política de Privacidade", f"""
<p class="lead">Esta Política explica quais dados pessoais o ClipeiAki trata, por quê, com quem compartilha, por quanto tempo guarda e como você
exerce seus direitos, conforme a Lei Geral de Proteção de Dados (Lei nº 13.709/2018 — LGPD).</p>

<h2 id="p1">1. Controlador e encarregado</h2>
{fornecedor()}
<p>Você também pode apresentar petição à Autoridade Nacional de Proteção de Dados (ANPD) — gov.br/anpd.</p>

<h2 id="p2">2. Dados que tratamos</h2>
<table class="tbl">
  <thead><tr><th>Categoria</th><th>Dados</th><th>Finalidade</th><th>Base legal (LGPD)</th></tr></thead>
  <tbody>
    <tr><td>Conta</td><td>e-mail, nome (opcional), @ do canal (opcional), hash da senha (scrypt)</td><td>criar e manter a conta, autenticar, assinar os cortes com o seu @</td><td>execução de contrato (art. 7º, V)</td></tr>
    <tr><td>Sessão</td><td>cookie de sessão aleatório (guardamos só o hash), validade de 30 dias</td><td>manter você conectado</td><td>execução de contrato (art. 7º, V)</td></tr>
    <tr><td>Aceite dos documentos</td><td>versão dos Termos e da Política, data e hora, contexto (cadastro ou reaceite)</td><td>provar o aceite</td><td>execução de contrato e exercício regular de direitos (art. 7º, V e VI)</td></tr>
    <tr><td>Registros de acesso</td><td>endereço IP, data e hora de login e cadastro</td><td>cumprir o Marco Civil da Internet (Lei nº 12.965/2014, art. 15) e prevenir fraude</td><td>obrigação legal (art. 7º, II)</td></tr>
    <tr><td>Conteúdo enviado</td><td>vídeos, áudio, imagens e vozes de quem aparece neles, transcrição da fala</td><td>gerar cortes, legendas e previews</td><td>execução de contrato (art. 7º, V)</td></tr>
    <tr><td>Live Monitor</td><td>canal conectado, declaração de direitos (titular/autorizado) com data, blocos de vídeo da transmissão, frames, transcrição, sinais medidos (volume, mudança de imagem), momentos detectados</td><td>monitorar a transmissão que você conectou e gerar cortes</td><td>execução de contrato (art. 7º, V)</td></tr>
    <tr><td>Evidências da revisão</td><td>frames mostrados ao seu Claude pelo MCP (com SHA-256), transcrição da janela e a decisão registrada</td><td>mostrar a você exatamente o que foi analisado e por quem</td><td>execução de contrato (art. 7º, V)</td></tr>
    <tr><td>Uso e limites</td><td>contagem mensal de projetos, minutos, horas de live e cortes</td><td>aplicar a franquia do plano</td><td>execução de contrato (art. 7º, V)</td></tr>
    <tr><td>Integração MCP (seu Claude)</td><td>tokens pessoais e conexões OAuth: nome do aplicativo cliente, escopos, validade, último uso (tokens e códigos guardados só como hash)</td><td>autenticar o Claude que você conectou</td><td>execução de contrato (art. 7º, V)</td></tr>
    <tr><td>Pagamento</td><td>e-mail do comprador, oferta, situação, valores e datas do pagamento (sem CPF, telefone, endereço ou cartão)</td><td>liberar e manter o acesso pago</td><td>execução de contrato (art. 7º, V)</td></tr>
  </tbody>
</table>
<p>Pessoas que aparecem nos vídeos (streamers, convidados) podem ter imagem e voz tratadas. Quem envia ou conecta o conteúdo declara ter
autorização para isso (ver <a href="/conteudo">Política de Conteúdo</a>). Não tratamos dados sensíveis de forma intencional e não usamos
reconhecimento facial para identificar pessoas: a detecção de rosto serve apenas para enquadrar a webcam no corte.</p>

<h2 id="p3">3. O que não fazemos</h2>
<ul>
  <li>Não vendemos dados pessoais.</li>
  <li>Não usamos cookies de publicidade, pixels de rastreamento ou ferramentas de analytics de terceiros.</li>
  <li>Não usamos seu conteúdo para treinar modelos de IA próprios.</li>
  <li>Não publicamos nada nas suas redes sociais.</li>
</ul>

<h2 id="p4">4. Com quem compartilhamos (operadores)</h2>
<ul>
  <li><strong>Hospedagem e armazenamento</strong>: {EMP} (provedor de nuvem ainda não definido; será identificado aqui antes do lançamento).</li>
  <li><strong>Cakto</strong> (pagamentos) — trata os dados de pagamento informados no checkout.</li>
  <li><strong>Seu Claude (Anthropic)</strong> — não é nosso operador: o ClipeiAki não envia nada à Anthropic por conta própria. Quando
  <em>você</em> conecta o seu Claude pelo MCP, ele pede ao ClipeiAki os dados que precisa (lista de transmissões, momentos, frames e transcrição
  dos trechos) e os recebe na sua conta do Claude, onde são tratados conforme o seu contrato com a Anthropic. Você vê as conexões ativas e pode
  desconectar em <em>Conta e plano</em>.</li>
  <li><strong>Twitch</strong> — não é nossa operadora: é a plataforma de origem das transmissões que você conecta. Ao abrir a página de inspeção,
  o player oficial da Twitch é carregado e segue as regras de privacidade da Twitch.</li>
  <li>Autoridades, quando houver obrigação legal ou ordem judicial.</li>
</ul>

<h2 id="p5">5. Transferência internacional</h2>
<p>O ClipeiAki não transfere dados para fora do Brasil por iniciativa própria além do que depender do provedor de hospedagem (local informado
na seção 4). Quando você conecta o seu Claude, os dados que ele solicita vão para a sua conta na Anthropic (EUA) por sua iniciativa
(LGPD, art. 33); o enquadramento dessa hipótese está em validação jurídica.</p>

<h2 id="p6">6. Por quanto tempo guardamos</h2>
<table class="tbl">
  <thead><tr><th>Dado</th><th>Retenção (como o sistema funciona hoje)</th></tr></thead>
  <tbody>
    <tr><td>Blocos brutos da transmissão</td><td>apagados automaticamente após cerca de 10 minutos (ou enquanto um momento pendente precisar deles) e apagados por completo quando a sessão termina</td></tr>
    <tr><td>Preview da transmissão (último frame)</td><td>substituído a cada bloco e apagado quando a sessão termina</td></tr>
    <tr><td>Trecho de um momento candidato aguardando revisão</td><td>até 15 minutos no buffer (depois só ficam os dados do momento)</td></tr>
    <tr><td>Frames mostrados ao seu Claude, transcrições e momentos</td><td>até você excluir a conta</td></tr>
    <tr><td>Vídeos enviados e cortes</td><td>até você excluir o projeto ou a conta</td></tr>
    <tr><td>Conta, aceite, uso, tokens</td><td>até a exclusão da conta</td></tr>
    <tr><td>Registros de acesso (IP, data e hora)</td><td>6 meses (Marco Civil, art. 15), mesmo após a exclusão da conta; depois são apagados automaticamente</td></tr>
    <tr><td>Registros de pagamento (e-mail, oferta, situação)</td><td>enquanto durar a assinatura e pelo prazo necessário para obrigações legais e defesa em disputas ({EMP}: prazo a definir com a contabilidade)</td></tr>
  </tbody>
</table>
<p class="destaque">Ainda não há exclusão automática de vídeos e cortes antigos: eles ficam até você apagá-los. Uma política de expiração automática
está em avaliação e, se adotada, será anunciada antes de entrar em vigor.</p>

<h2 id="p7">7. Segurança</h2>
<p>Medidas que o sistema aplica hoje: senhas com hash scrypt; cookie de sessão HttpOnly e SameSite, enviado só por HTTPS em produção; tokens de sessão
e de API guardados apenas como hash; tokens de API e conexões OAuth (PKCE, código de uso único, renovação com rotação) com escopos, validade e limite de requisições; isolamento por conta em todas as consultas e
pastas de arquivos; proteção contra CSRF e política de segurança de conteúdo (CSP); limites de tentativas de login e de cadastro; chaves de
serviços apenas no servidor, nunca no navegador.</p>
<p class="destaque">Não há, hoje, criptografia em repouso própria do aplicativo nem rotina de backup: isso depende do provedor de hospedagem ({EMP}).
Em caso de incidente de segurança que possa causar risco ou dano relevante, comunicaremos a ANPD e os titulares afetados em até 3 dias úteis
(Res. CD/ANPD nº 15/2024), e manteremos registro do incidente.</p>

<h2 id="p8">8. Seus direitos (LGPD, art. 18)</h2>
<p>Você pode pedir confirmação e acesso, correção, anonimização, bloqueio ou eliminação de dados desnecessários, portabilidade, informação sobre
compartilhamento, revogação de consentimento (quando for a base) e se opor a tratamento irregular. Já disponível na conta:</p>
<ul>
  <li><strong>Acesso e portabilidade</strong>: <em>Conta e plano → Seus dados → Baixar meus dados</em> (arquivo JSON).</li>
  <li><strong>Correção</strong>: nome e @ editáveis no perfil; demais dados pelo suporte.</li>
  <li><strong>Eliminação</strong>: <em>Excluir minha conta</em> (exige a senha).</li>
</ul>
<p>Outros pedidos: e-mail de privacidade em <a href="/contato">Contato</a>. Respondemos em até 15 dias (LGPD, art. 19, II).</p>

<h2 id="p9">9. Crianças e adolescentes</h2>
<p>O serviço é destinado a maiores de 18 anos. Se identificarmos conta de menor, ela será encerrada e os dados eliminados, salvo obrigação legal de guarda.</p>

<h2 id="p10">10. Cookies</h2>
<p>Usamos apenas o cookie de sessão necessário ao login. Detalhes na <a href="/cookies">Política de Cookies</a>.</p>

<h2 id="p11">11. Alterações</h2>
<p>Mudanças relevantes geram nova versão e pedido de novo aceite no painel.</p>
""")

DOC["cancelamento"] = ("Política de Cancelamento, Arrependimento e Reembolso", f"""
<p class="lead">Como cancelar a assinatura do ClipeiAki, quando há devolução de valores e o que acontece em caso de contestação (chargeback).</p>

<h2 id="c1">1. Direito de arrependimento (7 dias)</h2>
<p>Você pode desistir da contratação em até <strong>7 dias corridos</strong> contados da compra, sem precisar justificar (CDC, art. 49).
O valor pago é devolvido <strong>integralmente</strong>, pelo mesmo meio de pagamento. Pedidos feitos dentro do prazo são aceitos mesmo que você
já tenha usado o serviço.</p>
<p>Como pedir: pelo próprio canal da Cakto usado na compra ou pelo e-mail de suporte em <a href="/contato">Contato</a>. Confirmamos o recebimento
imediatamente e comunicamos a Cakto para estornar a cobrança (Decreto nº 7.962/2013, art. 5º). O prazo do estorno no cartão depende da operadora;
no Pix, a devolução é feita pela Cakto na conta de origem.</p>
<p>A renovação mensal não reabre o prazo de 7 dias, porque não é uma nova contratação.</p>

<h2 id="c2">2. Cancelamento da assinatura</h2>
<ul>
  <li>Pode ser feito a qualquer momento, sem multa e sem fidelidade, na área do cliente da Cakto ou pelo suporte.</li>
  <li>A cobrança seguinte não acontece e o acesso pago continua até o fim do período já pago. Depois disso, a conta perde os recursos pagos
  (o sistema registra a assinatura como cancelada e mantém o acesso até a data de vencimento).</li>
  <li>Seus cortes continuam disponíveis para download até você excluí-los ou excluir a conta.</li>
</ul>

<h2 id="c3">3. Reembolso fora do prazo de arrependimento</h2>
<p>Depois dos 7 dias, o período em curso não é reembolsado por simples desistência, porque o serviço ficou à disposição. Há reembolso
proporcional ou integral quando:</p>
<ul>
  <li>o serviço não funcionou como contratado por falha nossa e não foi corrigido (CDC, art. 20);</li>
  <li>houve cobrança indevida ou em duplicidade (CDC, art. 42, parágrafo único);</li>
  <li>a Eclyss encerrou ou alterou o serviço de forma que impeça o uso do que você pagou.</li>
</ul>

<h2 id="c4">4. Chargeback e contestação</h2>
<p>Se o pagamento for contestado junto ao banco ou à operadora (chargeback) ou houver pedido de devolução de Pix (MED), o acesso pago fica
<strong>suspenso enquanto a contestação estiver em análise</strong> — o sistema faz isso automaticamente ao ser avisado pela Cakto. Se a contestação
for decidida a favor da manutenção da cobrança, o acesso é restabelecido. Antes de contestar, fale com o suporte: resolvemos cobranças indevidas
diretamente.</p>
<p>Contestações reiteradas de má-fé podem levar ao encerramento da conta, após análise do caso e com direito de resposta.</p>

<h2 id="c5">5. Prazos de atendimento</h2>
<p>Confirmamos o recebimento de pedidos imediatamente e respondemos em até 5 dias (Decreto nº 7.962/2013, art. 4º, parágrafo único).</p>
""")

DOC["conteudo"] = ("Política de Conteúdo e Direitos de Terceiros", f"""
<p class="lead">Regras sobre o conteúdo que você envia, conecta ou corta no ClipeiAki, e como terceiros podem denunciar violações.</p>

<h2 id="d1">1. Quem é responsável pelo conteúdo</h2>
<p>Você escolhe os vídeos e as transmissões que serão processados. Por isso, precisa ter os direitos ou autorizações necessários sobre:</p>
<ul>
  <li><strong>direitos autorais</strong> da transmissão, do vídeo e de obras que aparecem nele (Lei nº 9.610/1998);</li>
  <li><strong>imagem e voz</strong> das pessoas que aparecem (Código Civil, art. 20; Constituição, art. 5º, X e XXVIII, "a");</li>
  <li><strong>músicas</strong> tocadas na transmissão — trilhas protegidas costumam gerar bloqueios nas redes sociais mesmo com autorização do streamer;</li>
  <li><strong>jogos</strong>: o uso de imagens de jogos segue as políticas das publicadoras (por exemplo, a política de conteúdo da Rockstar Games/Take-Two para GTA).</li>
</ul>
<p>O ClipeiAki não verifica previamente a titularidade de cada conteúdo, mas exige a declaração de direitos ao conectar uma transmissão e
responde às denúncias pelo procedimento abaixo.</p>

<h2 id="d2">2. Conteúdo proibido</h2>
<ul>
  <li>Conteúdo sexual envolvendo menores, ou qualquer conteúdo sexual sem consentimento — removido imediatamente e comunicado às autoridades.</li>
  <li>Violência real, incitação ao ódio ou à violência, terrorismo, instruções para crimes.</li>
  <li>Conteúdo de terceiros usado sem autorização, inclusive transmissões de canais que você não controla.</li>
  <li>Exposição de dados pessoais de terceiros (endereço, documentos, telefone) ou conteúdo para assédio.</li>
</ul>

<h2 id="d3">3. Denúncia, remoção e contestação</h2>
<ol>
  <li><strong>Denúncia</strong>: o titular do direito (ou seu representante) envia ao e-mail de suporte em <a href="/contato">Contato</a>: identificação,
  o conteúdo ou canal envolvido, o direito violado e uma declaração de boa-fé de que as informações são verdadeiras.</li>
  <li><strong>Análise</strong>: confirmamos o recebimento e analisamos em até 5 dias úteis. Casos graves (seção 2, primeiro item) são tratados imediatamente.</li>
  <li><strong>Medida</strong>: se a denúncia for procedente, removemos o conteúdo, desconectamos a transmissão ou suspendemos o recurso, de forma
  proporcional, e avisamos o usuário com o motivo.</li>
  <li><strong>Contestação</strong>: o usuário pode responder em até 10 dias com documentos que comprovem a autorização. Se a contestação for
  procedente, o recurso é restabelecido quando possível.</li>
  <li><strong>Reincidência</strong> ou má-fé comprovada podem levar ao encerramento da conta.</li>
</ol>
<p>Ordens judiciais são cumpridas nos termos da lei (Marco Civil da Internet, arts. 19 a 21).</p>

<h2 id="d4">4. Publicação dos cortes</h2>
<p>O ClipeiAki não publica nada. Ao postar um corte numa rede social, você também precisa seguir as regras dessa rede (TikTok, Instagram, YouTube)
e da plataforma de origem (Twitch), inclusive regras de crédito ao criador.</p>
""")

DOC["cookies"] = ("Política de Cookies", f"""
<p class="lead">O ClipeiAki usa o mínimo de armazenamento no navegador. Não há cookies de publicidade nem de analytics, por isso não exibimos banner de consentimento.</p>
<table class="tbl">
  <thead><tr><th>Nome</th><th>Tipo</th><th>Finalidade</th><th>Duração</th></tr></thead>
  <tbody>
    <tr><td><code>vm_session</code></td><td>cookie próprio, essencial, HttpOnly, SameSite=Lax, Secure em produção</td><td>manter você conectado depois do login</td><td>30 dias ou até sair</td></tr>
    <tr><td><code>lcfg</code></td><td>localStorage (não é enviado ao servidor)</td><td>lembrar orçamento, duração e idioma escolhidos no Live Monitor</td><td>até você limpar os dados do navegador</td></tr>
  </tbody>
</table>
<h2 id="k1">Conteúdo de terceiros</h2>
<p>Na página de inspeção de uma transmissão, carregamos o <strong>player oficial da Twitch</strong> (player.twitch.tv) para você assistir à live.
A Twitch pode definir cookies próprios nesse player, conforme a política dela. O player só é carregado quando você abre essa página.</p>
<h2 id="k2">Como gerenciar</h2>
<p>Você pode apagar cookies e dados do site nas configurações do navegador. Sem o cookie de sessão não é possível ficar conectado.
Referência: Guia Orientativo sobre Cookies e Proteção de Dados Pessoais da ANPD (2022).</p>
""")

DOC["regras-live-ia"] = ("Regras do Live Monitor, da IA e das Integrações", f"""
<p class="lead">Como o Live Monitor funciona de verdade, o que a IA vê, limites técnicos e regras de uso das integrações.</p>

<h2 id="r1">1. Quais transmissões podem ser conectadas</h2>
<ul>
  <li>Hoje: canais da <strong>Twitch</strong>. Outras plataformas estão em desenvolvimento e não estão disponíveis.</li>
  <li>Só conecte canais <strong>seus</strong> ou de quem <strong>autorizou</strong> você a gerar cortes. A declaração é obrigatória e fica registrada com data.</li>
  <li>O uso precisa respeitar os Termos de Serviço e as Diretrizes da Comunidade da Twitch. A Eclyss pode desconectar canais em caso de denúncia
  procedente ou de mudança nas regras da plataforma.</li>
</ul>

<h2 id="r2">2. Como o monitoramento funciona</h2>
<ol>
  <li>Um processo no servidor da Eclyss (não o seu navegador) recebe a transmissão e grava blocos de 10 segundos.</li>
  <li>Detectores locais medem cada bloco: volume do áudio, mudanças bruscas de imagem e palavras de reação na transcrição.</li>
  <li>Trechos acima do normal viram <strong>momentos candidatos</strong>, com horário da transmissão.</li>
  <li>Se você conectou o seu Claude pelo MCP, ele pode pedir as evidências de um momento (até 3 frames e a transcrição da janela) e registrar
  uma decisão (cortar ou ignorar), com início, fim, título e justificativa. <strong>O Claude não assiste à transmissão continuamente</strong>:
  vê apenas o que pede, e cada frame mostrado a ele aparece no painel com horário e SHA-256. Sem o Claude conectado, você decide pelo painel.</li>
  <li>O motor de edição renderiza o corte; você revisa o preview e aprova antes de baixar.</li>
</ol>
<p>O monitoramento continua com a aba fechada. Cada sessão tem duração máxima; ao atingir um limite, a sessão para sozinha e o motivo aparece no
painel. O trecho de um momento candidato fica disponível para revisão por cerca de 15 minutos.</p>

<h2 id="r3">3. Limites do plano</h2>
<p>Transmissões simultâneas (Creator: 3; Creator Studio: 10), horas de monitoramento e cortes por mês são aplicados pelo servidor. A capacidade
total do servidor também é limitada: se estiver cheia, o início de novas sessões é recusado com aviso, sem cobrança extra.</p>

<h2 id="r4">4. Limitações conhecidas</h2>
<ul>
  <li>Momentos silenciosos (piadas sem reação sonora, jogadas sem grito) podem não ser detectados.</li>
  <li>Picos de áudio de música, alertas ou doações podem gerar candidatos sem interesse.</li>
  <li>O enquadramento automático da webcam pode errar quando há sobreposições (chat, alertas) na tela.</li>
  <li>A transcrição pode errar nomes, gírias e falas sobrepostas.</li>
  <li>Quedas da transmissão: o agente tenta reconectar; se a live ficar offline por cerca de 3 minutos, a sessão é encerrada.</li>
  <li>O preview é o último frame <em>gravado</em> pelo servidor, com alguns segundos de atraso em relação ao player ao vivo.</li>
</ul>

<h2 id="r5">5. Integração MCP (seu Claude)</h2>
<ul>
  <li><strong>claude.ai / Claude Desktop</strong>: adicione um conector personalizado com a URL do MCP do ClipeiAki; você será levado ao ClipeiAki
  para entrar e autorizar. A tela mostra o aplicativo e o domínio de retorno: só autorize se foi você que iniciou a conexão.</li>
  <li><strong>Claude Code</strong>: além do OAuth, você pode criar tokens pessoais em <em>Conta e plano</em>, escolhendo escopos e validade (até 1 ano).</li>
  <li>O token é mostrado uma única vez; guardamos só o hash. Revogue imediatamente se ele vazar.</li>
  <li>Há limite de requisições por token (padrão: 120 leituras e 20 ações por minuto).</li>
  <li>Comandos enviados pelo cliente MCP (por exemplo, o Claude) agem em nome da sua conta e seguem as mesmas regras e limites do painel.
  Conectar um canal por MCP também exige a declaração de direitos.</li>
</ul>

<h2 id="r6">6. IA</h2>
<p>O ClipeiAki não usa API de IA paga: a análise contextual é feita pelo seu Claude, quando você o conecta, e conta no seu plano do Claude. As
decisões dele são sugestões registradas no painel; o corte só é liberado para download depois da sua aprovação. Veja a
<a href="/privacidade">Política de Privacidade</a>.</p>
""")

DOC["contato"] = ("Contato, Suporte e Exclusão de Dados", f"""
<p class="lead">Canais oficiais para suporte, cancelamento, privacidade e denúncias.</p>
{fornecedor()}
<h2 id="s1">Atendimento</h2>
<ul>
  <li><strong>Suporte e cancelamento</strong>: e-mail de atendimento acima. Confirmamos o recebimento na hora e respondemos em até 5 dias (Decreto nº 7.962/2013, art. 4º).</li>
  <li><strong>Arrependimento (7 dias)</strong>: mesmo canal, ou o canal da Cakto usado na compra. Veja a <a href="/cancelamento">política</a>.</li>
  <li><strong>Denúncias de conteúdo</strong>: mesmo canal, com as informações da <a href="/conteudo">Política de Conteúdo</a>.</li>
  <li><strong>Privacidade (LGPD)</strong>: encarregado indicado acima. Resposta em até 15 dias.</li>
</ul>
<h2 id="s2">Exclusão de dados</h2>
<ol>
  <li>Entre na sua conta e abra <em>Conta e plano → Seus dados</em>.</li>
  <li>Se quiser uma cópia, clique em <em>Baixar meus dados</em> e baixe também os cortes que deseja guardar.</li>
  <li>Clique em <em>Excluir minha conta</em> e confirme com a senha. Lives em andamento param, e projetos, cortes, transmissões, tokens,
  aceite e arquivos são apagados.</li>
  <li>Cancele a assinatura na Cakto para interromper cobranças futuras.</li>
</ol>
<p>Ficam guardados apenas os registros exigidos por lei: registros de acesso por 6 meses (Marco Civil, art. 15) e registros de pagamento
necessários a obrigações fiscais e a disputas. Sem acesso à conta? Escreva para o e-mail de privacidade a partir do e-mail cadastrado.</p>
""")

NAV = [(k, DOCS[k]) for k in ("termos", "privacidade", "cancelamento", "conteudo", "cookies", "regras-live-ia", "contato")]


def page(slug, title, body):
    v = VERSIONS.get(slug, DEFAULT_VERSION); d = v.split("-"); vtxt = f"{d[2]}/{d[1]}/{d[0]}"
    nav = "".join(f'<li><a href="/{k}"{" aria-current=\"page\"" if k == slug else ""}>{html.escape(t)}</a></li>' for k, t in NAV)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark"><meta name="theme-color" content="#0b0b14">
<title>{html.escape(title)} · ClipeiAki</title>
<meta name="description" content="{html.escape(title)} do ClipeiAki (Eclyss).">
<link rel="icon" href="/static/icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/site/legal.css">
</head>
<body>
<a class="skip" href="#doc">Pular para o conteúdo</a>
<header class="lhead"><a class="brand" href="/"><img src="/static/icon.svg" alt="" width="32" height="32">ClipeiAki</a><a class="btn" href="/entrar">Entrar</a></header>
<div class="lwrap">
<nav class="lnav" aria-label="Documentos jurídicos"><ul>{nav}</ul></nav>
<main id="doc" class="ldoc">
<p class="notice-draft" role="note">Documento em validação jurídica antes da venda pública. Itens marcados como {P} dependem dos dados da empresa.</p>
<h1>{html.escape(title)}</h1>
<p class="ver">Versão {v} · vigente desde {vtxt}</p>
{body}
</main>
</div>
<footer class="lfoot"><p>ClipeiAki é um serviço da Eclyss. Não afiliado à Twitch, YouTube, TikTok, Meta, Anthropic, Rockstar Games ou Take-Two.</p>
<p><a href="/termos">Termos</a> · <a href="/privacidade">Privacidade</a> · <a href="/cancelamento">Cancelamento e reembolso</a> · <a href="/conteudo">Conteúdo</a> ·
<a href="/cookies">Cookies</a> · <a href="/regras-live-ia">Regras do Live Monitor e IA</a> · <a href="/contato">Contato</a></p></footer>
</body>
</html>
"""


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    for slug, (title, body) in DOC.items():
        (OUT / f"{slug}.html").write_text(page(slug, title, body))
    return sorted(DOC)


if __name__ == "__main__":
    print(build())
