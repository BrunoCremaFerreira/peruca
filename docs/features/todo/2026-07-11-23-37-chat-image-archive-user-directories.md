# Plano: Arquivamento em disco das imagens enviadas no chat (subpasta por usuário)

- **Status:** todo
- **Criado em:** 2026-07-11 23:37
- **Implementado em:** —
- **PR/commit:** —
- **Branch (a criar quando o plano for aprovado):** `feature/chat-image-archive`
- **Consultorias realizadas (obrigatórias):** `arquiteto`, `especialista-de-seguranca`,
  `programador-tester` (2026-07-11). `especialista-de-prompt` dispensado — a feature
  não toca prompts nem graphs.

---

## 1. Problema e objetivo

Hoje as imagens enviadas no `POST /llm/chat` só existem no `RedisImageStore`, que é
um **cache de re-visão** (TTL 24h, cap de 10 por usuário) — depois disso são
perdidas. Requisitos do usuário:

1. **Todas** as imagens enviadas nas conversas devem ser salvas de forma
   **durável** em um diretório **montado dentro do container**.
2. Subpastas nomeadas com o **id do usuário** (UUID interno).
3. Arquivos nomeados no padrão **`yyyy-mm-dd-hh-mm-ss-nomedoarquivo`** para
   facilitar manipulações (ordenável lexicograficamente).

## 2. Estado atual relevante (verificado no código)

- Imagens chegam em `ChatRequest.images` (`application/appservices/view_models.py:15`)
  como data URIs base64 **sem nome de arquivo** — o payload atual não carrega o
  nome original. O padrão de nome pedido exige estender o contrato da API
  (ver §3.3).
- `ImageValidator` (`domain/validations/image_validation.py`) valida fail-fast em
  `LlmAppService.chat()` (linhas ~99-106): mimes `image/jpeg|png|webp`, 5 MiB
  decodificados, máx. 4 por request. Valida apenas o **mime declarado** no data
  URI (regex) — não inspeciona bytes.
- A validação roda **antes** do lookup do usuário; o `user.id` interno (UUID) só
  está disponível depois (necessário para a subpasta).
- `ImageStore` (ABC em `domain/interfaces/data_repository.py:216`) →
  `RedisImageStore`: semântica de cache (`next_index`, `latest_id`, TTL, cap).
  Chamado por `_store_images()` **somente quando há `image_description`**.
- IoC: `get_image_store()` (`infra/ioc.py:334`) retorna `None` sem Redis —
  padrão de wiring opcional já estabelecido (idem Music Assistant).
- Docker: volume nomeado `peruca_data:/data` já montado; Dockerfile roda como
  `peruca` (uid 1000) e faz `chown` de `/data`.

## 3. Desenho da solução

### 3.1 Porta de domínio — nova ABC `ImageArchive`

Em `domain/interfaces/data_repository.py`, ao lado de `ImageStore` (não criar
arquivo novo para 1 ABC; o arquivo já agrupa contratos de dados):

```python
class ImageArchive(ABC):
    @abstractmethod
    def archive(
        self, user_id: str, data_uri: str, filename: Optional[str] = None
    ) -> Optional[str]:
        """Persist an inbound chat image durably. Returns the relative path
        written, or None when nothing was archived. Never raises."""
```

- **ABC separada, não extensão de `ImageStore`** (arquiteto): o contrato do
  store carrega semântica de cache (`next_index`/`latest_id`/TTL/cap) que não
  faz sentido para arquivamento write-once — estender violaria ISP/LSP.
- **Contrato "nunca lança"** (tester): entrada malformada ou falha de I/O →
  retorna `None` e loga `WARNING`. O try/except no `LlmAppService` vira a
  **segunda** barreira (defesa em profundidade), testada separadamente.
  *Divergência registrada*: o arquiteto preferia exceção em falha com o
  chamador engolindo; adotado o contrato never-raise porque o chamador já
  precisa da barreira de qualquer forma e a suíte fixa as duas camadas.

