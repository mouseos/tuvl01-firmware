# TUVL01 firmware

日本アンテナのi-dio Wi-Fiチューナー TUVL01（Renesas SH726A）に、標準ファームの代わりに入れるファームウェア。電源を入れると、UHFのフルセグとワンセグをWi-Fiで送るチューナーとして立ち上がる。PC側に要るのはTVTest用のBonDriver 1本だけ。

MCU側のCソース、startup、FreeRTOS Kernel、ドライバはすべてソースからビルドする。例外はMT5931のradio firmwareとMN885521のPSEQデータで、標準ファームから取り出したバイナリを`firmware/`に置いてある。

## 動作

- 電源を入れて約25秒でAP（SSID `TUVL01`、パスワードなし）が上がる。PCもUARTも要らない。
- UHF 13〜52chを選局できる。フルセグは約17 Mbps出る。
- チャンネルスキャン、選局、受信の開始と停止は、BonDriverがWi-Fi越しにやる。
- 通信仕様は特定のプレーヤーに依存しない。標準Cのクライアントを`client/`に置いたので、スマホへ移すときはそれを使う。
- スクランブルされた放送を見るには、視聴側にB-CASなどの環境が別に要る。

LEDで状態が分かる。

- 赤が点灯: 起動中
- 緑がゆっくり点滅: 起動済みで、クライアントがつながっていない
- 緑が点灯: クライアントが接続している（受信中も同じ）
- 赤と緑が速く点滅: 失敗

## 書き込み

SPIプログラマでS25FL164K（8MiB）に書く。ケースを開ける必要がある。

1. 先に元のSPIを全部読み出して保管する。2回読んで一致を確かめること。標準ファームへ戻すときに使う。
2. 書き込むイメージを用意する。リリースの`tuvl01-spi-8MiB.bin`を`SHA256SUMS.txt`と照合して使うか、自分でビルドする。

   ```sh
   python3 tools/build_release.py --out release                 # firmware/ のデータを使う
   python3 tools/build_release.py 元ダンプ.BIN --out release    # 自分の機体のダンプから取り出して使う
   ```

   `firmware/`のデータはSHA-256を検査し、合わなければ止まる。単独起動版をビルドしたあと、loaderとapplicationの位置とCRC、単独起動版であることを確かめてから`release/tuvl01-spi-8MiB.bin`を出す。
3. `tuvl01-spi-8MiB.bin`をチップ全体に書き、読み戻して一致を確かめる。
4. 組み立てて電源を入れる。約25秒でAPが上がる。

標準ファームのSPIで中身があるのは、先頭8KiBのloaderと、`0x40000`以降の標準アプリだけだった。8MiB全体を置き換えると標準アプリは消える。戻すときは、保管した元ダンプを書き戻す。

元ダンプからデータだけ取り出すこともできる。版の違うダンプはSHA-256が合わず、拒否される。

```sh
python3 tools/extract_vendor.py 元ダンプ.BIN
```

## TVTestで見る

1. PCのWi-Fiを`TUVL01`につなぐ。DHCPで`192.168.74.2`になる。
2. `BonDriver_TUVL01.dll`をTVTestのフォルダに置く。リリースに入っている。自分でビルドするなら`client/bondriver/build.ps1`を使う（LLVMだけで足りる。MSVCは要らない）。
3. `TVTest.exe /d BonDriver_TUVL01.dll`で起動して、チャンネルスキャンをかける。チャンネル空間はフルセグの`UHF`とワンセグの`UHF (1seg)`の2つ。

PCのファイアウォールで、`TVTest.exe`のUDP 4202の受信を許可しておく。

BonDriverの信号レベルは、ロックしているかどうかと受信レートしか反映しない。受信品質を較正した値は持っていない。

## ビルド

Ubuntu 24.04かWSLのUbuntuで実行する。

```sh
sudo apt-get install build-essential binutils-sh-elf libgmp-dev libmpfr-dev libmpc-dev python3 git
git clone --recurse-submodules https://github.com/mouseos/tuvl01-firmware.git
cd tuvl01-firmware
python3 tools/bootstrap.py
make                                  # 開発版。build/app.img をUARTで転送する
make AUTOSERVE=1                      # 単独起動版（普通は tools/build_release.py を使う）
python3 -m unittest discover -s tests -v
```

出力は3つ。`build/boot.bin`は先頭8KiBのloader、`build/app.img`は32Bのヘッダが付いたapplication、`build/initial-spi.bin`は8MiBの初回書き込み用イメージ。

SPIの配置は、loaderが`0x0`〜`0x2000`、applicationが`0x10000`以降。applicationのload先とentryは`0x1c000000`で、payloadは`0xfc000`Bまで。

loaderは電源投入から5秒間、UARTの受信を待つ。何も来なければ、SPI上のapplicationをCRCで検査して実行する。1バイトでも受信したら待機に残るので、壊れたapplicationも入れ替えられる。

## 通信仕様（Wi-Fi）

TVTest、スマホなど、どのクライアントからでも使える。数値はすべてビッグエンディアン。

