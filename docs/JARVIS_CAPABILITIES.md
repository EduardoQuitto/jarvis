# J.A.R.V.I.S. — Seu assistente pessoal inteligente

O J.A.R.V.I.S. é um assistente pessoal de inteligência artificial concebido
para ir além de conversas: ele compreende objetivos, planeja tarefas em
etapas, utiliza ferramentas autorizadas, verifica se o trabalho realmente
funcionou e preserva o contexto entre uma conversa e outra — distribuído
entre os seus computadores e dispositivos.

O diferencial está na proposta: transformar solicitações em trabalho
executável, com continuidade, segurança e controle do usuário. Em vez de
apenas responder perguntas, o Jarvis pretende executar, acompanhar e
confirmar.

> **Observação honesta:** este documento descreve a visão do Jarvis após a
> conclusão do seu roteiro de desenvolvimento. A disponibilidade de cada
> funcionalidade depende da implementação e validação da fase
> correspondente — consulte o `README.md` e o `docs/ROADMAP.md` para saber
> o que já funciona na versão atual.

---

## O que o Jarvis poderá fazer

| Capacidade | O que significa na prática |
|---|---|
| Conversar por texto e voz | Dialogar normalmente e, quando a fase de voz estiver pronta, falar e ouvir |
| Lembrar e recuperar | Guardar informações, decisões e retomar conversas anteriores |
| Planejar objetivos | Quebrar um pedido complexo em etapas e acompanhar o progresso |
| Usar ferramentas autorizadas | Consultar o sistema, manipular arquivos e executar ações permitidas |
| Ajudar a programar | Analisar código, rodar testes e propor correções |
| Cuidar dos computadores | Diagnosticar estado, recursos e serviços das máquinas |
| Automatizar telas e navegador | Executar rotinas em interfaces gráficas, com supervisão |
| Pesquisar na web | Buscar informações atuais e confrontar fontes |
| Reutilizar procedimentos | Guardar modos de fazer testados e reaplicá-los (skills) |
| Agendar e notificar | Verificações recorrentes, compromissos e avisos proativos |
| Corrigir-se com controle | Detectar falhas, tentar rotas alternativas e registrar o aprendizado |
| Integrar a casa | Conversar com dispositivos via Home Assistant |
| Distribuir trabalho | Executar tarefas no computador mais adequado da sua rede |
| Crescer por plugins | Novos provedores de IA, ferramentas e integrações externas |
| Proteger e recuperar | Permissões, auditoria, backups e restauração de estado |

### Conversação por texto e voz

Na visão final, você conversa com o Jarvis por texto hoje e por voz quando
o pipeline de voz local estiver pronto (ativação por palavra-chave,
detecção de fala, transcrição e síntese locais). A mesma conversa, memória
e regras valem para os dois canais.

### Memória persistente e recuperação de conversas

O Jarvis pretende guardar o que importa — fatos sobre seus projetos,
decisões tomadas, preferências — e recuperar quando for útil, inclusive de
conversas antigas. Resumos e seleções de contexto são representações de
trabalho: o histórico original permanece preservado.

### Planejamento de objetivos e tarefas com múltiplas etapas

Diante de um pedido como “prepare meu ambiente de trabalho”, o Jarvis
pretende montar um plano (etapas, ordem, verificações), executá-lo passo a
passo e informar o progresso — retomando de onde parou, mesmo dias depois.

### Execução de ferramentas autorizadas

Ferramentas são as “mãos” do Jarvis: consultar CPU e memória, ler arquivos,
abrir aplicativos da lista permitida, pesquisar na web. Cada ferramenta tem
um nível de permissão, e nada executa sem passar pelas regras de segurança.

### Assistência ao desenvolvimento de software

Analisar um repositório, explicar trechos de código, executar a suíte de
testes, apontar falhas e sugerir correções — sempre mostrando o que foi
feito e o que mudou, sem inventar resultados.

### Administração e diagnóstico de computadores

Verificar uso de disco, memória, processos, serviços e rede, e apresentar
um diagnóstico legível com os dados reais coletados — nunca estimados.

