## Fase 16.5 — Inteligência Operacional Local, Descoberta Progressiva de Ferramentas e Respostas Naturais

**Status:** Planejamento técnico  
**Pré-requisito:** Fase 16 concluída e integrada  
**Tipo:** Evolução arquitetural do CORE e do fluxo de execução do J.A.R.V.I.S.  
**Objetivo principal:** Tornar o J.A.R.V.I.S. mais rápido, eficiente, natural e funcional localmente, reduzindo a dependência do LLM para operações simples sem comprometer a capacidade de raciocínio, a segurança ou a qualidade das respostas.

### 1. Visão geral da fase

A Fase 16.5 tem como finalidade desenvolver uma camada de inteligência operacional local capaz de compreender solicitações, identificar capacidades disponíveis, selecionar ferramentas relevantes, executar operações simples sem uma chamada ao LLM e produzir respostas naturais com base nos resultados reais das operações.

Atualmente, o fluxo de execução pode exigir que o LLM participe de tarefas que não necessariamente precisam de raciocínio generativo. Além disso, a quantidade de ferramentas e definições de parâmetros disponibilizadas ao modelo pode aumentar o consumo de tokens, o tempo de processamento e a complexidade da decisão.

A proposta é introduzir uma arquitetura em que o J.A.R.V.I.S. saiba identificar quando realmente precisa de um modelo de linguagem e quando pode resolver uma solicitação por meio de seus próprios componentes locais.

Isso não significa substituir o LLM ou limitar sua capacidade. O objetivo é utilizar cada recurso no momento adequado.

O sistema deverá conseguir, por exemplo:

- Consultar uma informação simples sem precisar chamar o LLM.
- Identificar qual ferramenta deve ser utilizada a partir de uma solicitação em linguagem natural.
- Reconhecer entidades, dispositivos, ambientes, serviços e referências contextuais.
- Executar operações locais de baixa complexidade com rapidez.
- Enviar ao LLM somente as ferramentas e os esquemas realmente relevantes para a solicitação.
- Produzir respostas naturais, contextualizadas e variadas, em vez de utilizar mensagens fixas e repetitivas.
- Continuar executando as capacidades locais essenciais mesmo quando não houver internet ou disponibilidade de um provedor de IA.
- Preservar integralmente as regras de autorização, confirmação e isolamento de dados.

A arquitetura deverá continuar respeitando a separação de responsabilidades do projeto:

- **SERVER:** permanece como fonte de verdade para os recursos e serviços que pertencem ao servidor, além de controlar suas ferramentas e integrações.
- **CORE:** continua responsável pela inteligência, interpretação, orquestração, seleção de ferramentas e processamento de IA.
- **LLM:** permanece como recurso de raciocínio e geração de linguagem, acionado quando a tarefa realmente exigir suas capacidades.
- **Ferramentas:** continuam sendo executadas pelos mecanismos oficiais do projeto, respeitando o registro, as políticas e as autorizações existentes.

### 2. Princípios obrigatórios

Toda a implementação deverá seguir estes princípios:

1. **Local-first:** sempre que uma operação puder ser resolvida localmente com segurança e precisão, não deverá depender de uma chamada externa.
2. **LLM sob demanda:** o modelo deverá ser utilizado para tarefas que realmente exijam interpretação complexa, planejamento, geração avançada ou raciocínio.
3. **Seleção contextual:** somente ferramentas relevantes deverão ser disponibilizadas ao LLM.
4. **Respostas naturais:** as respostas deverão ser construídas a partir do contexto e dos resultados reais, evitando mensagens engessadas.
5. **Segurança centralizada:** nenhuma otimização poderá contornar o Registry, o PolicyEngine, o ToolExecutor ou os mecanismos oficiais de confirmação.
6. **Offline funcional:** a indisponibilidade de internet ou de um provedor externo não poderá interromper capacidades locais independentes desses serviços.
7. **Arquitetura modular:** os novos componentes deverão possuir responsabilidades delimitadas e interfaces bem definidas.
8. **Mensuração antes da otimização:** mudanças de desempenho deverão ser comparadas com uma linha de base real.
9. **Compatibilidade:** os fluxos existentes deverão continuar funcionando, inclusive chamadas de ferramentas, confirmações, retomadas e respostas em streaming.
10. **Evolução gradual:** não realizar uma reescrita generalizada em outra linguagem sem evidências de que isso seja necessário.

---

# Frente 1 — Otimização do Catálogo de Ferramentas e do Registry

**Objetivo:** reduzir o processamento desnecessário na descoberta e disponibilização de ferramentas, evitando reconstruções repetidas de metadados e esquemas.

### Problema identificado

O Registry mantém as ferramentas registradas, mas a obtenção de suas informações pode gerar trabalho repetido.

Na implementação analisada:

- `ToolRegistry.list_tools()` consulta as propriedades de metadados das ferramentas.
- `BaseTool.metadata` pode regenerar o JSON Schema a partir do modelo de argumentos.
- O método `_build_tools_list()` do Orchestrator chama `register_default_tools(registry)` durante a construção da lista de ferramentas.

Isso significa que algumas informações podem ser reconstruídas ou reavaliadas diversas vezes durante a execução de uma conversa.

Além do custo de processamento, o comportamento dificulta estabelecer um catálogo estável e previsível.

### Como implementar

**1.1. Separar registro e consulta**

O registro das ferramentas deverá acontecer no momento adequado da inicialização do sistema.

A construção de uma lista de ferramentas para uma solicitação não deverá registrar novamente as ferramentas padrão.

A responsabilidade de registrar ferramentas deverá permanecer no ponto central de inicialização do Registry.

O método `_build_tools_list()` deverá ser responsável por consultar e selecionar ferramentas já registradas, não por reconstruir o ambiente de ferramentas.

**1.2. Implementar cache de metadados**

Avaliar a implementação de um cache interno para:

- Nome da ferramenta.
- Descrição.
- Categoria.
- Nível de segurança.
- Visibilidade.
- Parâmetros.
- JSON Schema.
- Informações auxiliares utilizadas pelo seletor.

O cache deverá evitar que o JSON Schema seja regenerado em cada consulta.

Sempre que possível, os metadados armazenados deverão ser tratados como imutáveis, impedindo alterações acidentais durante a execução.

**1.3. Implementar invalidação controlada**

Caso uma ferramenta seja adicionada, removida ou atualizada, o Registry deverá atualizar corretamente os metadados correspondentes.

Não deverá existir um cache desatualizado que disponibilize esquemas antigos ou ferramentas que já não estão registradas.

A invalidação deverá ocorrer somente quando houver alteração efetiva no catálogo ou em sua configuração.

**1.4. Preservar a responsabilidade do Registry**

O cache não deverá executar ferramentas, conceder permissões ou substituir o mecanismo de autorização.

O Registry continuará sendo o ponto oficial de acesso às ferramentas.

### Arquivos envolvidos

- `tools/registry.py`
- `core/contracts/tool.py`
- `core/orchestrator/engine.py`
- `tools/__init__.py`
- `core/config.py`

### Testes obrigatórios

- Verificar se as ferramentas padrão são registradas apenas uma vez durante a inicialização prevista.
- Verificar se múltiplas consultas ao catálogo reutilizam os metadados armazenados.
- Verificar se a alteração de uma ferramenta invalida somente os dados necessários.
- Verificar se ferramentas adicionadas e removidas são refletidas corretamente.
- Verificar se o cache não permite executar ferramentas que não estão registradas.
- Verificar se os metadados permanecem consistentes após várias solicitações simultâneas.

### Critérios de conclusão

- O catálogo deverá possuir um ciclo de vida previsível.
- A construção da lista de ferramentas não deverá repetir o registro das ferramentas padrão.
- Os metadados deverão ser reutilizados corretamente.
- A invalidação deverá funcionar sem comprometer a integridade do Registry.
- Nenhuma regra de segurança poderá ser alterada para obter ganho de desempenho.

---

# Frente 2 — Compreensão Local de Intenções (Natural Language Understanding)

**Objetivo:** permitir que o J.A.R.V.I.S. compreenda solicitações simples localmente, identificando a intenção do usuário antes de decidir se uma chamada ao LLM é necessária.

### Conceito

O sistema deverá desenvolver uma camada local de interpretação de linguagem natural.

Essa camada não deverá tentar reproduzir integralmente a capacidade de raciocínio de um LLM.

Sua finalidade será reconhecer intenções conhecidas, extrair informações relevantes e identificar quando uma solicitação pode ser resolvida por capacidades já disponíveis no sistema.

Exemplo:

Usuário: "Jarvis, que horas são?"

O sistema deverá reconhecer uma intenção conhecida e obter a informação diretamente de sua ferramenta de horário, sem precisar chamar o LLM.

