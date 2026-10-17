<div align="center">
  <img src="docs/images/bloodpsp.png" width="512" alt="Blood PSP">
</div>

# Blood PSP

[English](README.md) | [Português Brasileiro](README.pt-BR.md)

Blood para o PSP, baseado no [jfblood-vita](https://github.com/Rinnegatamante/jfblood-vita) e no [NBlood-Amiga](https://github.com/BSzili/NBlood-Amiga).

Ainda em desenvolvimento. Testado no PSP Slim e no PPSSPP.

<img src="docs/images/running-on-psp.png" width="512" alt="Blood rodando no PSP">

## Instalação

Baixe o [GUI para Windows](https://github.com/RainArcanjo/BloodPSP/releases/latest). Com ele você monta a pasta do jogo para o PSP e customiza controles, vídeo, áudio e o `nblood.cfg`.

Compatível com **Blood: Fresh Supply** e **One Unit Whole Blood**. Você precisa ter sua cópia do jogo.

1. Extraia o ZIP e abra `BloodPSPLauncher.exe`.
2. Selecione a pasta onde seu Blood está instalado. A EBOOT já vem junto; também dá para selecionar outra ou baixar do GitHub.
3. Selecione o cartão do PSP ou uma pasta de saída.
4. Clique em **BUILD PSP FOLDER**.
5. Copie a pasta `PSP` gerada para o cartão, caso tenha montado no PC.

Músicas OGG e user maps disponíveis são copiados automaticamente. Os arquivos originais do seu jogo ficam no lugar.

![GUI do BloodPSP — instalação](docs/images/launcher-setup.png)

### Instalação manual

Se preferir copiar os arquivos sem usar o programa, crie `PSP/GAME/BloodPSP/` no cartão do PSP. Coloque a `EBOOT.PBP` da release e o [nblood.cfg](nblood.cfg) nessa pasta, depois copie os seguintes arquivos da instalação do seu Blood para o mesmo lugar:

```text
PSP/GAME/BloodPSP/
├── EBOOT.PBP
├── nblood.cfg
├── BLOOD.INI
├── BLOOD.RFF
├── GUI.RFF
├── SOUNDS.RFF
├── SURFACE.DAT
├── TABLES.DAT
├── TILES000.ART
├── TILES001.ART
├── TILES002.ART
├── TILES003.ART
├── TILES004.ART
├── TILES005.ART
├── TILES006.ART
├── TILES007.ART
├── TILES008.ART
├── TILES009.ART
├── TILES010.ART
├── TILES011.ART
├── TILES012.ART
├── TILES013.ART
├── TILES014.ART
├── TILES015.ART
├── TILES016.ART
├── TILES017.ART
└── VOXEL.DAT
```

Os arquivos ficam direto ao lado da `EBOOT.PBP`, sem outra pasta do jogo dentro de `BloodPSP`. Mantenha os originais no PC.

Opcional: coloque as músicas de `blood02.ogg` até `blood09.ogg` em `PSP/GAME/BloodPSP/music/`, mantendo esses nomes. Os user maps ficam em `PSP/GAME/BloodPSP/usermaps/`.

## Controles

Na aba **Controls**, você pode mudar os botões e criar combinações. O **Map button** funciona com DualShock/DualSense ou pelos botões do PSP na tela. Segure os botões juntos e solte.

Use **Save preset** e **Load preset** para guardar seus controles. Com o jogo fechado, clique em **Apply controls** para salvar o CFG e depois abra o jogo.

![GUI do BloodPSP — controles](docs/images/launcher-controls.png)

## User maps

Coloque os arquivos `.MAP` em `PSP/GAME/BloodPSP/usermaps/`. No jogo, abra **NEW GAME > USER MAP**.

Tem suporte a músicas OGG, saves e resolução nativa de 480×272. Você pode usar 320×200 para ganhar desempenho. Multiplayer, vídeos Smacker e voxels ainda não são suportados.

## Compilar o projeto

### EBOOT

Instale o PSPDEV e o PSPSDK primeiro. Você também precisa de Git, Make e Bash. No Windows, use o terminal do MSYS2.

Clone o projeto junto com as bibliotecas:

```sh
git clone --recurse-submodules https://github.com/RainArcanjo/BloodPSP.git
cd BloodPSP
```

Configure o caminho e compile. Troque `/c/pspdev` pela pasta do seu PSPDEV:

```sh
export PSPDEV=/c/pspdev
export PSPSDK="$PSPDEV/psp/sdk"
export PATH="$PSPDEV/bin:$PSPSDK/bin:$PATH"
make -f Makefile.psp PSP_EXTRA_DEFINES=-DPSP_STABLE_PERFORMANCE_BUILD blood-eboot-release
```

O resultado é `EBOOT.PBP`, com uma cópia em `EBOOT-release.PBP`. Selecione essa EBOOT no GUI para montar a pasta do PSP. Não precisa dos arquivos do jogo para compilar.

Se já clonou sem as bibliotecas, rode `git submodule update --init --recursive` antes de compilar.

### GUI para Windows

Com o Python instalado, execute `launcher/Build.cmd`. Para incluir a EBOOT que você compilou, use o PowerShell na pasta do repositório:

```powershell
.\launcher\Build.cmd -EbootPath C:\build\EBOOT.PBP
```

Troque esse caminho pelo da sua EBOOT. O script roda os testes e gera o executável. Mantenha a pasta gerada inteira, incluindo `_internal`.

Outras opções de compilação: [docs/BUILD.md](docs/BUILD.md).

## Créditos

| Projeto / pessoas | Contribuição |
| --- | --- |
| Monolith Productions e detentores dos direitos de Blood | Jogo original |
| [Ken Silverman](https://advsys.net/ken/) | Engine BUILD |
| Jonathon Fowler e [colaboradores do JFBuild](https://github.com/jonof/jfbuild) | JFBuild |
| Nuke.YKT e [colaboradores do NBlood](https://github.com/nukeykt/NBlood) | NBlood |
| [BSzili](https://github.com/BSzili/NBlood-Amiga) | NBlood-Amiga, JFAudioLib e JFMact |
| [Rinnegatamante](https://github.com/Rinnegatamante/jfblood-vita) | jfblood-vita, ponto de partida deste port |
| **wa59** | Strafe no PSP, músicas MIDI, correções dos saves e resolução nativa |
| [Crow-bar](https://github.com/Crow-bar/PSPEDuke32) | Referências do PSPEDuke32 e PSPQuake2 |
| [Colaboradores do PSPDEV / PSPSDK](https://github.com/pspdev/pspsdk) | SDK e ferramentas do PSP |
| Bernhard Schelling / Steve Folta | TinySoundFont / SFZero |
| Sean Barrett | stb_vorbis |

Detalhes dos componentes e avisos: [CREDITS.md](CREDITS.md).

## Licença

Código distribuído sob [GPL-2.0](LICENSE), respeitando as licenças dos componentes incluídos. Blood PSP é um port não oficial feito por fãs.
