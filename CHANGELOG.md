# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto segue o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [1.0.0] - 2026-09-26

### Adicionado
- Interface gráfica completa em CustomTkinter (tema escuro/claro).
- Conexão em tempo real com o chat de lives do TikTok via TikTokLive.
- Leitura de comentários com vozes neurais em português (Edge TTS): Antônio,
  Francisca e Thalita.
- Janela de Configurações separada: tema, seleção de voz, prévia de voz e volume.
- Botão único de Iniciar/Parar e indicador de status de conexão.
- Monitor de chat / logs com opção de mostrar ou ocultar.
- Arquitetura assíncrona em thread separada, sem travar a interface.
- Tratamento de erros detalhado (usuário offline, não encontrado, rate limit
  do servidor de assinatura, erros de rede) encaminhado para o monitor de logs.
- Limpeza segura de arquivos de áudio temporários e encerramento limpo da
  conexão ao parar o bot ou fechar a janela.