Outro exemplo:

Usuário: "Apaga a luz do quarto."

O sistema deverá identificar a intenção de controlar um dispositivo, reconhecer a entidade mencionada e verificar se existe uma capacidade compatível.

Se a operação depender de confirmação, essa confirmação deverá continuar sendo solicitada normalmente.

### Como implementar

**2.1. Normalização de linguagem**

Criar uma etapa de normalização capaz de lidar com:

- Maiúsculas e minúsculas.
- Acentuação.
- Espaços desnecessários.
- Variações de escrita.
- Abreviações comuns.
- Expressões coloquiais.
- Sinônimos.
- Variações linguísticas em português.

A normalização não deverá apagar informações relevantes nem alterar o significado original da solicitação.

O texto original deverá permanecer disponível para as etapas seguintes.

**2.2. Classificação local de intenções**

Implementar um mecanismo de classificação que identifique intenções previamente conhecidas.

Exemplos de categorias:

- Consultar horário.
- Consultar data.
- Consultar informações do sistema.
- Consultar estado de um dispositivo.
- Controlar dispositivos.
- Consultar informações armazenadas.
- Pesquisar arquivos locais.
- Consultar capacidades disponíveis.
- Solicitar uma operação desconhecida ou complexa.

A lista deverá ser extensível, permitindo adicionar novas intenções sem modificar toda a arquitetura.

**2.3. Resultado estruturado**

A interpretação deverá produzir um objeto estruturado, e não apenas retornar uma palavra ou uma correspondência textual.

O contrato poderá seguir conceitualmente esta estrutura:

`IntentResult`:

- `intent`: intenção identificada.
- `confidence`: confiança da classificação.
- `entities`: entidades identificadas.
- `slots`: parâmetros extraídos.
- `requires_clarification`: indica se falta alguma informação.
- `requires_llm`: indica se a solicitação exige interpretação mais avançada.
- `source`: mecanismo utilizado para a classificação.

Os campos e tipos definitivos deverão seguir os padrões de contratos já utilizados no projeto.

**2.4. Estratégia de classificação**

A primeira implementação deverá priorizar mecanismos leves e determinísticos, como regras, expressões, aliases e padrões linguísticos.

Outras técnicas, como embeddings ou classificadores locais, poderão ser introduzidas quando apresentarem benefício comprovado.

Não será obrigatório instalar ou executar um segundo modelo de IA apenas para reconhecer intenções simples.

**2.5. Português como idioma prioritário**

O reconhecimento deverá ser desenvolvido considerando desde o início o português brasileiro.

Expressões diferentes que possuam o mesmo significado deverão ser reconhecidas como intenções compatíveis.

Exemplo:

- "Que horas são?"
- "Me fala o horário."
- "Qual é a hora agora?"
- "Jarvis, horário."

Todas deverão conseguir chegar à mesma intenção, respeitando a confiança da classificação.

O sistema também deverá manter possibilidade de expansão para outros idiomas.

### Arquivos envolvidos

Novos módulos poderão ser criados conforme a organização adotada:

- `core/config.py`
- `core/orchestrator/engine.py`
- `core/contracts/`
- Novo módulo de interpretação local, preferencialmente organizado em uma área própria, como `core/nlu/`.
- Novos testes em `tests/unit/`.

### Testes obrigatórios

- Reconhecimento de diferentes formulações em português.
- Reconhecimento de frases com e sem acentuação.
- Reconhecimento de abreviações e expressões coloquiais previstas.
- Rejeição de intenções desconhecidas.
- Tratamento de solicitações ambíguas.
- Verificação da confiança da classificação.
- Verificação de que uma intenção incorreta não resulta em execução de ferramenta.
- Verificação de que o texto original permanece preservado.

### Critérios de conclusão

- O sistema deverá reconhecer intenções conhecidas sem depender do LLM.
- A classificação deverá retornar dados estruturados.
- Solicitações desconhecidas ou ambíguas deverão seguir para o fluxo apropriado.
- O reconhecimento deverá funcionar em português brasileiro.
- Nenhuma operação deverá ser executada apenas porque uma palavra isolada foi identificada.

---

# Frente 3 — Descoberta Inteligente e Seleção Contextual de Ferramentas

**Objetivo:** aprimorar a seleção de ferramentas para que o sistema disponibilize somente recursos realmente relevantes para a solicitação atual.

### Problema identificado

O projeto já possui o mecanismo `core/context/tool_selector.py`, que utiliza palavras-chave, categorias e pontuação para selecionar ferramentas.

Entretanto, a implementação analisada apresenta pontos que precisam ser corrigidos:

- Algumas palavras-chave e categorias estão concentradas no inglês.
- O conjunto `CORE_TOOL_NAMES` utiliza `get_time`, enquanto a ferramenta existente possui o nome `get_current_time`.
- Ferramentas consideradas essenciais podem ser adicionadas independentemente de sua relevância para a solicitação.
- `min_tools` é armazenado, mas não participa efetivamente da seleção.
- A confiança calculada pode indicar uma correspondência aceitável mesmo quando a relevância real é baixa.
- O mecanismo de fallback pode aumentar a quantidade de ferramentas selecionadas sem uma avaliação suficientemente contextual.
- A quantidade mínima de ferramentas pode incentivar o envio de ferramentas desnecessárias.

### Como implementar

**3.1. Corrigir a correspondência entre catálogo e ferramentas**

Todos os nomes utilizados pelo seletor deverão corresponder exatamente aos nomes registrados.

A lista de ferramentas prioritárias deverá ser validada contra o catálogo real.

O sistema não poderá presumir que uma ferramenta existe apenas porque seu nome aparece em uma configuração.

**3.2. Melhorar a classificação de relevância**

A seleção deverá considerar múltiplos fatores:

- Intenção identificada.
- Palavras-chave.
- Sinônimos.
- Categoria da ferramenta.
- Descrição.
- Parâmetros necessários.
- Entidades identificadas.
- Contexto da conversa.
- Capacidades relacionadas à solicitação.

A seleção não deverá depender exclusivamente de correspondência textual.

**3.3. Criar um catálogo pesquisável**

Cada ferramenta deverá possuir informações suficientes para permitir sua descoberta sem exigir que todos os seus esquemas completos sejam carregados ou enviados ao LLM.

O catálogo poderá armazenar:

- Nome.
- Descrição resumida.
- Categoria.
- Palavras-chave.
- Capacidades.
- Visibilidade.
- Nível de segurança.
- Indicação de disponibilidade.
- Referência aos metadados completos.

Essas informações deverão ser mantidas alinhadas com os metadados oficiais do Registry.

**3.4. Melhorar a confiança**

A confiança deverá representar a qualidade real da correspondência.

Não deverá ser calculada exclusivamente pela pontuação da ferramenta mais bem classificada.

O mecanismo deverá considerar a diferença entre as melhores candidatas, a qualidade da correspondência e a identificação da intenção.

Quando a confiança for insuficiente, o sistema deverá ampliar a busca de maneira controlada ou encaminhar a solicitação ao LLM.

**3.5. Remover ferramentas obrigatórias sem justificativa contextual**

O sistema não deverá incluir ferramentas apenas para atingir uma quantidade mínima.

`min_tools` deverá ser revisto para que não obrigue o envio de ferramentas irrelevantes.

Caso seja mantido, deverá funcionar como parâmetro de comportamento controlado, nunca como regra que prevalece sobre a relevância.

**3.6. Implementar fallback inteligente**

Se nenhuma ferramenta apresentar relevância suficiente:

1. Verificar se a solicitação pode ser resolvida por uma intenção local conhecida.
2. Ampliar a busca no catálogo quando houver possibilidade de uma capacidade correspondente.
3. Considerar contexto e entidades já identificados.
4. Encaminhar ao LLM quando a solicitação exigir interpretação mais ampla.
5. Solicitar esclarecimento quando a ambiguidade impedir uma decisão segura.

A ampliação da busca deverá ter limites configuráveis para evitar que o sistema retorne ao comportamento de disponibilizar ferramentas indiscriminadamente.

**3.7. Seleção em português e inglês**

A seleção deverá funcionar com descrições, palavras-chave e expressões em português e inglês.

O catálogo não deverá depender do idioma utilizado na implementação da ferramenta.

### Arquivos envolvidos

- `core/context/tool_selector.py`
- `core/context/budget.py`
- `core/config.py`
- `core/orchestrator/engine.py`
- `tools/registry.py`
- `core/contracts/tool.py`

### Testes obrigatórios