### Automação de interfaces gráficas e navegadores

Rotinas repetitivas em programas e sites poderão ser executadas de forma
supervisionada, etapa por etapa, com verificação do resultado em cada passo.

### Pesquisa na web e análise de informações

Buscar informações atuais, ler páginas e comparar fontes independentes,
preservando divergências em vez de escondê-las — e sempre tratando
conteúdo externo como não confiável até ser verificado.

### Skills e procedimentos reutilizáveis

Um procedimento que funcionou bem (por exemplo, “publicar uma nova versão
do meu projeto”) poderá ser guardado como skill e reutilizado depois, com
os mesmos limites de autorização.

### Tarefas recorrentes, agendamentos e notificações

Verificações periódicas (“toda manhã, veja se o servidor está saudável”),
compromissos futuros e avisos proativos por voz, notificação ou painel —
sempre a partir de uma base de agendamento persistente e supervisionada.

### Autocorreção e melhoria controlada

Quando uma etapa falha, o Jarvis pretende registrar o erro, tentar uma
rota alternativa autorizada e incorporar o aprendizado — sem nunca
contornar permissões para “dar um jeito”.

### Integração com sistemas residenciais

Por meio do Home Assistant, o Jarvis poderá consultar e acionar
dispositivos autorizados da casa, combinando automações determinísticas
confiáveis com interpretação de pedidos complexos.

### Distribuição de tarefas entre computadores e servidores

Uma tarefa pesada poderá rodar no computador mais capaz, enquanto um
servidor leve centraliza o estado, as sessões e as permissões. O estado
central consistente permite trocar de máquina sem perder o fio.

### Plugins, provedores de IA e ferramentas externas

Novos modelos (locais ou em nuvem, conforme sua configuração),
ferramentas e integrações poderão ser conectados com capacidades e
requisitos declarados — sem contornar segurança ou autenticação.

### Segurança, backups e recuperação

Permissões explícitas, registro de auditoria de cada ação relevante,
cópias de segurança do estado e restauração supervisionada: a base para
confiar trabalho real a um assistente.

---

## Exemplos concretos de utilização

> Os cenários abaixo ilustram a visão final. Nem todos funcionam na versão
> atual — cada um depende de ferramentas, acesso e autorização adequados.

### Preparar um ambiente de desenvolvimento

**Você:** “Prepare meu ambiente do projeto Eryndor.”
**O Jarvis pretende:** montar o plano (verificar o computador, abrir o
editor, o terminal e a documentação), executar cada etapa com as
ferramentas autorizadas, verificar o resultado e responder com um resumo
do que está pronto — ou dizer honestamente o que não conseguiu fazer.

### Analisar um repositório e propor correções

**Você:** “Por que os testes estão falhando?”
**O Jarvis pretende:** ler a estrutura do código, executar a suíte de
testes, localizar a falha, propor a correção mínima e mostrar o diff —
pedindo confirmação antes de alterar qualquer arquivo sensível.

### Diagnosticar um servidor e apresentar um relatório

**Você:** “O servidor está lento?”
**O Jarvis pretende:** coletar CPU, memória, disco e processos no nó
indicado, comparar com o histórico guardado e entregar um relatório com
os dados reais e os pontos de atenção.

### Recuperar uma informação de uma conversa anterior

**Você:** “Qual foi a decisão sobre o banco de dados na semana passada?”
**O Jarvis pretende:** buscar na memória persistente e responder com a
decisão registrada, indicando de onde veio a informação.

### Agendar uma verificação e receber uma notificação

**Você:** “Me avise toda manhã se houver algo errado no servidor.”
**O Jarvis pretende:** registrar o compromisso recorrente, executar a
verificação no horário e notificar apenas quando houver algo relevante —
ou confirmar que está tudo bem.

### Executar uma tarefa em outro computador

**Você (no celular):** “Rode os testes no computador principal.”
**O Jarvis pretende:** encaminhar a tarefa ao nó autorizado com mais
recursos, acompanhar o progresso e trazer o resultado para a conversa
atual, mantendo o estado central consistente.

