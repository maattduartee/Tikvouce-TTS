# 🎙️ TikVoice

**TikVoice** é um bot de Text-to-Speech (TTS) para chats de lives do TikTok, com
interface gráfica moderna feita em CustomTkinter. Ele escuta os comentários da
sua live em tempo real e os lê em voz alta usando vozes neurais da Microsoft
(Edge TTS), tudo isso sem travar a interface.

![Versão](https://img.shields.io/badge/vers%C3%A3o-1.0.0-2fa572)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Plataforma](https://img.shields.io/badge/plataforma-Windows-informational)

## ✨ Funcionalidades

- **Conexão em tempo real** com o chat da sua live via [TikTokLive](https://github.com/isaackogan/TikTokLive).
- **Vozes neurais em português (pt-BR)** via [edge-tts](https://github.com/rany2/edge-tts):
  Antônio, Francisca e Thalita.
- **Prévia de voz**: teste qualquer voz antes de usar, direto na janela de Configurações.
- **Tema claro/escuro** alternável a qualquer momento.
- **Controle de volume** dedicado.
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
git clone https://github.com/SEU_USUARIO/tikvoice.git
cd tikvoice
pip install -r requirements.txt
```

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

## ⚠️ Avisos importantes

- Este projeto não é afiliado, endossado ou de qualquer forma associado
  oficialmente ao TikTok ou à Microsoft.
- O `edge-tts` utiliza uma API não oficial da Microsoft — o serviço pode
  mudar ou parar de funcionar sem aviso prévio.
- Se o usuário da live não estiver ao vivo no momento da conexão, ou se o
  servidor de assinatura da TikTokLive estiver limitando requisições, o
  monitor de logs mostrará o motivo específico da falha.
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