| 項目 | 値 |
| --- | --- |
| AP | open SSID `TUVL01`、2.4GHz、クライアントは1台だけ |
| 装置のIP | `192.168.74.1`（DHCPで、クライアントに`192.168.74.2`を渡す） |
| 制御 | UDP `192.168.74.1:4200`（要求と応答） |
| 生存確認とエコー | UDP `192.168.74.1:4201`（受け取った内容を返す） |
| ストリーム | UDP 装置の`:4202`からクライアントの`192.168.74.2:4202`へ。クライアントがbindして受ける |

### ストリーム（TTS1）

1データグラムは、16バイトのヘッダと、188バイトのTSパケット1〜7個。

| オフセット | 長さ | 内容 |
| --- | --- | --- |
| 0 | 4 | `TTS1` |
| 4 | 4 | シーケンス番号（データグラムごとに+1、32bitで巻く） |
| 8 | 4 | 先頭TSパケットの通し番号 |
| 12 | 4 | フラグ。bit0は装置FIFOの再同期 |
| 16 | 188×n | TSパケット |

欠落はシーケンス番号の飛びで分かる。

`START`のたびに新しいストリームが始まり、シーケンス番号も通し番号も0から数え直す。前のストリームの位置を覚えたままだと、新しい番号が小さく見えて遅延パケットとして捨てられ、選局し直した後のデータが1つも届かなくなる。シーケンス0かつ通し番号0のデータグラムは、新しいストリームの先頭として受け入れること。

### 制御（UDP 4200）

要求は8バイトのヘッダに、操作ごとのペイロードが続く。ヘッダは`TCT1`(4B)、操作コード(1B)、0(1B)、要求ID(2B)。応答も同じ形で、操作コードに`0x80`が立ち、オフセット5が状態になる（`0`成功、`1`要求不正、`2`未対応）。

| 操作 | コード | 要求ペイロード | 応答ペイロード |
| --- | --- | --- | --- |
| HELLO | 1 | なし | プロトコル版u8、revision u16、機能ビットu32、ストリームポートu16、状態u8、最初のチャンネルu8、最後のチャンネルu8 |
| START | 2 | なし | 状態u8 |
| STOP | 3 | なし | 状態u8 |
| STATUS | 4 | なし | 状態u8、チャンネルu16（0は未選局）、モードu8、選局状態u8、ロックu8 |
| KEEPALIVE | 5 | なし | 状態u8 |
| TUNE | 6 | チャンネルu8（13〜52）、モードu8（0=フルセグ、1=ワンセグ） | 選局状態u8 |

各値の意味:

- ストリームの状態は`0`が停止、`1`が送信中、`2`が開始要求の受理済み。機能ビットはbit0がSTART/STOP、bit1がTUNE。
- 選局状態は`0`未実施、`1`選局中、`2`完了、`3`失敗。ロックは`0`が非ロック、`1`がロック、`255`が不明で、約1秒ごとに更新される。

使い方:

- `TUNE`は、動いているストリームを止めてから選局する。STATUSの選局状態が`2`になり、チャンネルとモードが要求どおりになるまで待って、`START`を送る。ロック待ちを含めて、選局は普通1秒前後、長くて5秒ほどかかる。
- 選局が終わっても、放送を受信できたとは限らない。受信できているかはSTATUSのロックで見る。
- 制御で始めたストリームは、クライアントから4200か4201宛てのデータグラムが5秒来ないと、装置が自動で止める。`KEEPALIVE`を1秒間隔くらいで送るか、下の4201パケットで間に合わせる。UARTで始めたストリームは自動では止まらない。
- PCのWi-Fiアダプタが省電力に入ると欠落が出ることがある。ストリーム中に4201へ短いデータグラムを10ms間隔くらいで送ると減る。

## 開発（UART）

115200bps、8N1。UARTアダプタは基板と電圧とGNDを合わせ、TxDとRxDを交差させてつなぐ。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r tools\requirements.txt
tools\serve.ps1 -Port COMx           # RAMに転送して起動する（開発版）。PCツールは tools/uart.py（--help）
```

本ファームのloaderが入っている機体では、UARTでapplicationを入れ替えられる。

```powershell
python tools/uart.py recover --port COMx --log logs/update.bin
python tools/uart.py upload --port COMx --image build/app.img --log logs/update.bin
python tools/uart.py save --port COMx --log logs/update.bin
```

## ライセンス

独立MCU実装とPCツールはMIT（`LICENSE`）。

| 対象 | ライセンス |
| --- | --- |
| FreeRTOS Kernel V11.1.0 | MIT |
| wpa_supplicant 2.12（RSN部分） | BSD-3-Clause（`third_party/wpa_supplicant/COPYING`） |
| nanoprintf | 0BSD |
| GCC 13.3.0、GNU binutils（ビルド時のみ） | GPL（整数runtimeはGCC Runtime Library Exception） |
| pyserial、PyUSB、libusb-package（PC側のみ） | BSD-3-Clause、Apache-2.0、LGPL-2.1-or-later |
| `firmware/`のMT5931とMN885521のデータ | メーカーのデータ。MITの対象外 |