### 3.2 Adaptador de infra — `FileSystemImageArchive`

Novo provider: `infra/data/file_system/file_system_image_archive.py`
(convenção de diretório por provider, como `sqlite/` e `external/redis/`).

**Layout em disco:**

```
{CHAT_IMAGE_ARCHIVE_DIR}/
  {user_id}/                                  ← UUID interno, validado
    2026-07-11-23-40-05-recibo-oficina.jpg
    2026-07-11-23-41-12-image.png             ← fallback sem nome original
    2026-07-11-23-41-12-image-2.png           ← sufixo em colisão
```

**Regras de gravação (todas fixadas por teste):**

1. **`user_id`**: `uuid.UUID(user_id)` obrigatório; usar `str(uuid_obj)`
   normalizado como nome da pasta. Inválido/vazio → `None`, nada criado.
2. **Timestamp**: `yyyy-mm-dd-hh-mm-ss` (zero-padded), **hora local do
   servidor** — coerente com os nomes de planos do projeto e com o objetivo de
   manipulação manual pelo operador. (Se o plano de timezone do usuário em
   `todo/` for implementado antes, reavaliar; registrar a escolha no código.)
3. **`nomedoarquivo`**: nome original vindo da API (§3.3), sanitizado:
   `os.path.basename`, extensão original descartada, normalizado para
   minúsculas, espaços → `-`, whitelist `[a-z0-9_-]` (demais caracteres
   removidos), cap de 60 chars. Vazio após sanitizar ou ausente → fallback
   literal `image`.
4. **Extensão**: **mapa fechado** `{"image/jpeg": "jpg", "image/png": "png",
   "image/webp": "webp"}` — nunca derivar por manipulação de string do mime
   (o regex do validator aceita `[\w.+-]+`, que vazaria caracteres para o
   path). Mime fora do mapa → `None` (defesa em profundidade; o validator já
   filtra upstream, mas o adaptador não confia nisso).
5. **Magic bytes** conferidos contra o mime declarado antes de gravar:
   JPEG `FF D8 FF`, PNG `89 50 4E 47 0D 0A 1A 0A`, WebP `RIFF....WEBP`
   (offsets 0-3 e 8-11). Mismatch → `None` + `WARNING` (sem o payload no log).
   Elimina payload arbitrário estacionado com extensão de imagem.
6. **Colisão de nome** (mesmo segundo + mesmo nome): loop bounded acrescentando
   `-2`, `-3`, … antes da extensão; exaurido (limite 100) → `None` + log.
7. **Escrita atômica e permissões**: diretórios `mkdir(mode=0o700,
   parents=True, exist_ok=True)` (criação lazy no primeiro `archive()`, nunca
   na factory); arquivo escrito via `os.open(tmp, O_WRONLY|O_CREAT|O_EXCL,
   0o600)` + `os.replace()` para o nome final — nunca imagem truncada visível,
   sem overwrite/symlink-following. Não mexer no umask global do processo.
8. **Contenção de disco** (especialista-de-seguranca — P1; a mesma API key é
   compartilhada pelos clientes da casa, um cliente bugado em loop encheria o
   volume que também abriga o SQLite):
   - `chat_image_archive_max_bytes_per_user` (default 1 GiB): excedeu →
     **rotação FIFO** apagando os arquivos mais antigos do usuário (coerente
     com o precedente `max_per_user=10` do store Redis).
   - `chat_image_archive_min_free_bytes` (default 500 MiB): espaço livre do
     volume abaixo disso (`shutil.disk_usage`) → **pula** o arquivamento com
     `WARNING`. Protege o co-inquilino do volume (`peruca.db`).
9. **Higiene de log**: nunca logar data URI/bytes — apenas path relativo,
   tamanho e mime (invariante já existente no projeto).

### 3.3 Contrato da API — nome original do arquivo

