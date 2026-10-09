# UHF受信・TS転送

MN885521の基板初期化、I2C制御、PSEQ転送、周波数設定、TMCC・品質読出し、TS取得を実装します。
PSEQは同梱binaryを使用します。[同梱データ](../firmware/NOTICE.md)を参照してください。
ワンセグを主用途とし、フルセグ用設定は実験用です。フルセグの連続受信・Wi-Fi転送を保証しません。

## 初期化・選局

選局済みUHFのpartial/fullは、`tuner-switch`で同じRF設定のまま切り替えられます。
Wi-Fi通信・TS転送を停止して実行してください。対象外モード・未校正・通信中は拒否します。
設定を読み戻し、IRQマスクを復元します。失敗時は元のモードへの復帰を試みます。
`switched`は設定変更の確認であり、放送ロックや正常なTSを保証しません。

```powershell
python tools/uart.py tuner-switch --port COMx --log <external-log-path>
```

application実行後にUARTポートを指定します。

```powershell
python tools/uart.py tuner-init --port COMx --log logs/tuner.bin
python tools/tune.py --port COMx --profile profiles/uhf-ch14-partial.json --log logs/tuner.bin
python tools/uart.py tmcc --port COMx --log logs/tuner.bin
python tools/uart.py ts-output --port COMx --log logs/tuner.bin
python tools/uart.py ts-dma --port COMx --log logs/tuner.bin
```

`uhf-ch14-partial.json`は479143kHzのワンセグ設定、`uhf-ch14-full.json`は同channelの全帯域候補設定です。
`uhf-ch19-full.json`は509143kHzの全帯域候補設定です。受信地域に合うprofileを選択します。

```powershell
python tools/tune.py --port COMx --profile profiles/uhf-ch19-full.json --log logs/full-ts.bin
```
別周波数ではRF値だけでなくPLL/FAD/NCOなどprofile全体の整合性が必要です。
受信帯域、CRC、範囲とmodeごとのDTV設定をPC側とtarget側で検査します。
`sequence-complete`は設定処理の完了であり、RF lock・TS品質を保証しません。
`tmcc`、`tuner-fec`、`tuner-quality`、`tuner-monitor`で受信状態を確認してください。
`tuner-fec`はFEC状態に加え、bank `0x61` の `0xA1` とbank `0x60` の
`0xD6`～`0xD8`を読出しのみで表示します。表示は生値で、dB・dBmへの換算は行いません。

TS入力はRSPI1とDMAを使用します。`ts-dma`のloopback成功は放送TSの受信成功とは別です。
`ts-probe`やcaptureで188B同期、TEI、continuity、FIFO状態を確認します。

## フルセグ用のTS取得設定

全帯域profileでは、初期化・選局・TS出力設定後に次の操作を実行します。
新しいRAM applicationの起動直後を前提にしています。

```powershell
python tools/uart.py ts-dma --port COMx --log logs/full-ts.bin
python tools/uart.py ts-clock-max --port COMx --log logs/full-ts.bin
python tools/uart.py ts-dma-long --port COMx --log logs/full-ts.bin
python tools/uart.py icache --port COMx --log logs/full-ts.bin
python tools/uart.py ts-benchmark --port COMx --log logs/full-ts.bin
python tools/uart.py tmcc --port COMx --log logs/full-ts.bin
```

`ts-clock-max`はRSPI1のSPBRを0へ設定し、loopbackで検査します。
`ts-dma-long`はlongword DMAの選択を切り替えるため、繰り返すと無効になります。
`TS DMA long selected=00000001`を確認してください。
`icache`も有効・無効を切り替えます。新規RAM起動後に1回実行し、
`ICACHE CCR1 ... after=00000100`でinstruction cacheの有効化を確認してください。
benchmarkは10秒間の取得packet数、FIFO状態、同期・TEI・adaptation・continuityを表示します。
`measured`は測定完了を表します。各エラーが0で、TMCCがstable frame lockであることを確認します。
単独取得のbenchmarkはWi-Fi同時負荷やPCへの到達を検証しません。
AP/stream停止中に設定を変更してください。RAMを再起動した場合は設定をやり直します。

測定時間を1〜300秒で指定できます。省略時は従来の10秒commandを使用します。

```powershell
python tools/uart.py ts-benchmark --benchmark-seconds 60 --port COMx --log logs/full-ts.bin
```

指定時間の1つのwindow内でTSのcontinuity状態を保持し、FIFO再同期時のエラーも数えます。
設定packetは`TSB1`、seconds uint32 big endian、先行8BのCRC32の計12Bです。
新しいcommandはbyte `0x05`で開始し、12Bの受信には3秒の期限があります。
このcommandに対応したfirmwareが必要です。測定中は他のUART/USB command処理を待たせるため、
PCツールは測定時間に合わせて応答を待ちます。途中の復旧が必要ならCPUをリセットしてください。

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
