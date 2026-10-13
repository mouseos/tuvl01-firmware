# TUVL01 firmware

日本アンテナ製 i-dio Wi-Fiチューナー TUVL01（Renesas SH726A、SH-2A、big endian）用の独立ファームウェアです。
標準ファームの代わりに入れると、電源を入れるだけでUHFのテレビ放送（フルセグ・ワンセグ）をWi-Fi経由でPCへ送るチューナーになります。
MCU側のCソース、startup、FreeRTOS Kernel、ドライバをソースからビルドします。
MT5931用radio firmwareとMN885521用PSEQデータを`firmware/`に同梱しています。

## できること

- 電源投入だけで単独起動（約25秒）。PCもUARTも不要です。
- UHF 13〜52chのフルセグ・ワンセグを、Wi-Fi（open SSID `TUVL01`）から選局して受信できます。フルセグは約17 Mbpsです。
- PC側は専用の`BonDriver_TUVL01.dll`（TVTest用）を使います。スキャン、選局、受信の開始・停止はすべてWi-Fi経由です。
- 通信は特定のプレーヤーに依存しません（下記の通信仕様、標準Cのクライアント`client/`）。

放送がスクランブルされている場合は、視聴にB-CAS等の環境が別に必要です。

LED: 起動中は赤、待機中（未接続）は緑のゆっくりした点滅、接続中は緑の点灯、失敗は赤緑の速い点滅です。

## 導入（SPIプログラマ）

1. **最初に元のSPI（S25FL164K、8MiB）を全部読み出して保管します**（2回読んで一致を確認）。標準ファームへ戻すのに使います。
2. 書込みイメージを用意します。リリースの`tuvl01-spi-8MiB.bin`（`SHA256SUMS.txt`で照合）を使うか、自分でビルドします。

   ```sh
   python3 tools/build_release.py --out release                 # firmware/ のデータを使う
   python3 tools/build_release.py 元ダンプ.BIN --out release    # 自分の機体のダンプから取り出して使う
   ```

   `firmware/`のデータはSHA-256を検査し、一致しなければ止まります。単独起動版をビルドし、loaderとapplicationの位置・CRC、
   単独起動版であることを検査してから`release/tuvl01-spi-8MiB.bin`を出力します。
3. `tuvl01-spi-8MiB.bin`をチップ全体に書込み、**読み戻して一致を確認します。**
4. 組み立てて電源を入れます。約25秒でAPが上がります。

標準ファームのSPIで中身があるのは、loader領域（先頭8KiB）と標準アプリ（`0x40000`以降）だけです。
8MiB全体を置き換えると標準アプリは消えます。標準ファームに戻すときは、保管した元ダンプを書き戻します。

元ダンプからデータだけを取り出すこともできます（版が違うダンプはSHA-256が一致せず拒否されます）。

```sh
python3 tools/extract_vendor.py 元ダンプ.BIN
```

## TVTestで見る

1. PCのWi-Fiを`TUVL01`（open）へ接続します（DHCPで`192.168.74.2`になります）。
2. `BonDriver_TUVL01.dll`（リリースにあります。自分でビルドするなら`client/bondriver/build.ps1`、LLVMのみでMSVC不要）をTVTestのフォルダへ置きます。
3. `TVTest.exe /d BonDriver_TUVL01.dll`で起動し、チャンネルスキャンを実行します。チャンネル空間は「UHF」（フルセグ）と「UHF (1seg)」です。

PCのファイアウォールで`TVTest.exe`の受信（UDP 4202）が許可されている必要があります。
BonDriverの信号レベルは、ロックの有無（と受信レート）だけを反映します（受信品質の較正値はありません）。

## ビルド

Ubuntu 24.04またはWSLのUbuntuで実行します。

```sh
sudo apt-get install build-essential binutils-sh-elf libgmp-dev libmpfr-dev libmpc-dev python3 git
git clone --recurse-submodules https://github.com/mouseos/tuvl01-firmware.git
cd tuvl01-firmware
python3 tools/bootstrap.py
make                                  # 開発版。build/app.img がUART転送するapplication
make AUTOSERVE=1                      # 単独起動版（通常は tools/build_release.py を使う）
python3 -m unittest discover -s tests -v
```

生成物: `build/boot.bin`（先頭8KiBのloader）、`build/app.img`（32Bヘッダ付きapplication）、`build/initial-spi.bin`（8MiBの初回書込みimage）。
SPI配置は、loaderが`0x0`〜`0x2000`、applicationが`0x10000`以降です。applicationのload・entryは`0x1c000000`、payload上限は`0xfc000`Bです。

loaderは電源投入後5秒間、UARTの受信を待ちます。何も来なければSPIのapplicationをCRC検査して実行し、1バイトでも受信すると待機に残ります。

## 通信仕様（Wi-Fi）

どのクライアント（TVTest、スマートフォン等）からでも使えます。数値はすべてビッグエンディアンです。