O payload atual não tem nome de arquivo, então o padrão
`yyyy-mm-dd-hh-mm-ss-nomedoarquivo` precisa de um campo novo,
**retrocompatível** (default vazio, nenhum call site quebra):

```python
@dataclass
class ChatRequest:
    ...
    images: list[str] = field(default_factory=list)
    # Optional original filenames, positionally matched with `images`.
    image_filenames: list[str] = field(default_factory=list)
```

- Casamento **posicional** com `images`; ausente/curta → fallback `image` para
  as posições sem nome; entradas excedentes são ignoradas.
- Sanitização acontece no adaptador (§3.2 item 3) — o app service repassa cru.

### 3.4 Orquestração — `LlmAppService`

- Novo parâmetro opcional do construtor: `image_archive=None` (padrão
  `image_store` existente).
- Novo método privado `_archive_images(user, images, filenames)` espelhando o
  estilo de `_store_images`:
  - Guard clause: `image_archive is None or not images` → no-op.
  - **Posição do hook**: imediatamente **após** o `user` ser resolvido e
    validado não-nulo (a subpasta exige `user.id` interno), **antes** de montar
    o `GraphInvokeRequest`. *Não* é "logo após a validação" — a validação roda
    antes do lookup do usuário.
  - Arquiva **todas** as imagens validadas, **incondicionalmente** — diferente
    de `_store_images`, que exige `image_description`. Não fundir os dois
    (gatilhos, destinos e momentos diferentes — SRP).
  - **try/except por imagem** (não em volta do loop): falha em uma não impede
    as demais nem o chat; loga erro sem base64.
- **Síncrono inline, sem BackgroundTask** (arquiteto): pior caso ~20 MiB de
  decode+write custa dezenas de ms contra um pipeline de segundos de LLM;
  BackgroundTask vazaria orquestração para a rota e perderia a imagem se o
  processo caísse entre resposta e execução — trade-off errado para requisito
  de durabilidade. Encapsulado no método privado, dá para trocar por
  `asyncio.to_thread` depois sem tocar em mais nada (refinamento opcional).

### 3.5 IoC e Settings

- `infra/settings.py` (junto do bloco `chat_image_*` existente, linhas ~138-152):
  ```
  chat_image_archive_dir: str = ""                          # vazio = desabilitado
  chat_image_archive_max_bytes_per_user: int = 1_073_741_824  # 1 GiB, rotação FIFO
  chat_image_archive_min_free_bytes: int = 524_288_000        # 500 MiB, pula + warn
  ```
- `infra/ioc.py`: factory `get_image_archive() -> Optional[ImageArchive]` —
  retorna `None` quando `chat_image_archive_dir` é vazio/whitespace
  (`is_null_or_whitespace`), espelhando `get_image_store()`. Injetada em
  `get_llm_app_service` (mantendo o caveat de `Settings()` por factory).
- Factory **não** cria diretório (criação lazy no primeiro `archive()`).

### 3.6 Docker

- `docker-compose.yml`: adicionar ao `environment` do serviço `peruca`:
  `CHAT_IMAGE_ARCHIVE_DIR: "/data/images"` — **reutiliza** o volume
  `peruca_data:/data` existente (já com chown para uid 1000, mesma unidade de
  backup, zero mudança no Dockerfile). Operador que quiser navegar as imagens
  pelo host sobrescreve com bind mount no `docker-compose.override.yml`
  (documentar; recomendar ownership `1000:1000`, jamais `chmod 777`).
- `.env.example` e CLAUDE.md: documentar as novas envs.

## 4. Segurança e privacidade (resumo da auditoria)

