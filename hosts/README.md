# Configurações de hosts

Cada arquivo mostra o mesmo servidor com a configuração nativa do host. Troque
`/CAMINHO/ABSOLUTO/PROJETO` pelo caminho real do repositório antes de usar.

| Arquivo | Host | Chave raiz |
|---|---|---|
| `claude_desktop_config.example.json` | Claude Desktop | `mcpServers` |
| `cursor.mcp.example.json` | Cursor | `mcpServers` |
| `opencode.example.json` | OpenCode | `mcp.servers` |
| `../.vscode/mcp.json` | VS Code | `servers` |

## Regras que valem para todos

1. **Caminho absoluto** no comando e no banco. O host não roda no seu diretório.
2. **Reinicie o host** depois de editar a configuração.
3. **Nada de stdout**: em stdio, stdout é o protocolo. Use `logging` (stderr).
4. **Ambiente explícito**: o subprocesso não herda seu shell; passe `env` quando
   precisar de `AGRO_DB_PATH` ou de uma chave.
5. **Confirme o comando no terminal** antes de culpar o host:

   ```bash
   uv run --frozen --directory /caminho/do/projeto \
     python -m minicurso_einfo_mcphandson serve
   ```

   O comando deve ficar parado sem imprimir nada (esperando o host falar).

## OpenCode neste repositório

O `opencode.json` da raiz já está funcional. Confirme com:

```bash
opencode mcp list
# agro  connected
```

Se o host reclamar de `uv` fora do `PATH`, troque `"uv"` pelo caminho absoluto
retornado por `which uv`.

## VS Code

O `.vscode/mcp.json` usa `${workspaceFolder}`, então funciona ao abrir a pasta
do projeto. Requer VS Code 1.99+, GitHub Copilot autenticado e o chat em modo
**Agent**. Use **MCP: List Servers** na Command Palette.
