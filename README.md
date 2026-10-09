# Lumen — Controle de Gamma (Windows + AMD / Intel / NVIDIA)

Aplicativo Windows (x64) que modifica **de verdade** o gamma/brilho/contraste do
monitor, com comportamento equivalente ao ajuste de imagem do Painel NVIDIA /
AMD Adrenalin / Intel Graphics. Funciona com **qualquer GPU** — AMD, Intel,
NVIDIA, video integrado — e ate sem GPU dedicada (driver basico), pois usa
`SetDeviceGammaRamp` do Windows, que e vendor-agnostic.

## Decisao tecnica sobre NVAPI

Investigacao nas docs NVAPI R590 + NvAPIWrapper:

- **Nao existe funcao NVAPI para rampa de gamma de monitor.**
  `NvAPI_VIO_SetGamma` e de placas de captura VIO.
- O proprio Painel NVIDIA altera gamma via
  `GetDeviceGammaRamp` / `SetDeviceGammaRamp` do Windows.
- NVAPI moderna tem `NvAPI_Disp_ColorControl` (`NV_COLOR_DATA`) para formato de
  cor/BPC/HDR — nao substitui a rampa classica.

Arquitetura entregue:

```
UniversalGammaController (alias legado: NvidiaGammaController)
  -> WindowsGammaController -> DisplayManager
  -> ProfileManager -> HotkeyManager -> SettingsManager -> Tray/Autostart
```

- Deteccao GPU/driver (só informativa): WMI (todas: AMD/Intel/NVIDIA/Microsoft),
  `nvidia-smi` / NVML quando há NVIDIA, + presenca de `nvapi64.dll`.
  Ver `src/gpu_detector.py` (`src/nvidia_controller.py` mantido como compat).
- Aplicacao real: `SetDeviceGammaRamp` por monitor (`\\.\DISPLAYx`), mesma via
  dos paineis NVIDIA/AMD/Intel. Sem overlay, sem filtro, sem shader local.
  Funciona sem GPU dedicada.

## Requisitos

- Windows 10/11 x64, qualquer GPU: AMD, Intel, NVIDIA, video integrado
  ou driver basico da Microsoft (sem GPU dedicada também funciona).
- Python 3.11+ (dev) ou `.exe` standalone (distribuicao).
- `nvidia-ml-py` é **opcional** (só detalha deteccao em máquina NVIDIA).

## Uso (dev)

```bat
pip install -r requirements.txt
python main.py
python main.py --minimized
```

## Download

Pronto para Windows 10/11 x64, sem instalar Python:

