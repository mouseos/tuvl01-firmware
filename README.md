# TUVL01 firmware

日本アンテナ製 i-dio Wi-Fiチューナー TUVL01（Renesas SH726A、SH-2A、big endian）用の独立ファームウェアです。
標準ファームの代わりに入れると、電源を入れるだけでUHFのテレビ放送（フルセグ・ワンセグ）をWi-Fi経由でPCへ送るチューナーになります。
MCU側のCソース、startup、FreeRTOS Kernel、ドライバをソースからビルドします。
MT5931用radio firmwareとMN885521用PSEQデータ（メーカー製データ）を同梱しています。**権利者の許諾は未確認です**。
必ず[同梱メーカーbinaryの注意](firmware/NOTICE.md)を読んでください。

## できること

- 電源投入だけで単独起動（約25秒）。PCもUARTも不要です。LEDで状態が分かります（起動中=赤、待機中=緑の点滅、接続中=緑の点灯）。
- UHF 13〜52chのフルセグ・ワンセグを、Wi-Fi（open SSID `TUVL01`）から選局して受信できます。フルセグは約17 Mbpsです。
- PC側は専用の`BonDriver_TUVL01.dll`（TVTest用）を使います。スキャン、選局、受信の開始・停止はすべてWi-Fi経由です。
- スマートフォン等へ移植しやすいよう、通信は特定のプレーヤーに依存しない仕様です（[Wi-Fiプロトコル](docs/protocol.md)、標準Cのクライアント`client/`）。

放送がスクランブルされている場合は、視聴にB-CAS等の環境が別に必要です。

## 導入

SPIプログラマで、S25FL164K（8MiB）へ書き込みます。**書込み前に、元のSPIを必ず読み出して保管してください**（標準ファームへ戻すのに必要です）。
手順、確認済みの範囲、未確認の範囲は[配布と導入](docs/distribution.md)にあります。

標準ファームの更新機能（Wi-Fi）を使えるかは調査中で、未検証です。ケース開封なしでの導入は、現時点ではできません。

## 状態

| 機能 | 対応状況 |
| --- | --- |
| SPI NOR起動、単独起動、UART console、FreeRTOS | 実機確認済み |
| UHF 13〜52chの選局（フルセグ・ワンセグ）、Wi-Fi経由 | 実機確認済み（ロックしたチャンネルで受信を確認。ロックの有無は電波環境による） |
| TVTest（`BonDriver_TUVL01.dll`）での視聴 | 実機確認済み |
| MT5931 open AP、単一PC接続、DHCP・ARP・ping・UDP | 実機確認済み |
| UARTによるapplicationのRAM転送・SPI更新・ローダー更新 | 実機確認済み |
| 長時間の欠落ゼロ | 未達。PC側Wi-Fiアダプタの省電力で、300秒で約0.6%の欠落が出ることがある |
| WPA2 station | 実験用RSN処理あり。保護された通信は未実装 |
| SH726A native USB | 実装あり。列挙・転送・更新は未確認 |

受信品質の数値は較正されていません。BonDriverの信号レベルは、ロックの有無（と受信レート）だけを反映します。

## ビルド

Ubuntu 24.04またはWSLのUbuntuで実行します。

```sh
sudo apt-get install build-essential binutils-sh-elf libgmp-dev libmpfr-dev libmpc-dev python3 git
git clone --recurse-submodules https://github.com/mouseos/tuvl01-firmware.git
cd tuvl01-firmware
python3 tools/bootstrap.py
python3 tools/build_release.py --out release   # 単独起動版のSPIイメージ（release/tuvl01-spi-8MiB.bin）
python3 -m unittest discover -s tests -v
```

開発用（UARTから操作する版）は`make`、`build/app.img`がUART転送するapplicationです。
PC側のBonDriverは`client/bondriver/build.ps1`（LLVMでビルド。MSVCは不要）で作ります。

## 開発（UART）

WindowsのPCツールを準備します。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r tools\requirements.txt
```

UARTでRAMへ転送して試すには、ポート名を指定します。`COMx`は実際のポート名へ変更してください。

```powershell
tools\serve.ps1 -Port COMx
```

## 技術資料

- [配布と導入](docs/distribution.md)
- [Wi-Fiプロトコル（クライアント非依存）](docs/protocol.md)
- [ビルドと依存関係](docs/build.md)
- [image配置・単独起動・SPI書込み・更新・復旧](docs/images-and-recovery.md)
- [UART consoleとPCツール](docs/uart.md)
- [Wi-FiとRSN機能](docs/wifi.md)
- [UHF設定・TS転送・TVTest入力](docs/tuner.md)
- [native USBの条件とプロトコル](docs/usb.md)
- [ライセンス](docs/licenses.md)、[同梱メーカーbinary](firmware/NOTICE.md)
