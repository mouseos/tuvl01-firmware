# TUVL01 firmware

Renesas SH726A（SH-2A、big endian）搭載TUVL01用の独立ファームウェアです。
MCU側のCソース、startup、FreeRTOS Kernel、ドライバをソースからビルドします。
MT5931用radio firmwareとMN885521用PSEQデータを同梱しています。

## 機能

| 機能 | 対応状況 |
| --- | --- |
| SPI NOR起動、UART console、FreeRTOS | 対応 |
| UARTによるapplicationのRAM転送・CRC検査・実行 | 対応 |
| UARTによるSPI application更新・読戻し | 対応。先頭64KiBを保護 |
| MT5931 open AP、単一PC接続、DHCP・ARP・ping・UDP | 対応 |
| UHFワンセグTSのWi-Fi転送 | 対応。周波数と受信環境に依存 |
| フルセグ | 設定・転送コードあり。連続受信・転送は未保証 |
| WPA2 station | 実験用RSN処理あり。保護された通信は未実装 |
| SH726A native USB | 実装あり。列挙・転送・更新は未確認 |

各ビルドの動作確認は別途必要です。生成manifestの`hardware_tested`は`false`です。

## ビルド

Ubuntu 24.04またはWSLのUbuntuで実行します。

```sh
sudo apt-get install build-essential binutils-sh-elf libgmp-dev libmpfr-dev libmpc-dev python3 git
git clone --recurse-submodules https://github.com/mouseos/tuvl01-firmware.git
cd tuvl01-firmware
python3 tools/bootstrap.py
make
python3 -m unittest discover -s tests -v
```

SPIへ初回書込みするimageは`build/initial-spi.bin`、UART転送するapplicationは`build/app.img`です。
書込み先、hash確認、復旧の手順は[image配置・SPI書込み](docs/images-and-recovery.md)を参照してください。

## 編集・転送・実行

WindowsのPCツールを準備します。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r tools\requirements.txt
```

ソース編集後、接続中のUARTポートを指定します。`COMx`は実際のポート名へ変更してください。

```powershell
tools\uart-cycle.ps1 -Port COMx
```

WSLでビルドし、UART経由でRAMへ転送・実行してRTOS tickを確認します。
SPIへ保存する操作は[UART手順](docs/uart.md)に分けています。

## 技術資料

- [ビルドと依存関係](docs/build.md)
- [image配置・SPI書込み・更新・復旧](docs/images-and-recovery.md)
- [UART consoleとPCツール](docs/uart.md)
- [Wi-FiとRSN機能](docs/wifi.md)
- [UHF設定・TS転送・TVTest入力](docs/tuner.md)
- [native USBの条件とプロトコル](docs/usb.md)
- [ライセンス](docs/licenses.md)、[同梱メーカーbinary](firmware/NOTICE.md)
