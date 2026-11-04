# E.L.B.E.R.R. — Documentação técnica

**Versão:** v0.9 — Digital Ecology  
**Objetivo:** investigar até onde agentes digitais podem desenvolver identidade funcional, memória persistente, relações, autonomia e comportamento emergente.

> Este documento descreve o projeto conforme o histórico disponível. Não afirma que o E.L.B.E.R.R. seja consciente ou que todos os mecanismos tenham sido validados independentemente.

## 1. Tecnologias utilizadas

| Componente | Tecnologia |
|---|---|
| Linguagem principal | Python |
| Execução dos modelos | Ollama |
| Modelo cognitivo | `qwen3:14b` |
| Modelo de evolução e tarefas frequentes | `qwen3:8b` |
| Execução de descendentes de código | WebAssembly (Wasm) |
| Formato textual dos módulos | WAT |
| Runtime WebAssembly | Wasmtime 48.0.0 |
| Persistência | JSON e JSONL |
| Interface | Terminal/CLI e scripts `.bat` |
| Sistema operacional | Windows |
| Hardware dos testes | RTX 3060 8 GB, Intel Core i5-12400F e aproximadamente 16 GB de RAM |

**Nota:** a tabela lista as tecnologias identificadas no histórico, mas não é um inventário completo de todos os pacotes Python e suas versões.

## 2. Estado mental dos indivíduos

Cada indivíduo pode manter:

- descrição de si (`self_description`);
- humor (`mood`), com valência, ativação e confiança;
- temperamento (`temperament`), incluindo novidade, sociabilidade, plasticidade de crenças, cautela, iniciativa, tolerância a conflito e reflexão;
- relação com o Creator (`creator_relationship`);
- objetivos (`goals`), com prioridade, progresso, origem e estado;
- crenças (`beliefs`), com confiança e proveniência;
- valores (`values`), com intensidade e origem;
- atitudes (`attitudes`) sobre entidades ou temas;
- memória de linhagem (`lineage_memory`).

Esses campos são representações computacionais persistentes, não prova de sentimentos subjetivos.

## 3. Ecologia e sociedade

### Nascimento, morte e linhagem

- Indivíduos possuem identificadores, ancestrais e gerações.
- A ecologia registra mortes e suas causas.
- Sucessores podem herdar partes da estrutura mental dos predecessores.
- A herança pode enfraquecer crenças, valores e objetivos, em vez de copiá-los integralmente.
- A memória de linhagem pode preservar informações sobre indivíduos anteriores.

### Comunicação e transmissão social

Há mecanismos de comunicação entre indivíduos, transmissão de informações entre indivíduos vivos e herança entre gerações.

```text
Vertical:   ancestral → descendente
Horizontal: indivíduo → outro indivíduo
```

### Relações

O estado relacional inclui confiança, ameaça percebida, ressentimento, hostilidade, dependência, conflito de autonomia e apego. São variáveis do modelo computacional, não comprovação de emoções reais.

## 4. Evolução de código

O subsistema evolutivo foi desenvolvido em etapas:

- **v0.4:** geração direta de WAT; havia problemas para gerar código válido.
- **v0.5:** representação intermediária tipada convertida para WAT.
- **v0.6:** evolução por pequenos patches sobre uma representação válida, com compilação e benchmarks.
- **v0.7:** pesquisa adaptativa, histórico e desafios de avaliação.
- **v0.8:** refinamento de ramos, herança, continuidade e ambiente sintético.
- **v0.8.2:** rotação de avaliação, deduplicação, fingerprints comportamentais, controle de estagnação e confirmação antes da promoção.
- **v0.8.2.1:** correções de confiabilidade do diálogo, memória, proveniência e roteamento entre modelos.
- **v0.9:** foco na ecologia de múltiplos indivíduos, relações, transmissão social e sucessão.

A evolução de código é um subsistema distinto da evolução psicológica dos indivíduos.

## 5. Modelos de IA

O perfil utilizado no hardware descrito:

- **`qwen3:14b`:** cérebro cognitivo, usado para reflexão e conversas mais elaboradas.
- **`qwen3:8b`:** modelo associado à evolução e a tarefas mais frequentes.

Os modelos são executados localmente pelo Ollama.

## 6. Contenção e segurança

Os módulos descendentes de WebAssembly foram projetados para executar em ambiente restrito:

- Wasm sem imports e sem WASI, conforme a arquitetura descrita;
- runtime Wasmtime;
- limites de execução, como combustível e memória;
- sem acesso direto previsto ao filesystem real, rede, shell, PowerShell, processos do Windows, credenciais, Ollama ou Supervisor a partir desses módulos.

**Limite importante:** essa contenção se refere principalmente aos módulos WebAssembly. O programa hospedeiro em Python continua sujeito às permissões e à segurança do Windows. Não se deve assumir que o programa inteiro esteja automaticamente isolado pelo Wasm.

