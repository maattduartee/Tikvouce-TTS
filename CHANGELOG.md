# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto segue o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [1.2.0] - 2026-09-27

### Adicionado
- Suporte a 9 idiomas e cerca de 30 vozes neurais (antes só português do
  Brasil): português (Brasil/Portugal), inglês (EUA/Reino Unido), espanhol
  (Espanha/México), francês, italiano e japonês. Comentários, presentes e
  novos seguidores são falados no idioma escolhido, não só a voz.
- Biblioteca de vozes pt-BR ampliada de 3 para 16 vozes (Antônio, Francisca,
  Thalita, Brenda, Donato, Elza, Fábio, Giovanna, Humberto, Júlio, Leila,
  Letícia, Manuela, Nicolau, Valério e Yara).
- Janela principal redimensionável (antes tinha tamanho fixo).
- Cartão de perfil com foto e nome de quem está ao vivo, carregados assim
  que a conexão é estabelecida.
- Janela de Configurações agora tem botões OK / Cancelar: mudanças têm
  prévia ao vivo, mas só são salvas se você confirmar com OK.
- Interruptor mestre para ativar/desativar totalmente a leitura do nome de
  quem comentou (antes só dava para escolher o formato "com @" ou "sem @",
  mas não desligar completamente).

### Corrigido
- Trocar entre tema escuro e claro fechava a própria janela de Configurações
  sozinha (bug de redesenho do CustomTkinter). O tema agora só é aplicado
  depois que a janela de Configurações é fechada.

### Alterado
- Layout da tela inicial reorganizado num cartão de perfil mais moderno.

## [1.1.0] - 2026-09-26

### Adicionado
- Reconexão automática após queda de conexão não solicitada, com até 5
  tentativas e espera crescente entre elas.
- Filtro anti-flood: ignora mensagens repetidas recentemente e limita o
  tamanho da fila de fala num chat muito ativo (configurável).
- Anúncio em voz de presentes recebidos e novos seguidores (configurável).
- Leitura do nome de quem comentou antes da mensagem, com opção de incluir
  ou não o símbolo "@" (ex.: "@fulano disse: ..." ou "fulano disse: ...").
- Configurações persistidas automaticamente em `config.json` (usuário, voz,
  volume, tema e demais preferências).
- Script `build_exe.bat` para gerar um executável standalone com PyInstaller.

### Corrigido
- O nome de quem comentou nunca era efetivamente lido em voz alta, mesmo
  aparecendo no monitor de logs — a leitura só falava o texto da mensagem.

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
