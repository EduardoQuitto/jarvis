# J.A.R.V.I.S. — Regras Permanentes do Projeto

## 1. Identidade do projeto

Este repositório contém o desenvolvimento do sistema J.A.R.V.I.S., um assistente pessoal local, distribuído e modular.

O objetivo final é criar uma infraestrutura pessoal com:
- inteligência artificial local;
- controle do Windows;
- automação;
- voz;
- visão;
- memória;
- Android;
- Home Assistant;
- monitoramento;
- planejamento;
- agentes especializados;
- acesso remoto seguro.

J.A.R.V.I.S. NÃO é apenas um chatbot.
Ele é uma camada inteligente sobre uma infraestrutura distribuída.

---

## 2. Hardware definitivo

### JARVIS SERVER
Hardware: Intel Core i3-3220, 4 GB RAM, HDD 500 GB, Ubuntu Server.
Função: Home Assistant, Docker, automações, scheduler, dispositivos, monitoramento, memória central, Wake-on-LAN, serviços 24/7, gateway do JARVIS.
Esse computador deve permanecer leve.
NÃO rodar nele: LLM pesado; visão pesada; Whisper pesado; processamento intenso; agentes complexos.

### JARVIS CORE
Hardware: Intel Core i5-14400, 32 GB RAM, SSD NVMe 1 TB, GPU integrada inicialmente.
Função: LLM, Ollama, STT, TTS, visão, raciocínio, agentes, Windows Agent, processamento pesado.
A ausência de GPU dedicada NÃO deve ser tratada como requisito bloqueante. CPU é o caminho principal.

### JARVIS MOBILE
Hardware: Samsung Galaxy S20 FE, Snapdragon 865, 6 GB RAM.
Função: voz; notificações; sensores; câmera; microfone; interface móvel; ADB; controle Android.

### JARVIS PANEL
Hardware: Samsung Galaxy Tab E, Android 4.4.4.
Função: dashboard; telemetria; status; alertas; tarefas.
Não tentar transformá-lo em máquina de IA.

### NODE 2
Hardware: Pentium G3260, 8 GB RAM, GTX 650 Ti.
Função: laboratório; servidor auxiliar; tarefas secundárias; desenvolvimento; testes; serviços opcionais.
Durante a fase atual, esse computador é a máquina de desenvolvimento e NÃO é o servidor definitivo.

---

## 3. Regra arquitetural fundamental

Nunca criar uma arquitetura que dependa exclusivamente de uma máquina específica quando ela puder ser desacoplada.
Componentes devem possuir interfaces claras.
Exemplo: JARVIS Core -> LLM API
e não: JARVIS Core -> modelo específico embutido no código.

---

## 4. Regra da fonte de verdade

O LLM nunca deve inventar o estado do computador.
Dados como CPU, RAM, temperatura, disco, bateria, processos, estado de dispositivos, arquivos, serviços devem vir de ferramentas ou APIs reais.
Se uma ferramenta não existir, o sistema deve responder que não possui acesso. Nunca estimar.

---

## 5. Segurança

Nunca implementar execução arbitrária de shell diretamente a partir do LLM.
PROIBIDO criar: /execute?cmd=<qualquer coisa> ou equivalente.
Use ferramentas tipadas e específicas, como: get_cpu(); get_memory(); open_application(name); close_application(name); take_screenshot(); search_file(query); read_file(path).

---

## 6. Níveis de segurança

### Verde — ações automaticamente permitidas
Consultar sistema; consultar bateria; consultar rede; screenshot; abrir aplicativos autorizados; consultar status; consultas de memória.

### Amarelo — exigem confirmação
Reiniciar; desligar; mover arquivos; instalar software; alterar configurações; fechar vários aplicativos.

### Vermelho — exigem confirmação explícita
Excluir dados; formatar; alterar segurança; executar código arbitrário; alterar firewall; alterar credenciais; apagar grandes quantidades de arquivos.

---

## 7. Desenvolvimento

Nunca implementar grandes partes de uma vez. Sempre: analisar; planejar; implementar pequena parte; testar; corrigir; documentar; avançar.

---

## 8. Testes

Toda funcionalidade crítica deve ter teste. Depois de modificar código: executar testes; verificar lint; verificar erros; verificar comportamento; informar o resultado.
Não afirmar que algo funciona sem testar.

---

## 9. Dependências