- Solicitações em português e inglês.
- Sinônimos e diferentes formulações.
- Verificação de relevância das ferramentas selecionadas.
- Ferramentas com nomes semelhantes.
- Ausência de correspondência.
- Solicitação ambígua.
- Catálogo com poucas ferramentas.
- Catálogo com muitas ferramentas.
- Fallback com limite de seleção.
- Garantia de que ferramentas irrelevantes não são incluídas apenas para atingir `min_tools`.
- Correspondência entre os nomes do catálogo e os nomes reais do Registry.

### Critérios de conclusão

- A seleção deverá ser contextual e consistente.
- O sistema não deverá enviar ferramentas sem relevância suficiente.
- O mecanismo deverá reconhecer intenções em português.
- A quantidade de ferramentas deverá respeitar limites configuráveis.
- O fallback deverá ser controlado e testado.
- A seleção deverá ser mensurável, permitindo identificar sua precisão e eficiência.

---

# Frente 4 — Carregamento Progressivo de Esquemas e Otimização de Tokens

**Objetivo:** reduzir o volume de informações enviado ao LLM, disponibilizando os esquemas completos somente das ferramentas que realmente poderão ser utilizadas na solicitação.

### Problema identificado

Cada definição de ferramenta enviada ao LLM pode incluir:

- Nome.
- Descrição.
- JSON Schema.
- Parâmetros.
- Tipos.
- Campos obrigatórios.
- Restrições.

Quando muitas ferramentas são disponibilizadas simultaneamente, o conteúdo utilizado para descrevê-las pode representar uma parcela significativa do contexto.

Esse custo aumenta mesmo quando a solicitação exige apenas uma ferramenta simples.

O sistema deverá resolver esse problema sem prejudicar a capacidade do modelo de utilizar corretamente as ferramentas.

### Como implementar

**4.1. Separar metadados resumidos de esquemas completos**

O catálogo interno deverá permitir consultar informações resumidas sem carregar ou converter todos os esquemas completos.

A descoberta inicial deverá utilizar apenas informações necessárias para identificar as ferramentas candidatas.

**4.2. Selecionar antes de converter**

O fluxo correto deverá ser:

1. Receber a solicitação.
2. Interpretar a intenção localmente.
3. Pesquisar o catálogo.
4. Selecionar as ferramentas relevantes.
5. Recuperar os metadados completos somente dessas ferramentas.
6. Converter os metadados selecionados para o formato aceito pelo provedor.
7. Enviar a solicitação ao LLM.

A conversão não deverá ocorrer sobre todo o catálogo antes da seleção.

**4.3. Preservar esquemas completos nas ferramentas disponibilizadas**

Nenhum esquema deverá ser reduzido de maneira que o modelo receba informações insuficientes para construir parâmetros válidos.

Uma ferramenta disponibilizada ao LLM deverá possuir sua definição completa e correta.

O carregamento progressivo deverá reduzir a quantidade de ferramentas disponibilizadas, e não retirar arbitrariamente informações essenciais de seus parâmetros.

**4.4. Reavaliar a seleção quando necessário**

Caso o modelo demonstre que a seleção inicial não contemplou uma capacidade necessária, o sistema poderá executar uma nova etapa controlada de descoberta.

Essa expansão deverá possuir limites e evitar ciclos repetitivos de chamadas.

Uma solicitação não deverá provocar ampliações ilimitadas do catálogo.

**4.5. Integrar ao orçamento de contexto**

O mecanismo deverá trabalhar em conjunto com `core/context/budget.py`.

A quantidade de tokens destinada às definições de ferramentas deverá ser contabilizada separadamente sempre que possível.

A estimativa local deverá continuar disponível, mas deverá utilizar também os dados reais de consumo disponibilizados pelos provedores.

Quando o provedor retornar `LLMUsage`, os valores reais deverão ser utilizados para análise.

**4.6. Comparar custo e cobertura**

A redução de tokens não deverá ser considerada uma melhoria quando provocar perda de capacidade.

Deverão ser medidos:

- Quantidade de ferramentas existentes.
- Quantidade selecionada.
- Quantidade de ferramentas efetivamente utilizadas.
- Tokens estimados das definições.
- Tokens reais reportados pelo provedor.
- Taxa de sucesso das chamadas de ferramentas.
- Frequência de expansão da seleção.
- Casos em que uma ferramenta necessária não foi disponibilizada.

### Arquivos envolvidos

- `core/context/budget.py`
- `core/context/tool_selector.py`
- `core/conversation/context_builder.py`
- `core/llm/converters.py`
- `core/contracts/llm.py`
- `core/orchestrator/engine.py`

### Testes obrigatórios

- Conversão somente das ferramentas selecionadas.
- Preservação integral dos parâmetros e campos obrigatórios.
- Compatibilidade com diferentes provedores.
- Contabilização correta dos esquemas.
- Reutilização de metadados em cache.
- Fallback quando uma capacidade necessária não estiver na seleção inicial.
- Compatibilidade com o orçamento de contexto.
- Verificação de que o modelo continua conseguindo executar chamadas válidas.

### Critérios de conclusão

- O LLM deverá receber somente as ferramentas selecionadas para aquela solicitação.
- Os esquemas das ferramentas disponibilizadas deverão permanecer completos.
- O consumo de tokens deverá apresentar redução mensurável em relação à linha de base.
- A cobertura de capacidades e a taxa de sucesso deverão ser preservadas.
- A otimização não deverá alterar a semântica das ferramentas.

---

# Frente 5 — Resolução de Entidades e Capacidades

**Objetivo:** permitir que o J.A.R.V.I.S. reconheça o que o usuário está mencionando e relacione essa informação com as entidades, ferramentas e capacidades efetivamente disponíveis.

### Conceito

Reconhecer a intenção não é suficiente.

O sistema também precisa identificar os objetos e recursos relacionados à solicitação.

Exemplo:

Usuário: "Jarvis, apaga a luz do quarto."

O sistema precisa identificar:

- Intenção: controlar iluminação.
- Ação: desligar.
- Entidade: luz do quarto.
- Capacidade necessária: desligar um dispositivo compatível.
- Recurso real: entidade registrada no Home Assistant.

O sistema não deverá inventar IDs de dispositivos, serviços ou entidades.

### Como implementar

**5.1. Resolver entidades por aliases**

Criar uma camada de resolução capaz de relacionar expressões naturais a identificadores reais.

Exemplos:

- "Luz do quarto" → entidade de iluminação cadastrada.
- "TV da sala" → entidade correspondente.
- "Ventilador" → dispositivo registrado.
- "Computador principal" → recurso configurado no sistema.

Os aliases deverão ser configuráveis e compatíveis com os mecanismos já existentes.

**5.2. Integrar com o Home Assistant**

A integração deverá consultar as informações reais disponibilizadas pelo SERVER.

O CORE deverá utilizar os contratos e ferramentas existentes, sem assumir diretamente a responsabilidade de armazenar ou administrar credenciais do Home Assistant.

A arquitetura atual deverá ser preservada:

- Ferramentas e credenciais exclusivas do SERVER permanecem no SERVER.
- O CORE solicita operações por meio dos mecanismos remotos já implementados.
- O servidor valida e executa suas responsabilidades.

**5.3. Diferenciar entidade, capacidade e ferramenta**

Esses conceitos não deverão ser tratados como equivalentes.

- **Entidade:** objeto ou recurso real, como uma lâmpada.
- **Capacidade:** operação possível, como ligar ou desligar iluminação.
- **Ferramenta:** mecanismo técnico utilizado para executar essa operação.

Uma entidade poderá possuir diversas capacidades, e uma capacidade poderá ser atendida por diferentes ferramentas.

**5.4. Resolver referências contextuais**

O sistema deverá conseguir interpretar expressões que dependam do histórico recente.

Exemplo:

Usuário: "Qual é o estado da luz do quarto?"

J.A.R.V.I.S.: "Ela está ligada."

Usuário: "Então desliga."

A segunda solicitação deverá conseguir utilizar o contexto da primeira para identificar a entidade mencionada.

Essa associação deverá possuir limites temporais e regras de desambiguação.

**5.5. Tratar ambiguidades**

Se houver mais de uma entidade possível, o sistema não deverá escolher arbitrariamente.

Exemplo:

Existem duas lâmpadas cadastradas no quarto.

Usuário: "Desliga a luz."

O sistema deverá solicitar esclarecimento quando não for possível determinar com segurança qual dispositivo deverá ser acionado.

**5.6. Disponibilidade das capacidades**

O sistema deverá distinguir:

- Ferramenta registrada e disponível.
- Ferramenta registrada, mas temporariamente indisponível.
- Entidade inexistente.
- Entidade indisponível.
- Capacidade não suportada.
- Integração desconectada.

Essa distinção permitirá produzir respostas corretas sem inventar resultados.

### Arquivos envolvidos

