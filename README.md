# 🎙️ TikVoice

**TikVoice** é um bot de Text-to-Speech (TTS) para chats de lives do TikTok, com
interface gráfica moderna feita em CustomTkinter. Ele escuta os comentários da
sua live em tempo real e os lê em voz alta usando vozes neurais da Microsoft
(Edge TTS), tudo isso sem travar a interface.

![Versão](https://img.shields.io/badge/vers%C3%A3o-1.2.0-2fa572)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Plataforma](https://img.shields.io/badge/plataforma-Windows-informational)

## ✨ Funcionalidades

- **Conexão em tempo real** com o chat da sua live via [TikTokLive](https://github.com/isaackogan/TikTokLive).
- **9 idiomas e ~30 vozes neurais** via [edge-tts](https://github.com/rany2/edge-tts),
  incluindo 16 vozes em português do Brasil (além de português de Portugal,
  inglês, espanhol, francês, italiano e japonês) — comentários, presentes e
  novos seguidores são falados no idioma escolhido.
- **Prévia de voz**: teste qualquer voz antes de usar, direto na janela de Configurações.
- **Leitura do nome de quem comentou** (ativável/desativável), com ou sem `@` na frente (configurável).
- **Anúncio de presentes e novos seguidores**, além dos comentários (configurável).
- **Filtro anti-flood**: ignora mensagens repetidas recentemente e limita o
  tamanho da fila de fala, para não ficar muito atrasado num chat muito ativo.
- **Reconexão automática**: se a conexão cair sozinha (sem você ter clicado em
  Parar), o app tenta reconectar até 5 vezes, com espera crescente entre as
  tentativas, antes de desistir.
- **Foto e nome de perfil de quem está ao vivo**, exibidos assim que a conexão é
  estabelecida.
- **Configurações salvas automaticamente** em `config.json` — usuário, voz,
  idioma, volume, tema e demais preferências continuam na próxima vez que abrir o app.
- **Janela de Configurações com OK / Cancelar**: mudanças (tema, voz, volume
  etc.) têm prévia ao vivo enquanto a janela está aberta, mas só ficam valendo
  se você clicar em OK — Cancelar (ou fechar a janela) descarta tudo.
- **Janela redimensionável** e **tema claro/escuro** alternável a qualquer momento.
- **Monitor de chat / logs** que pode ser mostrado ou ocultado.
- **Arquitetura assíncrona**: todo o trabalho pesado (conexão + geração de áudio
  + reprodução) roda em uma thread separada — a interface nunca trava.
- **Encerramento seguro**: conexões e arquivos temporários de áudio são
  limpos corretamente ao parar ou fechar o app.

## 📋 Requisitos

- Windows 10/11
- Python 3.10 ou superior
- Conexão com a internet (para o TikTokLive e o Edge TTS)

## 🚀 Instalação

```bash
git clone https://github.com/maattduartee/Tikvouce-TTS.git
cd Tikvouce-TTS
pip install -r requirements.txt
```

> Se você renomear o repositório no GitHub, lembre de atualizar essa URL aqui.

## ▶️ Como usar

```bash
python app_gui.py
```

1. Digite o nome de usuário do TikTok da live que você quer monitorar.
2. Clique em **⚙** para escolher tema, voz e volume (e testar a voz antes de começar).
3. Clique em **▶ Iniciar** para conectar. O status mudará para **● Conectado**
   assim que a conexão for estabelecida.
4. Os comentários do chat aparecerão no monitor de logs e serão lidos em voz alta.
5. Clique em **■ Parar** para encerrar a leitura a qualquer momento.

## 📦 Gerando um executável (.exe)

Se quiser rodar o TikVoice sem precisar instalar Python, gere um `.exe`
standalone (Windows apenas):

```bash
build_exe.bat
```

O script instala o [PyInstaller](https://pyinstaller.org/) automaticamente se
necessário e gera o executável em `dist\TikVoice.exe`. Esse arquivo pode ser
copiado para qualquer pasta e rodado sem depender de Python instalado.

## ⚠️ Avisos importantes

- Este projeto não é afiliado, endossado ou de qualquer forma associado
  oficialmente ao TikTok ou à Microsoft.
- O `edge-tts` utiliza uma API não oficial da Microsoft — o serviço pode
  mudar ou parar de funcionar sem aviso prévio.
- Se o usuário da live não estiver ao vivo no momento da conexão, ou se o
  servidor de assinatura da TikTokLive estiver limitando requisições, o
  monitor de logs mostrará o motivo específico da falha.
- A reconexão automática só é tentada quando a queda **não** foi solicitada
  por você (clicando em Parar) — ela não tenta reconectar indefinidamente
  contra um usuário offline ou nome de usuário incorreto.
- O arquivo `config.json` guarda suas preferências localmente — não é enviado
  a lugar nenhum. Ele é criado automaticamente na primeira vez que você muda
  alguma configuração ou clica em Iniciar.
- Use com responsabilidade e em conformidade com os Termos de Serviço do TikTok.

## 🛠️ Stack técnica

| Componente | Biblioteca |
|---|---|
| Interface gráfica | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) |
| Chat da live | [TikTokLive](https://github.com/isaackogan/TikTokLive) |
| Síntese de voz | [edge-tts](https://github.com/rany2/edge-tts) |
| Reprodução de áudio | [pygame](https://www.pygame.org/) |

## 📄 Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE) para mais detalhes.

## 📝 Changelog

Veja [CHANGELOG.md](CHANGELOG.md) para o histórico de versões.