| 項目 | 値 |
| --- | --- |
| AP | open SSID `TUVL01`、2.4GHz、単一クライアント |
| 装置IP | `192.168.74.1`（DHCP、クライアントは`192.168.74.2`） |
| 制御 | UDP `192.168.74.1:4200`（要求/応答） |
| 生存確認・エコー | UDP `192.168.74.1:4201`（受けた内容を返す） |
| ストリーム | UDP 装置`:4202` → クライアント`192.168.74.2:4202`（クライアントがbindして受信） |

### ストリーム（TTS1）

1データグラムは16バイトのヘッダと、188バイトのTSパケットを1〜7個並べた本体です。

| オフセット | 長さ | 内容 |
| --- | --- | --- |
| 0 | 4 | `TTS1` |
| 4 | 4 | シーケンス番号（データグラム毎に+1、32bitで巻く） |
| 8 | 4 | 先頭TSパケットの通し番号 |
| 12 | 4 | フラグ。bit0 = 装置FIFOの再同期 |
| 16 | 188×n | TSパケット |

欠落はシーケンス番号の飛びで検出します。**`START`のたびに新しいストリームが始まり、シーケンス番号と通し番号は0から再開します。**
シーケンス0かつ通し番号0のデータグラムは、新しいストリームの先頭として受け入れてください（前の位置を覚えたまま「遅れて届いたもの」と
判定して捨てると、選局し直した後のストリームを全部捨てます）。

### 制御（UDP 4200）

要求は`TCT1`(4B)、操作コード(1B)、0(1B)、要求ID(2B)の8バイトと、操作ごとのペイロードです。
応答は同じ形式で、操作コードに`0x80`が付き、オフセット5が状態（`0`成功、`1`要求不正、`2`未対応）になります。

| 操作 | コード | 要求ペイロード | 応答ペイロード |
| --- | --- | --- | --- |
| HELLO | 1 | なし | プロトコル版u8、revision u16、機能ビットu32、ストリームポートu16、状態u8、最初のチャンネルu8、最後のチャンネルu8 |
| START | 2 | なし | 状態u8 |
| STOP | 3 | なし | 状態u8 |
| STATUS | 4 | なし | 状態u8、チャンネルu16（0=未選局）、モードu8、選局状態u8、ロックu8 |
| KEEPALIVE | 5 | なし | 状態u8 |
| TUNE | 6 | チャンネルu8（13〜52）、モードu8（0=フルセグ、1=ワンセグ） | 選局状態u8 |

- 状態（ストリーム）: `0`停止、`1`送信中、`2`開始要求受理済み。機能ビット: bit0=START/STOP、bit1=TUNE。
- 選局状態: `0`未実施、`1`選局中、`2`完了、`3`失敗。ロック: `0`非ロック、`1`ロック、`255`不明（約1秒ごとに更新）。
- `TUNE`は走行中のストリームを止めてから選局します。STATUSの選局状態が`2`でチャンネル・モードが要求どおりになるまで待ち、`START`を送ります。
  選局にはロック待ちを含め、通常約1秒、最長約5秒かかります。選局完了は放送の受信を保証しません。受信はSTATUSのロックで確認します。
- 制御で開始したストリームは、クライアントから4200または4201宛てのデータグラムが5秒間来ないと、装置が自動で停止します。
  `KEEPALIVE`を1秒間隔程度で送るか、下記の4201パケットを使います。UARTで開始したストリームは自動停止しません。
- PCのWi-Fiアダプタの省電力で欠落が出る場合は、ストリーム中に4201へ短いデータグラムを10ms間隔程度で送ると減ります。

## 開発（UART）

115200bps、8N1。UARTアダプタは基板と電圧・GNDを合わせ、TxD/RxDを交差接続します。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r tools\requirements.txt
tools\serve.ps1 -Port COMx           # RAMへ転送して起動（開発版）。PCツールは tools/uart.py（--help）
```

UARTでのapplication更新（本ファームのloaderが入っている機体）:

```powershell
python tools/uart.py recover --port COMx --log logs/update.bin
python tools/uart.py upload --port COMx --image build/app.img --log logs/update.bin
python tools/uart.py save --port COMx --log logs/update.bin
```

## ライセンス

独立MCU実装とPCツールはMIT（`LICENSE`）です。

| 対象 | ライセンス |
| --- | --- |
| FreeRTOS Kernel V11.1.0 | MIT |
| wpa_supplicant 2.12（RSN部分） | BSD-3-Clause（`third_party/wpa_supplicant/COPYING`） |
| nanoprintf | 0BSD |
| GCC 13.3.0、GNU binutils（ビルドのみ） | GPL（整数runtimeはGCC Runtime Library Exception） |
| pyserial、PyUSB、libusb-package（PC側のみ） | BSD-3-Clause、Apache-2.0、LGPL-2.1-or-later |
| `firmware/`のMT5931・MN885521データ | メーカーのデータ。MIT適用外 |