- `tools/builtin/home_assistant.py`
- `tools/registry.py`
- `core/orchestrator/engine.py`
- `core/contracts/tool.py`
- `core/conversation/context_builder.py`
- `docs/HOME_ASSISTANT.md`

Novos módulos de resolução de entidades poderão ser adicionados conforme a arquitetura definida.

### Testes obrigatórios

- Resolução de nomes e aliases.
- Entidades inexistentes.
- Entidades duplicadas ou ambíguas.
- Referências contextuais.
- Entidades indisponíveis.
- Capacidades não suportadas.
- Integração com ferramentas remotas.
- Garantia de que o CORE não acessa diretamente credenciais exclusivas do SERVER.

### Critérios de conclusão

- O sistema deverá relacionar linguagem natural a entidades reais.
- Nenhuma entidade deverá ser inventada.
- Referências contextuais deverão funcionar de maneira controlada.
- Ambiguidades deverão produzir esclarecimentos.
- A separação entre SERVER e CORE deverá permanecer intacta.

---

# Frente 6 — Fast Path: Execução Operacional sem LLM

**Objetivo:** implementar um fluxo rápido de execução para operações conhecidas, determinísticas e suficientemente seguras, sem exigir a participação do LLM.

### Conceito

O Fast Path será o mecanismo responsável por resolver diretamente operações que já possam ser compreendidas e executadas pela arquitetura local.

Exemplo:

Usuário: "Que horas são?"

Fluxo esperado:

1. Reconhecer a intenção.
2. Identificar a ferramenta de horário.
3. Executar a ferramenta.
4. Receber o resultado.
5. Construir uma resposta natural.
6. Responder ao usuário.

Nenhuma chamada ao LLM deverá ser realizada.

Outro exemplo:

Usuário: "Qual é o estado da luz do quarto?"

O sistema poderá resolver a entidade e utilizar uma operação de consulta existente, desde que esteja disponível e autorizada.

### Como implementar

**6.1. Criar critérios de elegibilidade**

Uma solicitação somente poderá utilizar o Fast Path quando:

- A intenção for conhecida.
- A confiança for suficiente.
- Todos os parâmetros necessários estiverem disponíveis.
- A ferramenta estiver registrada.
- A ferramenta estiver disponível.
- As entidades estiverem resolvidas quando necessário.
- A operação não exigir raciocínio ou planejamento complexo.
- O nível de segurança permitir o fluxo proposto.

Quando esses critérios não forem atendidos, o sistema deverá utilizar o fluxo tradicional.

**6.2. Separar leitura e alteração de estado**

Operações simples de consulta poderão ser candidatas naturais ao Fast Path.

Operações que alteram o estado de dispositivos ou sistemas deverão respeitar o nível de segurança definido.

O Fast Path não deverá transformar uma operação que exige confirmação em uma operação executada automaticamente.

Exemplo:

- Consultar o estado de uma lâmpada: poderá ser executado diretamente se autorizado.
- Desligar uma lâmpada: deverá respeitar a política configurada para essa operação.
- Executar uma operação classificada como RED: deverá continuar bloqueada ou seguir o tratamento de segurança definido pelo projeto.

**6.3. Reutilizar os mecanismos oficiais de execução**

O Fast Path não deverá executar diretamente `tool.execute()` ou criar uma rota alternativa que ignore o Registry.

A execução deverá continuar passando pelo mecanismo central, respeitando a arquitetura existente:

- Registry.
- ToolExecutor.
- PolicyEngine.
- Regras de visibilidade.
- Regras de autorização.
- Confirmações.
- Tratamento de erros.

As particularidades do fluxo de aprovação deverão permanecer compatíveis com o mecanismo atual.

**6.4. Validar os parâmetros**

Antes da execução, os argumentos deverão passar pelas validações previstas no contrato da ferramenta.

Parâmetros ausentes, inválidos ou incompatíveis deverão impedir a execução.

Não deverá existir conversão silenciosa que transforme uma solicitação ambígua em uma ação potencialmente perigosa.

**6.5. Definir fallback para o fluxo tradicional**

Quando o Fast Path não conseguir resolver uma solicitação:

1. Preservar o texto original.
2. Preservar as informações já identificadas.
3. Preservar o contexto relevante.
4. Encaminhar a solicitação ao Orchestrator e ao LLM quando necessário.
5. Evitar executar novamente uma operação que já tenha sido concluída.

**6.6. Evitar duplicidade de execução**

Solicitações provenientes de voz, eventos repetidos ou tentativas de repetição não deverão provocar ações duplicadas indevidamente.

Quando aplicável, deverão ser utilizados mecanismos de identificação da operação, idempotência ou controle de repetição.

### Arquivos envolvidos

- `core/orchestrator/engine.py`
- `core/orchestrator/tool_executor.py`
- `tools/registry.py`
- `core/context/tool_selector.py`
- `core/contracts/tool.py`
- `core/events/models.py`

### Testes obrigatórios

- Execução de intenção conhecida sem chamada ao LLM.
- Execução de consulta local.
- Execução de ferramenta remota.
- Parâmetros inválidos.
- Parâmetros ausentes.
- Ferramenta indisponível.
- Intenção com baixa confiança.
- Confirmação de operação YELLOW.
- Bloqueio de operação RED.
- Garantia de que o Registry e o PolicyEngine são utilizados.
- Garantia de ausência de execução duplicada.
- Fallback para o fluxo tradicional.

### Critérios de conclusão

- Operações elegíveis deverão ser executadas sem chamar o LLM.
- A execução deverá passar integralmente pelos mecanismos oficiais.
- O Fast Path não deverá contornar confirmações ou políticas.
- Falhas deverão produzir resultados estruturados.
- O fallback deverá preservar o contexto e impedir duplicidade.

---

# Frente 7 — Geração de Respostas Naturais e Contextualizadas

**Objetivo:** permitir que o J.A.R.V.I.S. responda de forma natural, contextual e coerente mesmo quando o LLM não for utilizado.

### Problema a resolver

Uma arquitetura local que utiliza apenas respostas fixas pode se tornar excessivamente robótica.

O objetivo não é substituir uma experiência inteligente por uma sequência de mensagens predefinidas.

O J.A.R.V.I.S. deverá conseguir comunicar resultados reais de maneira natural, considerando a solicitação, a operação executada e o contexto da conversa.

### Exemplo de comportamento desejado

Usuário: "Que horas são?"

Possíveis respostas, conforme o contexto:

- "Agora são 14h32."
- "São 14h32."
- "Agora são 14h32. Ainda temos bastante tempo antes do próximo compromisso."

A última resposta somente deverá ser utilizada quando houver contexto válido que justifique essa informação.

Outro exemplo:

Usuário: "A luz do quarto está ligada?"

Resposta: "Está sim, a luz do quarto está ligada."

Se o sistema tiver identificado mais de uma entidade ou não tiver conseguido consultar o dispositivo, deverá comunicar essa situação em vez de inventar um estado.

### Como implementar

**7.1. Criar um resultado operacional estruturado**

As ferramentas e os fluxos de execução deverão produzir resultados que possam ser interpretados sem depender de mensagens soltas.

O contrato poderá seguir conceitualmente a estrutura `OperationOutcome`, contendo:

- `success`: resultado da operação.
- `operation`: identificação da operação.
- `data`: dados retornados.
- `entity`: entidade envolvida, quando aplicável.
- `error`: erro ocorrido, quando existente.
- `requires_confirmation`: indicação de confirmação pendente.
- `source`: origem do resultado.
- `timestamp`: momento relevante da operação.

A implementação deverá respeitar os contratos e padrões existentes no projeto.

**7.2. Criar uma camada local de resposta**

Implementar um componente responsável por transformar resultados operacionais em respostas naturais.

Essa camada poderá utilizar:

- Modelos linguísticos curtos.
- Variações de construção de frases.
- Contexto recente.
- Informações relevantes da operação.
- Preferências de comunicação, quando disponíveis.
- Regras de coerência e factualidade.

O mecanismo deverá permanecer independente do provedor de LLM.

**7.3. Evitar mensagens fixas repetitivas**

Mensagens fixas poderão continuar existindo para casos muito específicos, como erros conhecidos, avisos críticos e confirmações padronizadas.

Entretanto, o fluxo normal de conversação deverá evitar repetir sempre a mesma frase.

A variação deverá ser contextual, e não aleatória a ponto de prejudicar a compreensão.

**7.4. Separar resultado de interpretação**

A camada de resposta não deverá modificar o resultado real de uma ferramenta.

Se uma lâmpada não respondeu, o sistema não poderá responder que ela foi desligada.

Se uma consulta falhou, deverá informar que não conseguiu verificar a informação.

Se uma ação estiver aguardando confirmação, deverá comunicar que ainda não foi executada.

**7.5. Preservar possibilidade de utilização do LLM**