| Prioridade | Item | Onde no plano |
|---|---|---|
| P1 | `uuid.UUID()` no user_id + mapa fechado mime→ext | §3.2 itens 1 e 4 |
| P1 | Magic bytes vs mime declarado | §3.2 item 5 |
| P1 | `O_EXCL` + `0o600`/`0o700` + escrita atômica | §3.2 item 7 |
| P1 | Cap de bytes por usuário (FIFO) + espaço livre mínimo | §3.2 item 8 |
| P1 | Logs sem base64 | §3.2 item 9 |
| P2 | Delete de usuário cascatear para `{dir}/{user_id}/` | Fora de escopo; nota §7 |
| P3 | Re-encode Pillow / criptografia por arquivo | Não fazer; condicional a servir imagens por HTTP (§7) |

- **Fail-open para o chat, fail-closed para a gravação**: erro de disco nunca
  derruba o `POST /llm/chat`; qualquer validação falhando → não grava nada.
- **Privacidade**: sem criptografia em repouso (o `peruca.db` ao lado guarda
  tudo em texto plano — cifrar só imagens seria teatral); documentar no README
  o que é armazenado, onde, e que a proteção é a do disco do host. Apagar
  `{dir}/{user_id}/` é a operação de esquecimento manual por ora.
- **Regra de ouro**: nada deve servir esse diretório estaticamente nem
  executar/interpretar seu conteúdo. Se um dia essas imagens forem servidas
  por HTTP: re-encode Pillow + `Content-Disposition: attachment` +
  `X-Content-Type-Options: nosniff` viram obrigatórios.

## 5. Plano de testes (TDD — escrever ANTES da implementação)

Especificação completa do `programador-tester` (~36 testes + os de filename),
convenções do projeto (unittest.mock, `_make_*`/`_sample_*`, classes
`TestXxxYyy`, `tmp_path` para filesystem — sem mock de FS exceto para simular
falha de disco). Nenhum teste de integração é necessário (sem dependência
externa).

### 5.1 `tests/unit_tests/test_file_system_image_archive.py`

- **Contract**: `FileSystemImageArchive` é subclasse de `ImageArchive`; a ABC
  não instancia (`TypeError`).
- **Happy path**: grava bytes decodificados (não o data URI cru); retorna path
  existente sob `{root}/{user_id}/`; cria subpasta do usuário e árvore de
  parents; nome casa com `^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-[a-z0-9_-]+\.(jpg|png|webp)$`
  (com `patch` de `datetime` para nome exato); dois usuários → subpastas
  isoladas.
- **Nome do arquivo**: nome original sanitizado (`"Recibo Oficina.JPEG"` →
  `...-recibo-oficina.jpg`); sem nome → fallback `image`; nome que sanitiza
  para vazio → fallback; cap 60 chars; **colisão** (mesmo segundo, mesmo nome,
  via `patch` de datetime) → sufixo `-2`; extensão vem sempre do mime, nunca
  do nome original.
- **Extensão/mime** (parametrizado): png/jpeg/webp → `.png`/`.jpg`/`.webp`;
  mime desconhecido (`application/pdf`) → `None`, nada gravado.
- **Magic bytes**: payload PNG válido com mime `image/jpeg` declarado →
  `None` + `WARNING` sem base64; payload com header correto grava.
- **Entrada malformada** (nunca lança, nada no disco, nem subpasta criada):
  sem prefixo `data:`; string vazia; `None`; sem `;base64`; base64 inválido
  (`binascii.Error` engolido).
- **user_id**: não-UUID (`"../evil"`, `""`, `"a/b"`) → `None`, nenhum arquivo
  fora de `tmp_path` (assert via `os.path.realpath`).
- **Falhas de disco**: raiz sem permissão de escrita (`chmod 0o500`, com
  `skipif(euid == 0)`) → `None` sem exceção; `OSError("disk full")` via patch →
  `None` + `WARNING` via `caplog` **sem** conter o payload; exceção nunca
  propaga.
- **Contenção**: cap por usuário excedido → FIFO apaga o(s) mais antigo(s) e
  grava o novo; `shutil.disk_usage` (mockado) abaixo do mínimo → pula + warn.

### 5.2 `tests/unit_tests/test_llm_app_service_image_archive.py`

