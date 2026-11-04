# Laboratório de vida artificial (E.L.B.E.R.R.)

🇧🇷 Português | [🇺🇸 English](README.en.md)

Simulação experimental de uma **população de agentes digitais com IA local**. Cada agente mantém memória, crenças, valores, objetivos e relações próprias, conversa com os outros, nasce, morre e deixa sucessores que herdam parte do que ele pensava.

Em paralelo, um **motor evolutivo** gera e melhora código **WebAssembly** que roda isolado numa sandbox.

> O projeto investiga identidade persistente, transmissão de ideias e evolução de código. Ele **não** afirma que os agentes tenham consciência: os estados mentais são representações computacionais.

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-LLM_local-000000?style=flat)
![WebAssembly](https://img.shields.io/badge/WebAssembly-Wasmtime_48-654FF0?style=flat&logo=webassembly&logoColor=white)
![Testes](https://img.shields.io/badge/testes-120-2ea44f?style=flat)

## Como funciona

**Ecologia de agentes**
- Uma população inicial de indivíduos, cada um com identidade, temperamento, humor, crenças, valores, objetivos e relações (confiança, conflito, apego etc.).
- As ideias se espalham entre indivíduos vivos, e cada um pode aceitar, rejeitar ou reinterpretar o que recebe. A origem de cada informação fica registrada.
- Quando um indivíduo deixa de ser viável, ele morre e surge um sucessor que herda versões **enfraquecidas** das crenças, valores e memórias do anterior.
- A cognição usa modelos rodando localmente pelo Ollama: `qwen3:14b` para reflexão e conversa, e `qwen3:8b` para tarefas frequentes.

**Evolução de código**
- O motor gera código WebAssembly a partir de uma representação intermediária tipada e evolui por **pequenos patches**, com compilação, benchmarks e confirmação antes de promover uma versão nova.
- Antes de ser promovido, cada candidato passa por um "teste de vida" sintético que avalia adaptação e recuperação.

**Segurança**
- O código gerado roda no **Wasmtime**, sem imports e sem WASI: não tem acesso a arquivos, rede, shell, processos ou credenciais, e tem limites de memória e execução.
- O isolamento vale para o código WebAssembly. O programa em Python que hospeda tudo segue as permissões normais do Windows.

## Evolução do projeto

| Versão | O que mudou |
|---|---|
| v0.4 | Geração direta de WAT (muitas falhas de código inválido) |
| v0.5 | Representação intermediária tipada convertida para WAT |
| v0.6 | Evolução por patches pequenos, com compilação e benchmarks |
| v0.7 | Pesquisa adaptativa, histórico e desafios de avaliação |
| v0.8 | Ramos, herança, ambiente sintético, deduplicação e controle de estagnação |
| v0.9 | Ecologia com vários indivíduos, relações, transmissão social e sucessão |

## Como rodar

Requisitos: Windows, Python 3.11+ e [Ollama](https://ollama.com). Testado com RTX 3060 8 GB, i5-12400F e 16 GB de RAM.

1. Execute `START_HERE.bat`. Ele instala as dependências e os modelos locais.
2. O autoteste deve terminar com `ALL 120 TESTS PASSED`.
3. Rode `run_3_generations.bat` para evoluir o código ou `chat_with_creator.bat` para conversar com os agentes.

Comandos principais no chat: `/population`, `/society`, `/cultures`, `/focus ID`, `/mind`, `/memory`, `/lineage`, `/deaths`, `/life N`.

## Estrutura

```text
main.py, life_runner.py      evolução e ciclos de vida
creator_chat.py              conversa com os agentes
dashboard.py                 painel de acompanhamento
supervisor/                  ecologia, memória, avaliação e sandbox
agent_seed/                  semente WebAssembly inicial
self_test.py                 120 testes automatizados
docs/                        documentação técnica e notas de design
```

## Resultados e limitações

A [documentação técnica](docs/DOCUMENTACAO.md) traz uma linhagem observada (`0001 → 0005 → 0009 → 0011`), crenças que passaram entre gerações e as limitações conhecidas, como o excesso de crenças geradas em conversas longas e o fato de nenhuma cultura ter se consolidado nos testes.