O LLM continuará sendo a melhor opção para respostas que exijam explicações complexas, elaboração avançada, criatividade ou raciocínio contextual amplo.

A geração local deverá ser utilizada principalmente para comunicar resultados conhecidos e operações de baixa complexidade.

### Arquivos envolvidos

- `core/orchestrator/engine.py`
- `core/conversation/context_builder.py`
- `core/contracts/`
- `core/events/models.py`

Novo componente local de geração de respostas poderá ser criado, desde que mantenha separação clara entre interpretação, execução e apresentação.

### Testes obrigatórios

- Respostas baseadas em resultados reais.
- Diferentes formulações para uma mesma operação.
- Respostas de sucesso e falha.
- Operação pendente de confirmação.
- Entidade não encontrada.
- Informação indisponível.
- Contexto válido e contexto ausente.
- Garantia de que dados não retornados pela ferramenta não aparecem como fatos.

### Critérios de conclusão

- O J.A.R.V.I.S. deverá produzir respostas naturais sem depender do LLM para operações simples.
- As respostas deverão representar fielmente os resultados recebidos.
- A camada deverá suportar variações sem introduzir informações inventadas.
- Erros e confirmações pendentes deverão ser comunicados corretamente.
- O sistema não deverá se tornar dependente de frases fixas para cada operação.

---

# Frente 8 — Contexto Conversacional e Continuidade

**Objetivo:** permitir que o J.A.R.V.I.S. mantenha continuidade entre mensagens relacionadas, inclusive durante execuções locais que não utilizem o LLM.

### Conceito

O sistema deverá entender que uma conversa é composta por mensagens relacionadas, e não por solicitações completamente independentes.

Exemplo:

Usuário: "Qual é a temperatura do quarto?"

J.A.R.V.I.S.: "Está em 24 °C."

Usuário: "E da sala?"

J.A.R.V.I.S.: "A sala está em 26 °C."

Usuário: "Aumenta um pouco."

O sistema deverá conseguir reconhecer que a última mensagem depende do contexto anterior.

Entretanto, deverá verificar se a referência e a intenção são suficientemente claras antes de executar uma operação.

### Como implementar

**8.1. Criar um contexto operacional compacto**

O contexto deverá armazenar somente as informações necessárias para a continuidade das operações.

Poderá conter:

- Última intenção identificada.
- Última entidade consultada.
- Último resultado relevante.
- Operações recentes.
- Entidades mencionadas.
- Referências ainda válidas.
- Informações necessárias para completar uma solicitação.

Esse contexto não deverá substituir o sistema de memória já existente.

**8.2. Diferenciar contexto recente de memória persistente**

O contexto operacional deverá possuir duração e regras próprias.

Informações recentes não deverão ser tratadas automaticamente como preferências permanentes ou memórias de longo prazo.

A arquitetura deverá respeitar os mecanismos existentes de memória.

**8.3. Criar regras de expiração**

Informações que perderem relevância deverão ser removidas ou deixarem de ser utilizadas.

O período de validade deverá considerar o tipo de informação.

Uma referência a uma lâmpada mencionada segundos antes pode continuar relevante; uma referência antiga, em outro assunto, pode não ser mais apropriada.

**8.4. Resolver referências ambíguas**

O sistema deverá identificar quando uma mensagem depende de contexto, mas não possui informações suficientes para resolver a solicitação.

Quando necessário, deverá pedir esclarecimento.

**8.5. Compartilhar contexto com os diferentes fluxos**

O contexto operacional deverá poder ser utilizado por:

- Natural Language Understanding.
- Resolução de entidades.
- Fast Path.
- Geração local de respostas.
- Orchestrator.
- LLM.

Cada componente deverá receber somente as informações necessárias para sua responsabilidade.

### Arquivos envolvidos

- `core/conversation/context_builder.py`
- `core/orchestrator/engine.py`
- `core/contracts/`
- `core/events/models.py`
- Componentes existentes de memória, quando necessário.

### Testes obrigatórios

- Continuidade entre mensagens.
- Resolução de referências.
- Expiração de contexto.
- Mudança de assunto.
- Ambiguidade.
- Ausência de contexto.
- Compatibilidade com o LLM.
- Compatibilidade com execução local.
- Separação entre contexto recente e memória persistente.

### Critérios de conclusão

- O sistema deverá manter continuidade de maneira controlada.
- Referências contextuais deverão funcionar nos fluxos local e tradicional.
- Informações expiradas não deverão ser utilizadas indevidamente.
- Contexto não deverá ser confundido com memória persistente.
- Ambiguidades deverão ser tratadas corretamente.

---

# Frente 9 — Runtime, Concorrência e Eficiência Operacional

**Objetivo:** melhorar a eficiência interna do sistema, reduzindo trabalho redundante e preparando a arquitetura para múltiplas solicitações e operações simultâneas.

### Conceito

A melhoria do desempenho não deverá depender apenas de reduzir chamadas ao LLM.

O runtime também deverá ser capaz de administrar corretamente operações concorrentes, tempos de espera, cancelamentos, falhas e recursos compartilhados.

### Como implementar

**9.1. Revisar o fluxo assíncrono**

Avaliar os pontos em que operações assíncronas podem estar sendo executadas de maneira desnecessariamente sequencial.

Operações independentes poderão ser executadas em paralelo quando isso não comprometer a consistência ou a ordem necessária.

Não deverá existir paralelismo indiscriminado em operações que dependam umas das outras.

**9.2. Implementar limites de concorrência**

Ferramentas e integrações deverão possuir limites de execução adequados.

Esses limites deverão impedir que muitas operações simultâneas sobrecarreguem o SERVER, o CORE ou serviços externos.

**9.3. Melhorar timeouts e cancelamentos**

Cada operação deverá respeitar os limites de tempo definidos para sua categoria.

Solicitações canceladas não deverão continuar consumindo recursos desnecessariamente.

O cancelamento deverá ser propagado pelos componentes envolvidos sempre que tecnicamente possível.

**9.4. Implementar cache somente quando seguro**

Informações que possam ser reutilizadas poderão utilizar cache, desde que apresentem critérios adequados de validade.

Exemplos possíveis:

- Metadados de ferramentas.
- Catálogo de capacidades.
- Informações relativamente estáveis.
- Consultas cujo resultado tenha uma validade definida.

O cache não deverá manter estados de dispositivos como verdade permanente.

Informações mutáveis deverão ter invalidação adequada após operações que alterem seu estado.

Dados sensíveis não deverão ser armazenados indiscriminadamente.

**9.5. Preservar consistência entre operações**

O sistema deverá identificar operações que não podem ser executadas simultaneamente sobre o mesmo recurso.

Quando necessário, utilizar controles de concorrência, bloqueios ou mecanismos de serialização específicos.

**9.6. Melhorar observabilidade**

Registrar métricas operacionais que permitam identificar:

- Tempo de interpretação.
- Tempo de seleção.
- Tempo de execução.
- Tempo total de resposta.
- Número de chamadas ao LLM.
- Número de ferramentas selecionadas.
- Número de ferramentas executadas.
- Quantidade de tokens.
- Frequência de fallback.
- Falhas por componente.
- Taxa de utilização do Fast Path.

Os registros não deverão expor credenciais, conteúdo sensível ou dados privados desnecessários.

### Arquivos envolvidos

- `core/orchestrator/engine.py`
- `core/orchestrator/tool_executor.py`
- `tools/registry.py`
- `core/context/budget.py`
- `core/events/models.py`
- `core/config.py`

### Testes obrigatórios

- Execução concorrente de operações independentes.
- Controle de operações dependentes.
- Timeout.
- Cancelamento.
- Falhas de ferramentas.
- Recuperação após falhas.
- Invalidação de cache.
- Solicitações simultâneas.
- Ausência de execução duplicada.
- Integridade dos eventos emitidos.

### Critérios de conclusão

- Operações concorrentes deverão respeitar a consistência do sistema.
- Timeouts e cancelamentos deverão ser controlados.
- O cache deverá respeitar a validade dos dados.
- As métricas deverão permitir analisar gargalos.
- A otimização não deverá introduzir condições de corrida ou inconsistências.

---

# Frente 10 — Inteligência Offline e Gerenciamento de Modelos Locais

**Objetivo:** garantir que o J.A.R.V.I.S. mantenha o funcionamento de suas capacidades essenciais mesmo sem conexão com a internet ou disponibilidade de provedores externos.

### Conceito

O funcionamento offline não deverá ser entendido como a obrigação de executar todas as tarefas com um modelo local.

Operações determinísticas, como consulta de horário, resolução de intenções conhecidas e execução de ferramentas locais, deverão funcionar sem depender de qualquer modelo generativo.