### Pesquisar na web e verificar informações

**Você:** “Esse componente ainda é fabricado?”
**O Jarvis pretende:** pesquisar em fontes independentes, comparar as
informações, apontar divergências e indicar o grau de confiança —
sem tratar a resposta do modelo como verdade.

### Realizar um procedimento reutilizável (skill)

**Você:** “Execute o procedimento de backup semanal.”
**O Jarvis pretende:** carregar a skill correspondente, executar as etapas
na ordem, verificar cada resultado e registrar a execução na auditoria.

### Controlar dispositivos residenciais autorizados

**Você:** “Apague as luzes da sala e confira se o computador ligou.”
**O Jarvis pretende:** interpretar o pedido, acionar os dispositivos
autorizados via Home Assistant, confirmar o estado real de cada um e
informar o resultado.

---

## Integração com a casa

Por meio do Home Assistant, o Jarvis poderá aproveitar os dispositivos e
serviços compatíveis que você já tem ou vier a instalar:

- iluminação, tomadas e interruptores inteligentes;
- sensores de temperatura, presença e abertura;
- climatização, cenas e rotinas;
- monitoramento de equipamentos e consumo de energia;
- rotinas por horário ou por condições (ex.: “quando eu sair, desligue…”);
- verificação e controle de computadores, incluindo Wake-on-LAN;
- notificações relacionadas à casa (voz, mensagem ou painel).

Tudo depende dos equipamentos instalados, das integrações disponíveis e
das permissões concedidas — sem promessa de compatibilidade universal com
todos os fabricantes.

A filosofia é combinar o melhor dos dois mundos: atividades simples e
críticas continuam em automações determinísticas confiáveis; o Jarvis
entra para interpretar pedidos complexos em linguagem natural e coordenar
vários serviços em um mesmo plano.

---

## Servidores e computadores

Sem jargão: o Jarvis foi desenhado para funcionar em rede, com papéis bem
definidos.

- **SERVER:** o coordenador. Mantém o estado persistente, as sessões, as
  permissões e o andamento das tarefas. É uma máquina leve, feita para
  ficar ligada.
- **CORE / AI NODE:** o “cérebro operacional”. Executa o processamento de
  IA e as tarefas pesadas, conforme os recursos da máquina.
- **Nós adicionais:** computadores autorizados que podem ajudar com
  processamento, memória ou serviços específicos.
- **APP e interfaces:** chat, painel e notificações — por onde você
  conversa, acompanha tarefas e autoriza ações sensíveis.

Perfis de instalação possíveis na arquitetura pretendida:

1. **Tudo em um único computador** — o jeito mais simples de começar.
2. **Servidor dedicado + computador principal** como nó de processamento.
3. **Servidor doméstico com diversos nós** — cada máquina contribui com o
   que tem de melhor.
4. **Ambiente remoto ou híbrido** — quando configurado de forma segura.

Nem todos os perfis precisam estar disponíveis na versão atual. O objetivo
da distribuição é permitir que vários equipamentos trabalhem juntos sem
depender rigidamente de uma única máquina — sem a promessa de que “mais
computadores = mais velocidade” para qualquer tarefa: o ganho depende da
tarefa, dos recursos, da conexão e da forma de distribuição.

---

## Memória, inteligência e planejamento

Vale separar conceitos que costumam se misturar:

- **Conversar** é trocar mensagens agora.
- **Guardar na memória** é registrar fatos, decisões e preferências para
  depois — por ação sua, do Jarvis (quando autorizado) ou de rotinas.
- **Recuperar** é trazer de volta o que foi guardado, com indicação da
  origem.
- **Planejar** é transformar um objetivo em etapas ordenadas e verificáveis.
- **Executar** é cumprir as etapas usando ferramentas autorizadas.
- **Reutilizar** é reaplicar procedimentos que já funcionaram (skills).
- **Verificar** é conferir se a operação realmente funcionou antes de
  declarar sucesso.