Reutiliza `_sample_user()`/`_make_service()` de `test_llm_app_service_images.py`
(estendido com `image_archive` mock). Sem filesystem real.

- **Arquiva imagens validadas**: 1 imagem → `archive.assert_called_once_with(
  user.id, uri, filename)` com o **id interno** (não `external_user_id`);
  3 imagens → 3 chamadas em ordem; `image_filenames` posicional repassado;
  ausente → `None`/fallback repassado; sem imagens → não chamado.
- **Só depois da validação**: imagem inválida → `ValidationError` sobe **e**
  `archive.assert_not_called()`; lote misto válido+inválido → zero chamadas.
- **Opcional**: `image_archive=None` (default) → chat normal com imagens;
  construtor sem o kwarg → atributo `None` (retrocompatibilidade).
- **Falha nunca quebra o chat**: `side_effect=OSError` → `chat()` retorna
  output normal; `main_graph.invoke` ainda chamado; falha logada; log sem
  base64; `side_effect=[OSError, None]` com 2 imagens → `call_count == 2`
  (try/except **por imagem**); `return_value=None` não é erro.

### 5.3 `tests/unit_tests/test_ioc_image_archive.py`

Molde de `test_ioc_image_store.py` (`patch.dict(os.environ)`).

- Dir configurado → instância de `FileSystemImageArchive` com root da env;
  vazio → `None`; whitespace → `None`; factory **não** cria o diretório.
- `Settings`: default `""` (opt-in — deploys existentes não mudam); lê a env.

### 5.4 `tests/unit_tests/test_chat_view_models_images.py` (estender)

- `ChatRequest.image_filenames` default `[]`; chamadas posicionais existentes
  continuam válidas.

## 6. Fases de implementação (TDD estrito em cada uma)

- **Fase A — Porta + adaptador**: RED (5.1) → ABC `ImageArchive` +
  `FileSystemImageArchive` completo (naming, sanitização, magic bytes,
  permissões, atomicidade, FIFO, free-disk) → GREEN → refactor.
- **Fase B — Wiring**: RED (5.2, 5.3, 5.4) → `ChatRequest.image_filenames`,
  `_archive_images` no `LlmAppService`, settings, factory na IoC → GREEN.
- **Fase C — Deploy e docs**: `docker-compose.yml` (env `/data/images`),
  `.env.example`, CLAUDE.md (envs novas + seção curta da feature), nota de
  privacidade no README. Suíte completa verde (`python -m pytest tests/ -v`).

Sem commit automático — commits somente quando o usuário pedir.

## 7. Fora de escopo / evoluções futuras registradas

1. **Retenção/TTL** (`CHAT_IMAGE_ARCHIVE_TTL_DAYS`): retenção indefinida é o
   default consciente aqui (requisito é durabilidade); anotar como evolução
   (limpeza lazy por usuário na escrita seria barata). YAGNI por ora.
2. **Endpoint de leitura/galeria**: o path retornado não é consumido além de
   log — correto; não inventar API de download sem requisito. Se vier, aplicar
   as mitigações do §4 (P3).
3. **Delete de usuário** cascatear para o diretório de imagens (P2).
4. **`asyncio.to_thread`** no write se profiling apontar bloqueio relevante do
   event loop.

## 8. Alternativas descartadas

- **Estender `ImageStore`** — violaria ISP/LSP (métodos de cache sem sentido
  no arquivo durável).
- **BackgroundTask do FastAPI** — ganho de latência <1%, vaza orquestração
  para a rota, perde a imagem em crash pós-resposta.
- **Bind mount novo como default** — exigiria gestão de permissão no host;
  o volume `/data` existente já resolve (override para quem quiser).
- **`images` como lista de objetos `{data, filename}`** — quebraria o contrato
  atual; campo paralelo `image_filenames` é retrocompatível.
- **Re-encode com Pillow / criptografia por arquivo** — desproporcional para
  self-hosted com banco em texto plano ao lado; condicionado a servir imagens
  por HTTP.