Para tarefas que realmente exigem raciocínio, o sistema poderá utilizar modelos locais disponíveis.

Quando não houver um modelo adequado, deverá informar suas limitações e preservar as funcionalidades independentes.

### Como implementar

**10.1. Criar uma classificação de dependências**

Cada capacidade deverá indicar de quais recursos depende.

Exemplos:

- Consulta de horário: recurso local.
- Consulta de informações de sistema: recurso local.
- Consulta de dispositivo Home Assistant: depende da conectividade com o SERVER e da integração.
- Consulta de informações na internet: depende de conectividade externa.
- Raciocínio generativo: depende de um provedor de LLM disponível.

Essa classificação permitirá determinar quais capacidades continuam operacionais durante uma desconexão.

**10.2. Integrar ao roteamento de provedores**

O sistema deverá identificar se existe um provedor local disponível.

Quando houver um modelo local configurado, poderá utilizá-lo para tarefas compatíveis.

Quando não houver, deverá aplicar o comportamento de contingência apropriado.

**10.3. Preservar o funcionamento determinístico**

A indisponibilidade de um modelo não deverá bloquear:

- Interpretação de intenções conhecidas.
- Fast Path.
- Consultas determinísticas.
- Ferramentas locais.
- Respostas naturais baseadas em resultados conhecidos.
- Operações independentes de serviços externos.

**10.4. Implementar gerenciamento de disponibilidade**

O sistema deverá identificar:

- Modelo configurado.
- Modelo instalado.
- Modelo carregado.
- Modelo disponível.
- Falha de inicialização.
- Falha durante a inferência.
- Provedor indisponível.

Essas informações deverão alimentar o roteamento, sem presumir que um modelo está disponível apenas porque foi configurado.

**10.5. Evitar carregamentos desnecessários**

Modelos locais não deverão ser carregados indiscriminadamente para operações que podem ser resolvidas por mecanismos determinísticos.

A inicialização e o gerenciamento de recursos deverão considerar a memória e a capacidade de processamento disponíveis.

**10.6. Definir comportamento de degradação**

Quando não houver conexão e uma solicitação exigir informações externas, o J.A.R.V.I.S. deverá explicar a limitação.

Quando um provedor de IA estiver indisponível, operações locais deverão continuar funcionando.

O sistema não deverá entrar em ciclos intermináveis de tentativa de conexão ou fallback.

### Arquivos envolvidos

- `core/llm/router.py`
- `core/config.py`
- `core/orchestrator/engine.py`
- `core/contracts/llm.py`
- Módulos locais de NLU e geração de respostas.

### Testes obrigatórios

- Execução sem internet.
- Provedor externo indisponível.
- Provedor local disponível.
- Provedor local indisponível.
- Falha durante carregamento do modelo.
- Falha durante inferência.
- Operações determinísticas sem LLM.
- Continuidade de recursos locais.
- Comportamento correto em solicitações que exigem serviços externos.

### Critérios de conclusão

- O sistema deverá possuir funcionamento offline para suas capacidades independentes de internet.
- A indisponibilidade do LLM não deverá interromper operações determinísticas.
- O roteamento deverá reconhecer a disponibilidade real dos modelos.
- O consumo de recursos deverá ser controlado.
- As limitações de conectividade deverão ser comunicadas corretamente.

---

# Frente 11 — Segurança, Integridade, Observabilidade e Validação Final

**Objetivo:** garantir que todas as melhorias introduzidas na Fase 16.5 mantenham os padrões de segurança do J.A.R.V.I.S., possuam comportamento verificável e apresentem ganhos reais de desempenho.

Esta frente é transversal e deverá ser considerada durante toda a implementação, não apenas no final.

### 11.1. Preservar a autoridade do PolicyEngine

Nenhuma camada nova poderá executar diretamente uma ferramenta ignorando as políticas existentes.

O caminho oficial de autorização deverá permanecer obrigatório.

A seleção de uma ferramenta não significa autorização para executá-la.

A identificação de uma intenção também não significa que a ação esteja autorizada.

O Fast Path deverá respeitar as mesmas regras aplicadas ao fluxo tradicional.

### 11.2. Corrigir o isolamento entre provedores locais e externos

Foi identificado um ponto que merece atenção especial no roteamento atual.

A construção da lista de ferramentas utiliza `is_next_provider_local()` para identificar a natureza do primeiro provedor previsto.

Entretanto, o roteador pode tentar outro provedor quando o primeiro falhar.

Caso a mesma solicitação e as mesmas definições de ferramentas sejam reutilizadas durante esse fallback, existe o risco de informações que deveriam permanecer locais serem encaminhadas a um provedor externo.

A implementação deverá resolver esse problema no próprio fluxo de roteamento.

**Requisitos obrigatórios:**

- O nível de confiança e compartilhamento deverá ser avaliado para cada tentativa de provedor.
- Um provedor externo não poderá receber definições de ferramentas `LOCAL_ONLY`.
- Descrições, esquemas, argumentos, contexto e resultados classificados como locais deverão respeitar as restrições de compartilhamento.
- O fallback entre provedores de níveis de confiança diferentes deverá ser controlado.
- Caso não seja possível construir uma solicitação compatível com o destino, o sistema deverá interromper o fallback de maneira segura.
- O roteamento deverá evitar reutilizar conteúdo local em uma tentativa externa sem uma nova avaliação de segurança.

A solução poderá utilizar reconstrução da solicitação para cada tentativa, separação de cadeias de provedores por nível de confiança ou outra abordagem equivalente.

O requisito essencial é que a classificação de segurança seja aplicada individualmente a cada provedor antes do envio.

**Teste adversarial obrigatório:**

1. Configurar um provedor local como primeira tentativa.
2. Fazer esse provedor falhar intencionalmente.
3. Configurar um provedor externo como alternativa.
4. Incluir ferramentas e informações classificadas como `LOCAL_ONLY`.
5. Verificar o conteúdo efetivamente enviado ao segundo provedor.
6. Garantir que nenhuma informação proibida seja transmitida.

Esse teste deverá validar também a proteção de contexto e não somente a lista de ferramentas.

### 11.3. Preservar visibilidade e níveis de segurança

As classificações existentes deverão permanecer válidas:

- `LOCAL_ONLY`: uso restrito ao ambiente permitido.
- `SHARED`: compartilhamento permitido conforme as políticas.
- GREEN: operação de baixo risco, conforme a política existente.
- YELLOW: operação que exige confirmação conforme a política existente.
- RED: operação de alto risco ou bloqueada conforme as regras estabelecidas.

As novas classificações e os mecanismos de seleção não poderão alterar essas responsabilidades.

### 11.4. Garantir integridade das chamadas de ferramentas

O fluxo OpenAI-compatible de chamadas de ferramentas deverá continuar respeitando a sequência correta entre:

- Mensagem do assistente contendo `tool_calls`.
- Execução autorizada.
- Mensagem com o resultado correspondente à chamada.
- Continuidade da conversa.

A otimização de esquemas e a introdução do Fast Path não poderão gerar mensagens inconsistentes ou chamadas sem resultado correspondente.

### 11.5. Implementar observabilidade sem expor informações sensíveis

Deverão existir métricas suficientes para identificar o comportamento real do sistema.

Os registros deverão permitir verificar:

- Por que uma ferramenta foi selecionada.
- Por que uma ferramenta foi descartada.
- Qual mecanismo identificou a intenção.
- Por que o Fast Path foi utilizado ou recusado.
- Qual provedor foi selecionado.
- Se houve fallback.
- Quantos tokens foram utilizados.
- Quanto tempo cada etapa consumiu.
- Se uma operação exigiu confirmação.
- Se houve falha de execução.

Os logs não deverão registrar indiscriminadamente credenciais, tokens de autenticação, dados pessoais ou conteúdo classificado como privado.

### 11.6. Implementar validação de desempenho

Antes de otimizar, deverá ser estabelecida uma linha de base com o comportamento atual.

Os testes deverão comparar:

- Tempo de resposta antes e depois.
- Tempo de interpretação local.
- Tempo de seleção das ferramentas.
- Tempo de construção das definições.
- Tempo de execução.
- Consumo de tokens.
- Quantidade de chamadas ao LLM.
- Taxa de sucesso.
- Taxa de seleção correta.
- Quantidade de ferramentas disponibilizadas.

Deverão ser avaliados cenários com poucas ferramentas e catálogos maiores.

As medições deverão distinguir processamento local, comunicação com o SERVER e latência de serviços externos.

### 11.7. Estratégia de testes

A validação deverá incluir:

**Testes unitários**

Validar isoladamente normalização, classificação de intenção, resolução de entidades, catálogo, seleção, geração de respostas e roteamento.

**Testes de integração**