Não adicionar dependências sem necessidade. Antes de instalar uma biblioteca: verificar se é necessária; verificar se já dá pra resolver com biblioteca padrão; verificar manutenção; verificar licença; verificar compatibilidade.

---

## 10. Código

Preferências: Python para backend e automação; FastAPI para serviços HTTP; SQLite para primeira camada de memória; HTML/CSS/JS para painel; YAML para Home Assistant; PowerShell para automação nativa Windows.
Escrever código modular. Evitar arquivos gigantes. Evitar funções gigantes. Evitar estado global desnecessário.

---

## 11. Windows Agent

Deve ter: health check; autenticação; logging; ferramentas explícitas; allowlist; validação de argumentos; tratamento de erros.
Não executar programas arbitrários enviados diretamente pelo usuário ou LLM.

---

## 12. Home Assistant

Home Assistant será a espinha dorsal do sistema distribuído. Usá-lo para: dispositivos; automações; scripts; scheduler; notificações; dashboard; presença; Wake-on-LAN; integração móvel.
Não recriar funcionalidades existentes do Home Assistant sem necessidade.

---

## 13. IA

A IA deve ser desacoplada. O código deve falar com uma interface abstrata de LLM (ex: LLMProvider).
Implementações podem incluir: Ollama; llama.cpp; outro provedor futuro.

---

## 14. Voz

Arquitetura planejada: Wake Word -> VAD -> STT -> Orchestrator -> Tool/LLM -> TTS.
STT e TTS devem permanecer desacoplados.

---

## 15. Memória

Primeira camada: SQLite. Depois: embeddings; busca semântica; banco vetorial.
Nunca adicionar banco vetorial antes de realmente precisar.

---

## 16. Android

Priorizar: 1) Home Assistant Companion; 2) ADB; 3) somente depois app nativo customizado.
Não desenvolver um aplicativo Android próprio sem provar que as soluções existentes são insuficientes.

---

## 17. Tablet

O Galaxy Tab E deve usar uma interface extremamente leve. Não utilizar frameworks modernos pesados sem necessidade.
Preferir: HTML; CSS; JavaScript simples; XMLHttpRequest/polling quando necessário.

---

## 18. Internet

Preferir processamento local quando possível. Internet somente quando necessário para: informações atuais; APIs externas; downloads; atualizações; pesquisa.
Não criar dependências de serviços pagos para funções básicas.

---

## 19. Offline-first

O J.A.R.V.I.S. deve continuar funcional sem internet nas funções que dependem apenas da LAN.

---

## 20. Privacidade

Não armazenar: senhas; tokens; códigos MFA; credenciais bancárias; dados privados desnecessários.
Nunca colocar segredos no Git. Arquivos .env devem ser protegidos.

---

## 21. Git

Sempre trabalhar com Git. Antes de grandes mudanças: git status; git diff; commit quando apropriado.
Nunca executar git push sem autorização explícita.

---

## 22. Desenvolvimento atual

O Pentium G3260 é somente a máquina temporária de desenvolvimento. O código deve ser desenvolvido de forma portátil para posteriormente ser executado no i5.
Não otimizar o projeto inteiro para as limitações do Pentium.

---

## 23. Comportamento do agente (Antigravity)

Antes de implementar uma grande funcionalidade: estudar o repositório; ler documentação; verificar arquitetura; identificar impacto; propor plano.
Quando houver ambiguidade arquitetural importante, pergunte antes de implementar.
Não reescreva componentes funcionais sem motivo.
Não criar código fictício para mascarar integração inexistente.
Nunca dizer "está funcionando" sem executar testes ou verificar comportamento.

---

## 24. Documentação

Toda decisão arquitetural relevante deve ser registrada em docs/.
Se uma decisão substituir uma decisão anterior, atualizar a documentação em vez de deixar informações contraditórias.

---

## 25. Objetivo final

O teste de aceitação de alto nível é:
"JARVIS, ligue meu computador e prepare meu ambiente Eryndor."

O sistema deverá eventualmente: detectar que o Core está desligado; enviar Wake-on-LAN; esperar o computador; verificar o Windows Agent; verificar o LLM; abrir Unity; abrir o projeto Eryndor; abrir VS Code; abrir terminal; abrir documentação; verificar o resultado; informar ao usuário.

Esse objetivo deve orientar as decisões arquiteturais, mas não deve ser implementado de uma única vez.
