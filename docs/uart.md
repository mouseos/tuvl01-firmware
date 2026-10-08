# UART console

115200 baud、8 data bits、no parity、1 stop bit、flow controlなしです。
adapterは基板と電圧・GNDを合わせ、TxD/RxDを交差接続します。
PCツールはDTR/RTSをfalseで開きます。terminalと同じポートを同時に開かないでください。

## 編集・ビルド・RAM実行

PC環境は[ビルド手順](build.md)で準備します。`COMx`を実際のポートへ変更してください。

```powershell
tools\uart-cycle.ps1 -Port COMx
```

WSLでビルド後、imageのheader・size・CRCを検査してRAMへ転送します。
起動bannerと進行するRTOS tickを取得します。SPIはこの操作では更新しません。

手動転送:

```powershell
python tools/uart.py cycle --port COMx --image build/app.img --log logs/cycle.bin
```

## 永続更新

```powershell
python tools/uart.py recover --port COMx --log logs/update.bin
python tools/uart.py upload --port COMx --image build/app.img --log logs/update.bin
python tools/uart.py save --port COMx --log logs/update.bin
python tools/uart.py load --port COMx --log logs/update.bin
python tools/uart.py run --port COMx --log logs/update.bin
```

`save`がSPI applicationを書き換える操作です。読戻し成功を確認してから実行します。
範囲・中断時の復旧は[image仕様](images-and-recovery.md)を参照してください。
applicationで`audit`を実行すると保護されたNOR領域のCRCを読み出します。

## 起動ログ

```powershell
python tools/log.py COMx --seconds 30 --output logs/startup.txt
```

開いた後にリセットすれば最初のbannerを取得できます。
loaderは`TUVL01 independent recovery boot`、
applicationは`TUVL01 independent / FreeRTOS 11.1.0 / GNU SH2A BE`を出力します。

## loader console protocol

| byte | 処理 |
| --- | --- |
| `i` | status・written・ready・busyを照会 |
| `b` | 32B image header受信を開始 |
| `w` | offset uint32 BE、length uint16 BE、payload chunk受信 |
| `s` | 全payloadのCRCを検査してseal |
| `r` | sealされたapplicationを実行 |
| `p` | sealされたapplicationをSPIへ保存 |
| `l` | SPI applicationをRAMへ読出し・検査 |

PCツールは64B chunkと各responseの待合せを使用します。
applicationでは`i`で状態、`q`でrecoveryへ戻します。他のbyteはapplication用commandです。
header検査とtimeoutを持つ`tools/uart.py`を使用してください。

## 機能別コマンド

`python tools/uart.py --help`に全commandと引数を列挙しています。
Wi-Fi操作は[Wi-Fi](wifi.md)、選局・TS・TVTestは[チューナー](tuner.md)を参照してください。
診断commandの成功はそれぞれの限定した検査が通ったことを示します。