Validar a comunicação entre NLU, Registry, ToolExecutor, PolicyEngine, Orchestrator e Router.

**Testes ponta a ponta**

Simular solicitações reais, desde a entrada do usuário até a resposta final.

**Testes de segurança**

Validar permissões, visibilidade, confirmações, isolamento de provedores, parâmetros e tentativas de execução indevida.

**Testes de desempenho**

Medir latências, consumo de tokens, reutilização de cache e comportamento em condições de concorrência.

**Testes offline**

Verificar o funcionamento sem internet e sem provedores externos.

**Testes de regressão**

Garantir que as funcionalidades anteriores continuem funcionando.

### Arquivos envolvidos

- `core/llm/router.py`
- `core/orchestrator/engine.py`
- `core/orchestrator/tool_executor.py`
- `tools/registry.py`
- `core/contracts/tool.py`
- `core/contracts/llm.py`
- `core/config.py`
- `docs/SECURITY.md`
- `tests/unit/`
- `tests/integration/`

### Critérios de conclusão

- Nenhuma regra de segurança poderá ser contornada.
- O isolamento entre ferramentas locais e provedores externos deverá estar comprovado por testes.
- O fallback deverá respeitar a classificação dos dados para cada provedor.
- O fluxo de chamadas de ferramentas deverá permanecer consistente.
- As métricas deverão demonstrar os ganhos obtidos.
- Todos os testes anteriores e novos deverão passar.
- Não deverão existir regressões críticas conhecidas.

---

# 3. Arquivos e componentes envolvidos

Os caminhos abaixo representam os principais pontos de integração identificados na arquitetura atual. Novos arquivos poderão ser criados quando houver justificativa técnica, respeitando a organização existente.

| Arquivo ou diretório | Responsabilidade na Fase 16.5 |
|---|---|
| `core/context/tool_selector.py` | Seleção contextual, relevância e confiança das ferramentas. |
| `core/context/budget.py` | Estimativa e controle do orçamento de tokens. |
| `core/contracts/tool.py` | Metadados, contratos e esquemas das ferramentas. |
| `core/contracts/llm.py` | Contratos de comunicação com provedores e uso de tokens. |
| `core/orchestrator/engine.py` | Integração dos fluxos de NLU, seleção, Fast Path e LLM. |
| `core/orchestrator/tool_executor.py` | Execução das ferramentas pelo mecanismo oficial. |
| `core/llm/router.py` | Seleção de provedores, fallback e isolamento de dados. |
| `core/llm/converters.py` | Conversão dos metadados selecionados para definições aceitas pelo LLM. |
| `core/conversation/context_builder.py` | Construção do contexto e das definições disponibilizadas ao modelo. |
| `tools/registry.py` | Registro, consulta, cache e integridade do catálogo. |
| `tools/builtin/home_assistant.py` | Integração com recursos do Home Assistant. |
| `tools/__init__.py` | Registro e inicialização das ferramentas padrão. |
| `core/config.py` | Configurações de seleção, limites e comportamento operacional. |
| `core/events/models.py` | Eventos e comunicação entre os componentes. |
| `docs/SECURITY.md` | Documentação das políticas e do isolamento de dados. |
| `docs/HOME_ASSISTANT.md` | Documentação da integração com o Home Assistant. |
| `tests/unit/` | Testes unitários dos componentes. |
| `tests/integration/` | Testes dos fluxos integrados. |

Novos módulos de NLU, resolução de entidades, Fast Path, respostas naturais e catálogo poderão ser criados em diretórios próprios, caso isso resulte em melhor separação de responsabilidades.

A criação de novos arquivos deverá ser decidida após a inspeção da organização real do repositório. Não duplicar responsabilidades que já existam em outros módulos.

---

# 4. Ordem de implementação e dependências

A Fase 16.5 deverá ser desenvolvida incrementalmente.

A ordem abaixo considera as dependências arquiteturais e a necessidade de validar segurança antes de habilitar os novos caminhos de execução.

### Etapa 0 — Preparação e auditoria

Antes de modificar o código:

1. Confirmar a conclusão e integração da Fase 16.
2. Verificar a situação da Fase 15.3 e sincronizar as alterações existentes que devam integrar a branch de trabalho.
3. Examinar novamente a implementação atual, pois o repositório poderá ter recebido alterações desde a análise que fundamentou esta especificação.
4. Registrar os resultados dos testes existentes.
5. Medir o desempenho atual em cenários representativos.
6. Registrar a quantidade de ferramentas e o consumo estimado de tokens.
7. Confirmar os contratos e as responsabilidades existentes.

**Resultado esperado:** linha de base técnica e ambiente preparado para a implementação.

### Etapa 1 — Fundamentos de segurança

Implementar e validar a proteção do roteamento entre provedores locais e externos.

Resolver o risco de reutilização de ferramentas e contexto local durante fallback para provedores externos.

**Dependência:** auditoria inicial.

### Etapa 2 — Catálogo e Registry

Otimizar registro, consulta e cache dos metadados.

Remover reconstruções desnecessárias.

**Dependência:** auditoria inicial.

### Etapa 3 — Compreensão local de intenções

Implementar normalização, classificação e contratos do NLU.

**Dependência:** contratos e configuração existentes; poderá evoluir em paralelo ao catálogo.

### Etapa 4 — Resolução de entidades e capacidades

Implementar o mapeamento entre solicitações naturais, entidades reais e capacidades disponíveis.

**Dependência:** NLU e catálogo de capacidades.

### Etapa 5 — Descoberta e seleção contextual

Aprimorar o Tool Selector utilizando as informações do NLU e do catálogo.

**Dependência:** catálogo e classificação de intenções.

### Etapa 6 — Carregamento progressivo de esquemas

Integrar a seleção com a conversão dos metadados para o formato do LLM.

**Dependência:** catálogo e seletor.

### Etapa 7 — Fast Path

Implementar execução direta para operações elegíveis.

**Dependência:** NLU, resolução de entidades, catálogo, seleção e segurança.

### Etapa 8 — Respostas naturais

Implementar a camada local de respostas baseada em resultados estruturados.

**Dependência:** contratos de resultados operacionais e Fast Path.

### Etapa 9 — Continuidade conversacional

Implementar o contexto operacional e sua integração com os fluxos locais e tradicionais.

**Dependência:** NLU, resolução de entidades e resultados operacionais.

### Etapa 10 — Runtime e eficiência operacional

Aprimorar concorrência, cache, cancelamento, timeouts e observabilidade.

**Dependência:** integração dos componentes anteriores, embora melhorias independentes possam ser antecipadas.

### Etapa 11 — Inteligência offline

Integrar as novas capacidades ao roteamento de modelos locais e ao comportamento de contingência.

**Dependência:** roteamento, NLU, Fast Path e geração local de respostas.

### Etapa 12 — Validação completa

Executar a matriz de testes, comparar os benchmarks e revisar a documentação.

Nenhuma frente deverá ser considerada concluída apenas porque sua implementação foi escrita. A conclusão dependerá dos testes e critérios verificáveis.

---

# 5. Critérios gerais de aceitação da Fase 16.5

A Fase 16.5 somente poderá ser considerada concluída quando todos os requisitos a seguir forem atendidos.

### Funcionamento

- O J.A.R.V.I.S. deverá reconhecer intenções conhecidas localmente.
- Operações determinísticas elegíveis deverão funcionar sem chamadas ao LLM.
- Solicitações complexas deverão continuar utilizando o fluxo de raciocínio apropriado.
- O sistema deverá identificar entidades reais e capacidades disponíveis.
- O contexto conversacional deverá funcionar sem depender exclusivamente do LLM.
- O sistema deverá produzir respostas naturais com base nos resultados reais.

### Eficiência

- Metadados deverão ser reutilizados adequadamente.
- Ferramentas deverão ser selecionadas antes da conversão de seus esquemas.
- Somente as definições completas das ferramentas selecionadas deverão ser enviadas ao LLM.
- O consumo de tokens deverá ser medido antes e depois.
- O Fast Path deverá apresentar latência significativamente inferior ao fluxo que exige uma chamada generativa.
- O processamento local simples deverá buscar o objetivo de resposta inferior a 1 segundo, medido em condições controladas e com o hardware documentado.
- O tempo de execução de integrações remotas deverá ser mensurado separadamente, pois depende de fatores externos ao processamento local.

### Segurança

- Nenhum componente poderá ignorar o Registry ou o PolicyEngine.
- Confirmações existentes deverão permanecer obrigatórias.
- Ferramentas `LOCAL_ONLY` não poderão ser enviadas a provedores externos.
- O fallback deverá respeitar a classificação de confiança de cada provedor.
- Nenhuma ação poderá ser executada com parâmetros inválidos.
- Operações ambíguas deverão ser esclarecidas, não presumidas.

