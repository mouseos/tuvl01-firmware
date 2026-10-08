# ビルド

## 環境

LinuxまたはWSL Ubuntu 24.04、Python 3、GNU make、host C compiler、`sh-elf` binutilsを使用します。
SH726A向けコンパイルはGCC 13.3.0、`-m2a-nofpu -mb -Os -ffreestanding`です。
hosted libcと浮動小数点runtimeは使用しません。必要な整数libgccを同じGCCソースから構築します。

```sh
sudo apt-get install build-essential binutils-sh-elf libgmp-dev libmpfr-dev libmpc-dev python3 git
git clone --recurse-submodules https://github.com/mouseos/tuvl01-firmware.git
cd tuvl01-firmware
python3 tools/bootstrap.py
make
```

既存cloneでは`git submodule update --init --recursive`を実行してください。
bootstrapは公式GCC archiveのSHA256を確認します。toolchainの既定配置は
`~/.cache/tuvl01-independent/gcc13/install`です。
配置変更時はbootstrapの`TUVL_TOOLCHAIN_DIR`とmakeの`TOOLCHAIN`を合わせます。

```sh
TUVL_TOOLCHAIN_DIR=/opt/tuvl01-gcc python3 tools/bootstrap.py
make TOOLCHAIN=/opt/tuvl01-gcc/install
```

## 構成

| パス | 内容 |
| --- | --- |
| `src/boot.c`、`src/startup.S` | recovery bootloader、startup・例外入口 |
| `src/app.c`、`include/FreeRTOSConfig.h` | applicationとRTOS設定 |
| `src/board.c`、`include/board.h` | 基板固有のclock・RAM・UART・GPIO設定 |
| `linker/boot.ld`、`linker/app.ld` | loaderとapplicationのメモリ配置 |
| `rtos/port/` | GNU SH-2A integer用FreeRTOS port |
| `rtos/wpa/port/` | RSN用メモリ・timer・UART・MT5931接続層 |
| `third_party/` | 固定版の依存ソースとライセンス |
| `firmware/` | MT5931 firmware、MN885521 PSEQデータ |
| `profiles/` | チューナー設定JSON |
| `tools/`、`tests/` | PCツール、host側試験 |

元のSPI dumpや解析用ELFはビルドに不要です。同梱binaryと依存ソースのhashを検査します。
FreeRTOS Kernelはsubmodule、wpa_supplicantのRSN部分とnanoprintfはmanifestで固定しています。

## 検証と出力

```sh
python3 -m unittest discover -s tests -v
```

host側試験はimage・通信protocol・状態遷移・依存データなどを検証します。
実機の起動、UART、無線通信、USB列挙の試験は含みません。
`build/manifest.json`は4imageのサイズとSHA256を記載します。[image仕様](images-and-recovery.md)を参照してください。
再現性の比較では同じtoolchain・submodule・ソースを用いて空の`build/`から生成した4imageを比較します。

## Windows側ツール

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r tools\requirements.txt
```

UARTツールはpyserial、USBツールはPyUSBとlibusbを使用します。
`tools/uart-cycle.ps1`の`-Distribution`でWSL distribution、`-LogDirectory`で出力先を指定できます。

## 別のMT5931 firmwareを選ぶ

既定は同梱の`firmware/mt5931.bin`です。外部ファイルの比較ビルドでは
`RADIO_FILE`と`RADIO_SHA256`を指定します。検証器が許可したサイズ・SHA256の組だけ使用でき、
全長とCRC32をapplicationへ埋め込みます。変更時にはapplicationを再リンクします。

```sh
make RADIO_FILE=/path/to/WIFI_RAM_CODE RADIO_SHA256=<approved-sha256>
```

検証器が受け付ける外部候補は139,776バイト、SHA256
`af345785369ee0a53efd85654810ba47463833186201fb3d3e9f9ac8195ca53c`です。
外部候補は同梱していません。入手・配布条件と対象chipの互換性は別途確認が必要です。
ビルド成功は、そのfirmwareの実機起動や通信速度を保証しません。
Wi-Fi firmwareが既に起動している場合、applicationの再実行だけでは差し替わりません。
比較時にはWi-Fiモジュールを含む電源の再投入が必要です。