O Jarvis pretende preservar o relevante ao longo do tempo, reconhecer
quando está incerto, respeitar o contexto e continuar tarefas
interrompidas quando for seguro. Memória, habilidades reutilizáveis e
treinamento de modelos são coisas diferentes — este projeto não promete
treinar modelos automaticamente.

---

## Proatividade e autonomia

Na visão final, o Jarvis poderá acompanhar tarefas em andamento, executar
verificações agendadas, perceber problemas e sugerir ações antes de você
perguntar. A autonomia será progressiva e controlada:

- **Baixo risco e autorizado:** pode acontecer sozinho (ex.: verificação
  de rotina, resumo matinal).
- **Sensível, destrutivo ou irreversível:** exige confirmação explícita,
  sempre — sem exceção e sem atalho.
- **Rotinas e agendamentos:** você poderá acompanhar, pausar, cancelar e
  revogar quando esses controles existirem.

E um princípio inegociável: a confiança do modelo jamais substitui
evidência, autorização ou verificação real.

---

## Segurança e privacidade

Em linguagem direta, os princípios que orientam o projeto:

- **Permissões explícitas:** ações sensíveis pedem aprovação sua.
- **Autenticação:** usuários e dispositivos se identificam antes de agir.
- **Separação de papéis:** quem processa (CORE) não é quem guarda o
  estado e as permissões (SERVER).
- **Ferramentas controladas:** cada ferramenta declara o que faz e seu
  nível de risco; agentes não ampliam as próprias permissões.
- **Credenciais protegidas:** segredos ficam onde pertencem (ex.: o token
  do Home Assistant vive só no SERVER) e nunca viajam sem necessidade.
- **Local primeiro:** processamento local quando apropriado; provedores
  externos só quando você configurar — e, nesse caso, eles recebem apenas
  o mínimo necessário.
- **Auditoria:** ações relevantes ficam registradas para consulta.
- **Backups e recuperação:** estado copiado e restauração supervisionada.
- **Verificação:** operações importantes são conferidas, não presumidas.

O Jarvis não deverá executar uma ação apenas porque o modelo sugeriu.
Princípios de projeto não são garantia absoluta: segurança se valida na
prática, versão a versão — sem promessa de invulnerabilidade.

---

## Instalação e configuração

A experiência desejada para a versão concluída, em dez passos:

1. Baixar a versão compatível com seu sistema.
2. Escolher o perfil de instalação (tudo junto, servidor dedicado…).
3. Verificar requisitos e compatibilidade do hardware.
4. Configurar o SERVER.
5. Conectar os nós autorizados.
6. Selecionar provedores e modelos de IA.
7. Configurar ferramentas e integrações.
8. Configurar interfaces e notificações.
9. Validar a instalação com verificações de saúde.
10. Começar a usar o assistente.

A meta é uma configuração guiada: menos edição manual de arquivos, mais
diagnóstico automático e atualização/recuperação simples. Isso é a
experiência pretendida — não a descrição de um instalador que já exista.

---

## Diferenciais

Sem alegar exclusividade de mercado para cada item: o diferencial do
Jarvis está na combinação, em um sistema integrado, de:

- **Continuidade de contexto** entre conversas e tarefas, por dias.
- **Execução de trabalho real**, não só geração de respostas.
- **Arquitetura distribuída** desacoplada do hardware.
- **Integração entre IA, computadores e casa** no mesmo plano.
- **Flexibilidade de modelos**, do local ao externo, por configuração.
- **Habilidades reutilizáveis** com aprendizado procedimental controlado.
- **Segurança integrada à execução**, não adicionada depois.
- **Verificação e recuperação**, com honestidade sobre falhas.

---

## Visão de longo prazo

O destino do projeto é um assistente pessoal persistente, extensível,
multimodal, distribuído e confiável: capaz de entender objetivos, planejar
trabalho, usar recursos autorizados, acompanhar tarefas por quanto tempo
for preciso e integrar o mundo digital à sua casa.

> Um assistente que não apenas responde, mas compreende o que precisa ser
> feito, executa o que está autorizado a fazer e verifica se realmente
> funcionou.
