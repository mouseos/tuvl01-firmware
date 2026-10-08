# UHF受信・TS転送

MN885521の基板初期化、I2C制御、PSEQ転送、周波数設定、TMCC・品質読出し、TS取得を実装します。
PSEQは同梱binaryを使用します。[同梱データ](../firmware/NOTICE.md)を参照してください。
ワンセグを主用途とし、フルセグ用設定は実験用です。フルセグの連続受信・Wi-Fi転送を保証しません。

## 初期化・選局

application実行後にUARTポートを指定します。

```powershell
python tools/uart.py tuner-init --port COMx --log logs/tuner.bin
python tools/tune.py --port COMx --profile profiles/uhf-ch14-partial.json --log logs/tuner.bin
python tools/uart.py tmcc --port COMx --log logs/tuner.bin
python tools/uart.py ts-output --port COMx --log logs/tuner.bin
python tools/uart.py ts-dma --port COMx --log logs/tuner.bin
```

`uhf-ch14-partial.json`は479143kHzのワンセグ設定、`uhf-ch14-full.json`は同channelの全帯域候補設定です。
別周波数ではRF値だけでなくPLL/FAD/NCOなどprofile全体の整合性が必要です。
受信帯域、CRC、範囲とmodeごとのDTV設定をPC側とtarget側で検査します。
`sequence-complete`は設定処理の完了であり、RF lock・TS品質を保証しません。
`tmcc`、`tuner-fec`、`tuner-quality`、`tuner-monitor`で受信状態を確認してください。

TS入力はRSPI1とDMAを使用します。`ts-dma`のloopback成功は放送TSの受信成功とは別です。
`ts-probe`やcaptureで188B同期、TEI、continuity、FIFO状態を確認します。

## Wi-Fi転送とPC受信

[open AP](wifi.md)を起動し、PCが`192.168.74.2`へ接続している状態で実行します。

```powershell
python tools/ts_receive.py --port COMx --output logs/capture.ts --log logs/stream.bin --seconds 30
```

UARTでstreamを開始・停止し、Wi-Fi UDPでTSを受信します。
TS本体と`capture.ts.json`に統計・SHA256を出力します。
datagram欠落、順序、packet index、FIFO overrun/underrun、target busy、TS同期・TEI・continuityを区別します。
受信したpacketをそのまま保存します。補完packetやサンプル映像は生成しません。

## TS転送protocol

送信先は`192.168.74.2:4202`、送信元は`192.168.74.1:4202`です。
datagramは16B headerと1〜7個の188B TS packetで構成します。

| header offset | 内容 |
| --- | --- |
| 0 | ASCII magic `TTS1` |
| 4 | datagram sequence、uint32 big endian |
| 8 | 最初のTS packet index、uint32 big endian |
| 12 | flags、uint32 big endian。bit0はFIFO再同期 |

TS payload長と同期byteを検査します。UDPのため再送や到達保証はありません。
`ts-frame-size`、`ts-burst`、`ts-aggregate`などの診断設定はAP/stream停止中に変更してください。

## TVTest

```powershell
python tools/ts_receive.py --port COMx --output logs/capture.ts --log logs/stream.bin --seconds 60 --forward-port 1234
```

TVTestのUDP入力をlocalhostの指定portへ合わせます。
PCツールはTTS1 headerを除去し、TS payloadを変更せず転送します。
対応input driver、decoder、必要な正規のCAS環境はPC側で準備してください。
本firmwareとPCツールは放送のdescramblingを実装しません。