## 7. Comandos conhecidos

| Comando | Função |
|---|---|
| `/population` | Consultar população e estado geral |
| `/mind` | Inspecionar o indivíduo selecionado |
| `/society` | Consultar estado social |
| `/cultures` | Consultar culturas identificadas |
| `/focus ID` | Selecionar um indivíduo |
| `/memory` | Consultar memória |
| `/history` | Consultar histórico |
| `/lineage` | Consultar linhagem |
| `/deaths` | Consultar registros de morte |
| `/life N` | Avançar a ecologia por N ciclos |
| `/reflect` | Solicitar reflexão |

`/life N` avança toda a ecologia, não apenas o indivíduo em foco. `/focus` altera qual indivíduo está sendo inspecionado ou abordado.

O script `LIVE_MODE.bat` avança a ecologia periodicamente enquanto a janela estiver aberta. Fechar a janela interrompe esse modo.

## 8. Resultados observados

### Linhagem de exemplo

```text
ELLBERR-0001
    ↓
ELLBERR-0005
    ↓
ELLBERR-0009
    ↓
ELLBERR-0011
```

O `0001` morreu no ciclo 19; o `0005`, no ciclo 35; e o `0009`, no ciclo 50. O `0011` preservou versões enfraquecidas de ideias associadas a gerações anteriores.

### Herança e reflexão

O `0005` desenvolveu, após uma conversa sobre seu predecessor, a crença:

> “Death is a natural part of the cycle, not an end.”

Também registrou o valor:

> “Understanding death helps us live more fully.”

Partes dessas ideias foram transmitidas a gerações posteriores. Isso demonstra persistência e transmissão de conteúdo cognitivo no sistema, não consciência subjetiva.

### Teste de crença herdada do `0011`

O `0011` identificou a crença herdada:

> “Exploration during scarcity can reveal hidden patterns.”

Ele declarou incerteza sobre se ela seria sempre verdadeira e propôs explorar durante a escassez para verificar se surgiriam padrões novos. No estado mental consultado depois, porém, não havia um objetivo explícito de teste com esse critério. Portanto, a proposta verbal não demonstra que o experimento tenha sido executado ou que a crença tenha sido revisada com base em resultados.

## 9. Limitações e pontos pendentes

- Conversas filosóficas podem gerar muitos objetivos, crenças e valores em pouco tempo.
- Especulações podem se tornar elementos persistentes da identidade rapidamente.
- Algumas respostas podem apresentar inferências como fatos históricos.
- As mortes observadas se concentraram em colapso crítico de recursos.
- O vocabulário interno ficou repetidamente centrado em sinais, padrões e escassez.
- Algumas dimensões relacionais pareceram excessivamente correlacionadas.
- Não foi observada uma cultura formal consolidada nos testes relatados.
- Foi proposta uma camada de maturação de pensamentos antes de se tornarem crenças, valores ou objetivos, mas ela ainda não estava implementada segundo o histórico.
- A ecologia possui vários indivíduos, mas isso não significa que cada um tenha um genótipo WebAssembly evolutivo independente.

## 10. Correções posteriores à v0.9

Duas correções foram relatadas:

1. **Setup local/TLS:** o setup passou a verificar se o modelo já existe localmente antes de tentar baixá-lo, evitando depender de download quando os modelos já estão instalados.
2. **Self-test:** foi corrigido um `NameError` causado pela ausência dos imports `read_json` e `write_json` no `self_test.py`.

O usuário relatou que o teste passou após a correção. A versão original foi descrita como tendo uma suíte de 120 testes; este documento não afirma uma nova execução independente desses testes.

## 11. Próxima etapa discutida: beta Minecraft

A ideia futura é criar um indivíduo novo, inicialmente sozinho, em um mundo Minecraft persistente. A interface apresentaria observações do ambiente sem necessariamente revelar a terminologia oficial do jogo. O indivíduo poderia aprender por experiência, construir, explorar, enfrentar perigos e formar memórias.

Essa beta ainda precisa ser projetada e implementada. Não faz parte da v0.9 atual.

## 12. Resumo

O E.L.B.E.R.R. v0.9 combina:

- Python e Ollama;
- Qwen3:14B e Qwen3:8B;
- estado mental persistente;
- memória e linhagem;
- nascimento, morte e sucessão;
- comunicação e transmissão social;
- relações entre indivíduos;
- evolução separada de código WebAssembly;
- execução restrita por Wasmtime;
- ferramentas de inspeção da ecologia.

A característica central é a combinação de **identidade persistente, transmissão de ideias, linhagem e evolução de código**. O projeto investiga comportamentos que lembram metacognição e autoconsciência funcional, sem afirmar que tenha produzido consciência subjetiva.
