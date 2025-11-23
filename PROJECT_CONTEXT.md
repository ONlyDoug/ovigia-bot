# **O Vigia Bot \- Documentação do Sistema**

## **1\. Visão Geral**

O "O Vigia Bot" é um bot de Discord desenvolvido em Python para gerir o recrutamento e autenticação de jogadores de Albion Online.  
O sistema opera em dois modos distintos: "Modo Guilda" (focado em requisitos de fama) e "Modo Aliança" (focado na pertença à aliança).

## **2\. Stack Tecnológica (Obrigatória)**

* **Linguagem:** Python 3.11+  
* **Framework:** discord.py (com app\_commands para Slash Commands)  
* **Base de Dados:** PostgreSQL (via Supabase)  
* **Driver DB:** asyncpg (obrigatório para performance)  
* **Cliente HTTP:** aiohttp (para API do Albion)

## **3\. Regras Críticas de Arquitetura (NÃO QUEBRAR)**

1. **Supabase Pooler:** A conexão com a base de dados usa o "Transaction Pooler" do Supabase (porta 6543).  
   * **CRÍTICO:** Ao inicializar o asyncpg.create\_pool, o parâmetro statement\_cache\_size=0 DEVE ser definido. Caso contrário, o bot falha com DuplicatePreparedStatementError.  
2. **Parse da URL da DB:** Não usar urllib ou asyncpg para fazer parse da DATABASE\_URL automaticamente, pois falham na validação do hostname do Supabase. O parse deve ser feito manualmente via regex ou string split.  
3. **Sincronização de Comandos:** O bot usa um comando de prefixo \!sync (restrito a admins) para sincronizar a árvore de comandos (self.tree.sync) por servidor, evitando *rate limits* globais.  
4. **Estrutura de Cogs:** O código é modular. bot.py carrega:  
   * cogs.admin\_cog: Setup da DB, configuração de canais/cargos.  
   * cogs.recrutamento\_cog: Comando /registrar e lógica de cartões de aprovação.  
   * cogs.suporte\_cog: Comandos de gestão de fila (/suporte).  
   * cogs.sync\_cog: Loop de verificação/expulsão automática.  
   * cogs.alianca\_cog: Comando /aplicar\_alianca.

## **4\. Lógica de Negócio**

### **A. Modo Guilda**

* Verifica requisitos de Fama (PvE Total e PvP).  
* Se falhar nos requisitos \-\> Envia para aprovação manual com aviso (Log Laranja).  
* Se passar \-\> Envia para aprovação manual normal (Log Azul).  
* **Exceção:** Membros antigos (já na guilda) ignoram o filtro de fama.

### **B. Modo Aliança**

* Ignora requisitos de Fama.  
* Comando específico: /aplicar\_alianca.  
* Verifica se a tag da guilda do jogador corresponde à aliança configurada.  
* Atribui cargo de Aliado ou Membro (se for da guilda líder).

## **5\. Base de Dados (Schema)**

O Cog admin\_cog.py é responsável por criar as tabelas server\_config, server\_config\_permissoes, guild\_members e recruitment\_log usando tipos TIMESTAMPTZ corretos.