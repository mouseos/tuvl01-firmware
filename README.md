# TUVL01 firmware

日本アンテナのi-dio Wi-Fiチューナー（TUVL01）を、地上デジタル放送（UHF 13〜52ch / フルセグ・ワンセグ）のWi-Fi受信用チューナー化するカスタムファームウェアです。
起動するとWi-Fi APが立ち上がり、TVTest等から選局・TSストリーム受信が行えます。

## 特徴・仕様

- **完全スタンドアロン起動**: 電源投入後約25秒でAP（SSID: `TUVL01` / 暗号化なし）が自動起動。PC接続やUART操作は不要です。
- **フルセグ / ワンセグ対応**: フルセグ転送レート約17Mbps。
- **BonDriver同梱**: TVTest専用の `BonDriver_TUVL01.dll` からWi-Fi経由でチャンネルスキャン・選局・ストリーム制御可能。
- **プレーヤー非依存**: 独自UDPプロトコル（TTS1 / TCT1）を採用し、クライアント用C言語実装を `client/` に収録。他OSやスマホアプリへの移植も容易です。
- ※スクランブル放送の視聴・復号には別途B-CAS環境が必要です。

### LEDインジケータ
- **赤点灯**: 起動処理中
- **緑点滅（遅）**: 起動完了・待機中（クライアント未接続）
- **緑点灯**: クライアント接続中（ストリーム受信中含む）
- **赤緑高速点滅**: 起動・動作エラー

## 導入手順（SPI書き換え）

基板上のSPI NORフラッシュ（S25FL164K / 8MiB）をプログラマ等で直接書き換えます。分解が必要です。

**読み出し・書き込み・ベリファイは、次のいずれかの方法で行ってください。この条件を満たさないと失敗します。**

- 基板上で作業する場合は、USBコネクタ付近にある隠しリセットボタン **SW3を押し続けたまま**読み出し・書き込み・ベリファイを行います。
- または、SPIフラッシュのチップを基板から取り外し、プログラマで読み出し・書き込み・ベリファイを行います。作業後にチップを基板へ戻します。

バッテリーは接続したままでも、外した状態でも作業できます。

1. **バックアップ取得**: 作業前に元のフラッシュ内容を必ずバックアップしてください（ベリファイ推奨）。
2. **書き込みイメージの準備**:
   - リリースの `tuvl01-spi-8MiB.bin` を使用（`SHA256SUMS.txt` でハッシュ確認）。
   - または下記ビルド手順で独自ビルド。
3. **ROM焼き**: `tuvl01-spi-8MiB.bin` をフラッシュ全体（8MiB）に書き込み、ベリファイを実施。
4. **起動確認**: 基板を戻して電源投入。約25秒後にLEDが緑点滅になり、SSID `TUVL01` が見えれば成功です。

※純正ファームに戻す場合は、事前に退避したダンプを書き戻してください。

## TVTestでの利用手順

1. PCのWi-Fiを `TUVL01` に接続（DHCPで `192.168.74.2` が割り当てられます）。
2. `BonDriver_TUVL01.dll` をTVTestフォルダに配置。
3. `TVTest.exe /d BonDriver_TUVL01.dll` を起動し、チャンネルスキャンを実行。
   - チューニング空間: `UHF`（フルセグ） / `UHF (1seg)`（ワンセグ）
4. ※WindowsファイアウォールでTVTestのUDPポート4202受信が許可されている必要があります。

## ビルド方法

Ubuntu 24.04 または WSL2（Ubuntu）環境でビルドします。

```sh
sudo apt-get install build-essential binutils-sh-elf libgmp-dev libmpfr-dev libmpc-dev python3 git
git clone --recurse-submodules https://github.com/mouseos/tuvl01-firmware.git
cd tuvl01-firmware
python3 tools/bootstrap.py
python3 tools/build_release.py --out release
```

`release/` ディレクトリに以下のファイルが生成されます：
- `tuvl01-spi-8MiB.bin`: SPI書込用フルイメージ
- `SHA256SUMS.txt`: ハッシュリスト
- `BonDriver_TUVL01.dll`: TVTest用BonDriver（ビルド済みの場合）

※開発・デバッグ用イメージ（UART制御前提）をビルドする場合は単に `make` を実行してください。

## 通信仕様（Wi-Fi UDP）

| 項目 | 設定値 |
| --- | --- |
| AP設定 | SSID: `TUVL01` / 2.4GHz / 認証なし / 1クライアント |
| IP割当 | デバイス: `192.168.74.1` / クライアント: `192.168.74.2` (DHCP) |
| 制御ポート | UDP `192.168.74.1:4200`（コマンド / レスポンス） |
| キープアライブ / エコー | UDP `192.168.74.1:4201` |
| TSストリーム | UDP `192.168.74.1:4202` → `192.168.74.2:4202` |

### ストリームフォーマット（TTS1）
各UDPパケットは16バイトヘッダ + 188バイトTSパケット（1〜7個）で構成されます。ビッグエンディアン。

- `0x00` (4B): マジック `TTS1`
- `0x04` (4B): パケットシーケンス番号（STARTごとに0リセット、1ずつ加算）
- `0x08` (4B): TSパケット通し番号（STARTごとに0リセット）
- `0x0C` (4B): フラグ（bit0: FIFO再同期フラグ）
- `0x10`〜: TSデータ本体（188 * n バイト）

※ストリーム開始（START）ごとにシーケンス番号は0に初期化されます。受信側でパケット破棄判定を行う際はストリーム境界（seq=0, index=0）を考慮してください。

### コントロールコマンド（TCT1）
UDPポート4200宛てに送信。ヘッダは `TCT1` (4B) + コマンド (1B) + 予約 (1B) + 要求ID (2B) + パラメータ。
応答はコマンドの最上位ビット（0x80）が立ち、5バイト目にステータスコード（0: 成功）が格納されます。

- **HELLO (0x01)**: バージョン・機能ビット等の照会
- **START (0x02)**: ストリーム送信開始
- **STOP (0x03)**: ストリーム送信停止
- **STATUS (0x04)**: 現在のステータス取得（選局ch、ロック状態等）
- **KEEPALIVE (0x05)**: セッション維持（5秒無通信で自動停止）
- **TUNE (0x06)**: 選局要求（ch: 13〜52 / mode: 0=フルセグ, 1=ワンセグ）

## UARTインターフェース（開発・リカバリ用）

ボーレート: 115200bps / 8N1（3.3V TTL、Tx/Rx交差接続）

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r tools\requirements.txt
```

ファームウェア更新（ブートローダ起動中）:
```powershell
python tools/uart.py recover --port COMx --log logs/update.bin
python tools/uart.py upload --port COMx --image build/app.img --log logs/update.bin
python tools/uart.py save --port COMx --log logs/update.bin
```

電源投入後5秒以内にUART入力を検知した場合、自動起動をキャンセルしてリカバリ待機状態を維持します。

## ライセンス

本プロジェクトのオリジナルコードおよびツール類は MIT ライセンスです。
詳細は `LICENSE` を参照してください。

- FreeRTOS Kernel: MIT
- wpa_supplicant (一部): BSD-3-Clause
- nanoprintf: 0BSD
- `firmware/` 配下のバイナリ（MT5931 radio firmware, MN885521 PSEQ）はハードウェア固有のファームウェアデータです（MIT対象外）。
