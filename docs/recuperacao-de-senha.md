# Recuperação da senha do administrador do VOXEL Router

Há dois caminhos, ambos auditados em `audit_logs`:

| Caminho | Quem usa | Requisito | Ação auditada |
|---|---|---|---|
| **Esqueci a senha** (tela de login) | operador da clínica + suporte VOXEL | chave pública da VOXEL no build | `PASSWORD_RECOVERY_REQUEST`, `RESET_PASSWORD_RECOVERY` |
| `VOXELResetAdmin.exe` | administrador do Windows na máquina | acesso local de administrador | `RESET_PASSWORD_LOCAL` |

O usuário padrão criado na primeira configuração é `voxeladmin`.

## Como funciona o "Esqueci a senha"

1. Na tela de login: **Esqueci a senha → GERAR PEDIDO**. O Router cria um código
   `VXRR1.<router_id>.<usuário>.<pedido>.<expiração>` válido por 24 h (no máximo 3 pedidos abertos).
2. **ENVIAR E-MAIL PARA A VOXEL** abre o programa de e-mail com o pedido para
   **admin@voxelpacs.com.br** (ou **COPIAR PEDIDO** e enviar por outro meio). O pedido não contém
   senha, chave, nome de paciente nem UID.
3. O suporte VOXEL **confirma a identidade** de quem pediu (ligação para o contato cadastrado da
   clínica) e assina o pedido (abaixo). Responde com o código `VXRS1.…`.
4. Na mesma tela: colar o código de resposta, definir a nova senha → **REDEFINIR SENHA**. A troca é
   exigida no próximo login; sessões antigas são encerradas e o bloqueio por tentativas é limpo.

Garantias: a resposta só vale para aquele Router, aquele usuário e aquele pedido, uma única vez e até
expirar. O equipamento guarda apenas a chave **pública** (`config/recovery_public_keys.json`); quem
tiver acesso à máquina não consegue gerar respostas. Respostas inválidas são limitadas a 5 por hora.
A interface só abre em `127.0.0.1`, então o pedido e a resposta precisam ser feitos na própria máquina.

Enquanto `config/recovery_public_keys.json` não tiver chave, a tela informa que a recuperação por
e-mail não está configurada e indica o `VOXELResetAdmin.exe`.

## Suporte VOXEL — configurar uma vez

Numa máquina da VOXEL (não no cliente), com o ambiente de desenvolvimento do Router:

```powershell
.venv\Scripts\python scripts\voxel_recovery_tool.py gerar-chave --saida D:\cofre\voxel-router-recovery.pem
```

- A chave privada sai **cifrada por senha** (mínimo 16 caracteres). Guardar em cofre com backup
  offline. Nunca enviar, nunca colocar em repositório (`*.pem` está no `.gitignore`).
- Copiar a linha JSON exibida para a lista `keys` de `config/recovery_public_keys.json`, fazer commit
  e gerar um novo instalador. Só Routers instalados com esse build aceitam a recuperação.
- Troca de chave: adicionar a nova entrada, manter a antiga até todos os clientes atualizarem e depois
  removê-la.

## Suporte VOXEL — atender um pedido

```powershell
.venv\Scripts\python scripts\voxel_recovery_tool.py assinar --chave D:\cofre\voxel-router-recovery.pem --pedido "VXRR1.…"
```

A ferramenta mostra Router ID, usuário e validade, pede a confirmação `SIM` (identidade conferida) e a
senha da chave, e imprime o código `VXRS1.…` para responder ao e-mail.

## Pelo Windows (VOXELResetAdmin)

PowerShell **como Administrador** na máquina do Router:

```powershell
& "C:\Program Files\VOXEL\Router\VOXELResetAdmin.exe" --list
& "C:\Program Files\VOXEL\Router\VOXELResetAdmin.exe" --username voxeladmin
```