### Offline

- O NLU local deverá funcionar sem internet.
- Operações determinísticas independentes de serviços externos deverão continuar funcionando.
- O Fast Path deverá funcionar sem provedor de LLM.
- A indisponibilidade de provedores deverá produzir degradação controlada.

### Qualidade

- Todos os novos testes deverão passar.
- Os testes anteriores não deverão apresentar regressões.
- A documentação técnica deverá refletir o comportamento efetivamente implementado.
- Os resultados dos benchmarks deverão estar registrados.
- A arquitetura deverá permanecer modular e preparada para futuras expansões.

---

# 6. Métricas e benchmarking

Antes de implementar as otimizações, deverá ser criada uma linha de base.

O objetivo não é definir números arbitrários, mas comparar o comportamento real antes e depois da fase.

As medições deverão considerar pelo menos três cenários:

**Cenário A — Operação determinística local**

Exemplo: consulta de horário ou informação local.

Métricas:

- Tempo total.
- Tempo de interpretação.
- Tempo de execução.
- Tempo de geração da resposta.
- Chamadas ao LLM.

**Cenário B — Operação com ferramenta**

Exemplo: consultar o estado de um dispositivo.

Métricas:

- Tempo de seleção.
- Tempo de construção do esquema.
- Tempo de execução da ferramenta.
- Latência de comunicação com o SERVER.
- Tokens enviados ao LLM, quando utilizado.

**Cenário C — Solicitação complexa**

Exemplo: solicitação que exige planejamento e utilização de múltiplas ferramentas.

Métricas:

- Tempo total.
- Quantidade de ferramentas disponibilizadas.
- Quantidade de ferramentas utilizadas.
- Tokens de entrada.
- Tokens de saída.
- Quantidade de chamadas ao LLM.
- Taxa de sucesso.

Sempre que possível, registrar p50, p95 e média, separando aquecimento inicial de execuções recorrentes.

### Alvos de desempenho

Os seguintes alvos deverão orientar o desenvolvimento:

- Fast Path: processamento local de operações simples com objetivo de p95 inferior a 1 segundo, em ambiente de referência documentado.
- Seleção: reduzir significativamente o número de ferramentas disponibilizadas em relação ao catálogo completo.
- Tokens: atingir redução mensurável de pelo menos 30% nos tokens destinados às definições de ferramentas em cenários de catálogo amplo, sem perda relevante de cobertura ou precisão.
- Qualidade: não reduzir a taxa de sucesso das chamadas de ferramentas em consequência da seleção.
- Offline: executar todas as capacidades determinísticas independentes de serviços externos sem precisar de um provedor de LLM.

Os resultados deverão ser comparados com a linha de base. Caso algum alvo se mostre inadequado ao ambiente real, sua revisão deverá ser justificada por medições, e não por suposição.

---

# 7. Decisões arquiteturais e restrições

Durante a fase, deverão ser respeitadas as seguintes decisões:

### 7.1. Não substituir o LLM

A Fase 16.5 não tem como objetivo eliminar o modelo de linguagem.

O objetivo é retirar do LLM tarefas desnecessárias, preservando seu uso em situações que realmente exigem raciocínio e capacidade generativa.

### 7.2. Não criar um segundo sistema de ferramentas

Não deverá existir um mecanismo paralelo ao Registry para executar ferramentas.

Novas camadas poderão descobrir, classificar e preparar ferramentas, mas a execução continuará subordinada à arquitetura oficial.

### 7.3. Não duplicar a política de segurança

O Fast Path e os demais componentes não deverão implementar regras próprias que substituam o PolicyEngine.

As novas camadas deverão consultar e respeitar as políticas existentes.

### 7.4. Não transformar todas as respostas em templates

A geração local deverá ser capaz de produzir respostas contextuais e variadas.

Templates poderão ser utilizados como recurso interno, mas não deverão representar a totalidade da experiência conversacional.

### 7.5. Não introduzir modelos locais sem necessidade

O reconhecimento de intenções e a execução determinística deverão priorizar mecanismos leves.

Modelos locais adicionais somente deverão ser incorporados quando houver benefício técnico comprovado.

### 7.6. Não reescrever tudo em Rust ou outra linguagem

A linguagem atual deverá ser mantida enquanto atender aos requisitos.

A possibilidade de utilizar Rust ou outra linguagem deverá ser avaliada apenas em componentes cujo perfil de desempenho demonstre um gargalo real e cuja migração apresente benefícios superiores aos custos de manutenção e integração.

### 7.7. Preservar contratos existentes

Alterações nos contratos públicos deverão ser compatíveis com os consumidores atuais.

Quando uma mudança incompatível for realmente necessária, deverá existir plano de migração e testes específicos.

---

# 8. Entregáveis esperados

Ao concluir a Fase 16.5, o projeto deverá possuir:

1. Catálogo de ferramentas otimizado e com metadados reutilizáveis.
2. Mecanismo local de compreensão de intenções.
3. Seleção contextual de ferramentas mais precisa.
4. Carregamento progressivo de esquemas.
5. Resolução de entidades e capacidades.
6. Fast Path para operações determinísticas elegíveis.
7. Camada local de respostas naturais.
8. Contexto operacional para continuidade de conversas.
9. Runtime com controle adequado de concorrência, cache e cancelamento.
10. Integração com o funcionamento offline.
11. Isolamento de informações entre provedores locais e externos devidamente testado.
12. Testes unitários, de integração, ponta a ponta, segurança e desempenho.
13. Documentação técnica atualizada.
14. Relatório comparativo de benchmarks antes e depois da fase.

---

# 9. Definição de conclusão

A Fase 16.5 estará concluída quando o J.A.R.V.I.S. conseguir identificar e resolver localmente operações simples, selecionar ferramentas de forma contextual, disponibilizar ao LLM somente os esquemas relevantes quando houver necessidade de utilizá-lo, manter respostas naturais e contextualizadas e continuar funcionando em suas capacidades independentes de internet.

Tudo isso deverá ocorrer sem comprometer a segurança, as confirmações, a separação entre SERVER e CORE, a integridade do Registry ou a compatibilidade com os fluxos já existentes.

**Resultado arquitetural esperado:**

O J.A.R.V.I.S. deixa de depender do LLM como intermediário obrigatório para operações simples e passa a possuir uma camada operacional própria, capaz de compreender, decidir, executar e responder localmente quando apropriado.

O LLM permanece como componente de raciocínio avançado, e não como requisito obrigatório para cada interação.

A Fase 16.5 deverá estabelecer essa base para futuras evoluções de autonomia, memória, planejamento, especialização de agentes e integração com os recursos do ambiente.



## 10. Instruções obrigatórias para implementação por agentes de desenvolvimento

Esta especificação deverá ser considerada a referência técnica principal para a implementação da Fase 16.5.

Antes de modificar qualquer código, o agente deverá:

1. Ler integralmente esta especificação, o `ROADMAP.md`, o `AGENTS.md`, o `SECURITY.md` e a documentação relacionada aos componentes envolvidos.
2. Inspecionar a implementação atual e confirmar se os arquivos, contratos, interfaces e comportamentos descritos continuam correspondendo ao repositório.
3. Identificar divergências entre esta especificação e o código existente, apresentando os ajustes arquiteturais necessários antes de prosseguir.
4. Elaborar um plano de execução baseado nas dependências e na ordem das etapas definidas nesta fase.

Durante a implementação:

- Desenvolver uma frente por vez, respeitando suas dependências.
- Não avançar para uma frente dependente enquanto os requisitos da etapa anterior não estiverem validados.
- Preservar a arquitetura existente sempre que possível.
- Não criar componentes duplicados ou mecanismos paralelos às responsabilidades existentes.
- Não contornar políticas de segurança, confirmações ou mecanismos oficiais de execução.
- Criar e executar testes para cada componente implementado.
- Executar testes de integração e regressão conforme as alterações realizadas.
- Não remover, enfraquecer ou modificar testes apenas para obter aprovação da suíte.
- Documentar decisões arquiteturais e justificar desvios desta especificação.
- Registrar métricas e resultados de desempenho antes e depois das otimizações.

Ao concluir cada frente, registrar:

- Implementações realizadas.
- Arquivos criados e modificados.
- Testes executados e respectivos resultados.
- Critérios de aceitação atendidos.
- Problemas identificados.
- Pendências e dependências restantes.

A fase somente poderá ser declarada concluída após todas as frentes e critérios gerais de aceitação terem sido validados.

**Importante:** esta especificação define os requisitos e resultados esperados, mas não autoriza o agente a presumir que a implementação atual possui exatamente a estrutura descrita. O código existente deverá ser tratado como fonte de verdade para decisões de integração.
