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

有限UART captureは、取得を終えてから最大128パケットをPCへ送ります。
`--polling`はDMAを使わず同じSPI clockで取得し、終了後に元のDMA設定を戻します。
このoptionにはUART command `0x17`に対応したfirmwareが必要です。
連続受信や転送速度の測定には使用しません。

```powershell
python tools/ts_capture.py --port COMx --log logs/capture.bin --output logs/capture.ts --polling
```

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

## TVTest（専用BonDriver）

`client/bondriver/build.ps1`で`BonDriver_TUVL01.dll`（x64）をビルドし、TVTestのディレクトリへ置きます。
装置を`tools/serve.ps1`で起動し、PCのWi-Fiを`TUVL01`へ接続してから、次のように起動します。
開始・停止は[Wi-Fiプロトコル](protocol.md)でBonDriverが行うため、UARTもPC側の中継ツールも不要です。

```powershell
.\TVTest.exe /d BonDriver_TUVL01.dll
```

PCのファイアウォールでTVTest.exeの受信（UDP 4202）が許可されている必要があります。
クライアント部分（`client/tuvl01_*`）は標準Cで、他の前端（スマートフォン等）でも再利用できます。
ファームウェアは特定のプレーヤーに依存しません。

## TVTest（UDP入力ドライバー経由）

TVTestのディレクトリでUDP入力ドライバーと受信ポートを指定して起動します。

```powershell
.\TVTest.exe /d BonDriver_UDP.dll /port 1234
```

[/d・/portの仕様](https://github.com/DBCTRADO/TVTest/blob/develop/doc/TVTest.txt)はTVTestの説明を参照してください。
次にファームウェアのリポジトリでPC受信ツールを実行します。

```powershell
python tools/ts_receive.py --port COMx --output logs/capture.ts --log logs/stream.bin --seconds 60 --forward-port 1234
```

`/port`と`--forward-port`には同じ番号を指定します。
PCツールはTTS1 headerを除去し、TS payloadを変更せず転送します。
対応input driver、decoder、必要な正規のCAS環境はPC側で準備してください。
本firmwareとPCツールは放送のdescramblingを実装しません。

## Wi-Fi停止中の品質測定

Wi-Fiを初期化し通信を停止した状態で、`wifi-quiet-quality`を実行できます。
NICへ電源モード1を指示し、最大5秒でWLAN_READYの消失を確認します。
firmwareへ所有権を渡して受信品質を測定した後、radioのリセットとfirmwareの再ロードを試みます。
停止後の復帰に失敗する場合があります。`restart-failed`ではWi-Fiを使用できず、完全な電源入れ直しが必要です。
古いMAC・基板設定・HIFクレジットは無効になるため、続けてWi-Fiを使う前に`mac`を実行してください。
この診断はプロトコル上の停止を確認します。クロックや電源の実測は行いません。

## 受信感度と診断コマンド

初期化直後は、bank `0x62` のregister `0xE8` が `0x0f` です。この値では、RSSI生値とCNが約20dB悪化することを実測しました。
`0xE8` が `0`〜`2` のとき感度は正常です。選局時に `2` を書き、TS出力設定と同じ値を先に選択します。

`tuner-reg`は、`0x60`〜`0x62` bankのregisterを1つずつ読み書きする診断です。
書込みは `0xF0` 未満に限り、書込み後に読み戻します。意味が確認できないregisterを書き換えると、受信が止まることがあります。

```powershell
python tools/uart.py tuner-reg --reg 62:e8 --port COMx --log <external-log-path>
python tools/uart.py tuner-reg --reg 62:e8=02 --port COMx --log <external-log-path>
```

`rf-switch`は、`PB14`と`PB15`の出力状態を読み、許可した状態へ切り替えます。
`stock`は純正の初期化と同じ`PB14=1`・`PB15=0`、`alt`は`PB15`だけを上げた状態です。
`inverse`は`PB14=0`・`PB15=1`で、チューナーがI2Cに応答しなくなります。復旧には`tuner-init`が必要です。
実測では、`alt`にしてもRSSI・CN・PERは変わりませんでした。RFスイッチの制御端子としては確認できていません。

`gpio-dump`は`0xFFFE3800`〜`0xFFFE38FF`のport・ピン機能レジスタを読むだけです。
`gpio-drive`は指定した1本のGPIOを、現在の読出し値の反対レベルへ一時的に出力し、`gpio-release`で元へ戻します。
出力を有効にする前に現在と同じレベルを設定し、反転後に読み戻して、他の素子と競合していれば即座に復元します。
チューナー用の`PB14`・`PB15`・`PB16`・`PD1`は拒否します。`PB18`を反転するとMCUが再起動しました。
他のピンも、電源・リセット・LEDなどの基板機能を変える可能性があります。ポート全体の走査は用途のわかる範囲で行ってください。

```powershell
python tools/uart.py gpio-dump --port COMx --log <external-log-path>
python tools/uart.py gpio-drive --gpio B13 --port COMx --log <external-log-path>
python tools/uart.py gpio-release --port COMx --log <external-log-path>
```

## 実機で確認した範囲

次の範囲を、RAM実行のbuildで確認しています。受信地域・アンテナ・時間帯で結果は変わります。

- ワンセグ（UHF partial設定）: TS取得、open APへのWi-Fi接続、DHCP、ping、UDP、25秒単位のTS転送を繰り返し、
  データグラム欠落・TSの同期／TEI／adaptation／CCエラーが0であることを確認しました。
- 受信TSをffmpegでデコードして映像と音声を取り出せること、`tools/wifi_connect.py`の`--ts-forward-port`と
  TVTestの`BonDriver_UDP`で表示できることを確認しました。放送がスクランブルされている場合のCAS環境は別途必要です。
- フルセグ（13seg）: 選局・TMCC同期は成立しますが、受信できた全局でLayer-B（64QAM）のPERがほぼ100%でした。
  CNの値は未較正で、dB換算はしていません。アンテナ・受信位置を含め、原因は未確定です。
- 約280秒の連続転送では、Wi-Fi区間のデータグラム欠落は0でした。チューナー入力側のTEIは約0.4%あり、電波側の受信エラーです。
  数十分以上の連続動作、音声の聴取は確認していません。
- USB列挙、WPA2通信、SPIへ書込んだimageからの起動は確認していません。