**[Baixar Lumen v1.0.0](https://github.com/kamiKD/Lumen/releases/latest)**

O executavel nao e assinado digitalmente, entao o SmartScreen pode mostrar
"Windows protegeu seu PC" na primeira execucao: clique em **Mais
informacoes** → **Executar assim mesmo**. Para nao ver o aviso de novo,
clique com o botao direito no `Lumen.exe` → Propriedades → marque
**Desbloquear**.

## Build do .exe

Para compilar localmente:

```
python -m PyInstaller --noconfirm --clean Lumen.spec
```

Gera `dist\Lumen.exe` standalone (PyInstaller, sem exigir Python).
Para um build de desenvolvimento, acrescente `--windowed --name Lumen-dev`.

## Recursos

- Sliders gamma 0.10–5.00 (0.01), brilho/contraste 0–100%, aplicacao em tempo real,
  com previa da curva resultante.
- Tema claro/escuro (automatico segue o Windows) e posicao da janela lembrada.
- Toggle global (default `F8`; suporta `CTRL+F8`, `CTRL+ALT+G` etc.), via
  `RegisterHotKey` (eventos, sem polling, CPU ~0%).
- Perfis: criar/renomear/excluir/duplicar/aplicar (Default, Gaming, CS2...).
- Config em `%APPDATA%\Lumen\config.json`, logs em `...\logs\`.
- System tray com menu Gamma ON/OFF + perfis + toggle + sair.
- Iniciar com Windows (HKCU Run) + iniciar minimizado.
- Restaura rampa original ao desligar toggle/sair (opcao ligada por padrao) +
  `active.flag` contra crash + reaplicacao apos troca de resolucao/monitor.
- Multi-monitor (`CreateDC` por `\\.\DISPLAYx`), deteccao GPU/driver/resolucao/
  refresh/HDR (AMD/Intel/NVIDIA/integrado), tratamento de erros PT-BR,
  sem exigir admin, sem servico, sem tocar em DLL/driver de video.

## Estrutura

```
main.py  launcher
src/
  app.py  janela (header + abas) + tray
  theme.py  tokens de cor/espacamento + folha de estilo (claro/escuro)
  ui.py  widgets reutilizaveis (banner, chip, slider, curva, lista, captura)
  gamma_controller.py  IGammaController, Windows + Universal (AMD/Intel/NVIDIA)
  gpu_detector.py      deteccao generica GPU/driver (AMD/Intel/NVIDIA/integrado)
  nvidia_controller.py compat (delega p/ gpu_detector)
  display_manager.py   monitores/resolucao/refresh/HDR
  profile_manager.py   CRUD perfis
  hotkey_manager.py    RegisterHotKey global
  settings_manager.py  config.json + logs
  autostart.py  HKCU Run + active.flag
requirements.txt  Lumen.spec
config/default_config.json
```

## Interface

Segue o visual do Windows 11: barra lateral de navegacao a esquerda, com
pilula de selecao no item ativo, e cards de agrupamento na area de conteudo.

A janela e dividida em um cabecalho fixo e tres paginas.

**Cabecalho** — chip de estado (ON/OFF), botao principal de toggle, botao
Restaurar, seletor de monitor, chip de HDR e o botao **Diagnostico**.
Fica sempre visivel, inclusive ao trocar de pagina.

**Banner** — aparece abaixo do cabecalho para HDR ativo ou falha de gamma.
Mostra a causa provavel, esconde o detalhe tecnico em "Detalhes" e traz a
acao que resolve (abrir configuracoes de tela / guia). Nao bloqueia a janela
com modal.

**Navegacao** — barra lateral com Gamma, Perfis e Opcoes. O item ativo fica
com pilula de selecao, como no painel do Windows.

**Gamma** — os tres sliders (Gamma, Brilho, Contraste) com rotulos
alinhados em coluna e o valor numerico a direita, ao lado da **curva
resultante**: o grafico da LUT que sera aplicada, com a curva neutra
(gamma 1.0) tracejada como referencia. O texto abaixo dos sliders muda
conforme o estado do toggle, para ficar claro quando as mudancas entram
na tela.

**Perfis** — lista com o nome e os valores de cada perfil, o monitor
vinculado e um asterisco nos perfis com alteracoes nao salvas. Duplo clique
aplica; clique direito abre o menu de acoes. O botao Salvar fica
desabilitado quando nao ha nada a salvar. `Default` vem sempre primeiro.

**Opcoes** — tres cards (Atalho global, Inicializacao, Aparencia) com uma
linha por ajuste. O diagnostico abre pelo botao do cabecalho.

Referencias de comportamento:

- O toggle e a unica fonte de verdade do estado. Aplicacao, bandeja e atalho
  passam todos por `_set_gamma_state`, que no fim reescreve o botao e a
  config — inclusive quando a aplicacao falha, caso em que o estado volta
  para OFF em vez de a UI afirmar um "ON" que nao aconteceu.
- Tema Automatico segue o Windows (`colorScheme` do sistema).
- Posicao e tamanho da janela sao lembrados entre sessoes.
- Mensagens de sucesso (perfil salvo, atalho definido) aparecem numa barra
  transitoria no rodape, sem interromper com dialogo.

## Limitacoes conhecidas

- Com **HDR ligado** o Windows ignora `SetDeviceGammaRamp` (aviso exibido).
- Alguns overlays fullscreen exclusivos podem sobrescrever a rampa; o app
  reaplica ao detectar troca de tela.
- MCCS/DDC (brilho fisico do monitor via I2C) nao implementado — fora do escopo.
