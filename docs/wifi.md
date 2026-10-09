# Wi-Fi

## 対応範囲

MT5931をSDIO経由で操作し、同梱radio firmwareをロードします。
open APは単一peer、DHCP、ARP、ICMP echo、UDP echo、TS送信に対応します。
AP側IPは`192.168.74.1`、PCへ割り当てるIPは`192.168.74.2`です。
APに接続するPCを通常のinfrastructure clientとして登録します。Wi-Fi Directのgroup clientには対応しません。
WPA2 stationでの保護されたIP通信は未対応です。

## open AP起動

application実行後に同じUARTポートへ順に実行します。`COMx`は実際のポートへ変更してください。

```powershell
python tools/uart.py wifi --port COMx --log logs/wifi.bin
python tools/uart.py wifi-clock --port COMx --log logs/wifi.bin
python tools/uart.py mac --port COMx --log logs/wifi.bin
python tools/uart.py capability --port COMx --log logs/wifi.bin
python tools/uart.py board --port COMx --log logs/wifi.bin
python tools/uart.py ap --port COMx --log logs/wifi.bin
```

PCのWi-Fi選択から起動したopen APへ接続します。識別情報はUART出力で確認してください。
終了は`python tools/uart.py apstop --port COMx --log logs/wifi.bin`です。
AP・stream停止後にchannelやrateなどの設定を変更します。

`tools/wifi_connect.py`はWindowsで一時接続、DHCP・ping・UDP確認、TS受信、元profileへの復帰を行います。
`--interface`と`--restore-profile`を指定し、詳細は`--help`を参照してください。
既存profileの秘密情報をexportしません。

## radio状態と制限

CPUリセットやloaderへの復帰だけでMT5931が初期状態へ戻るとは限りません。
fresh loadは全136576B転送、download OK、WLAN_READY、driver ownershipを検査します。
already-ready状態は完全reload成功と同一ではありません。
`wifi-restart`はCHIP_RSTとreloadの診断操作です。すべての停止状態からの回復は保証しません。

SDIO command・RX/TX処理はtimeoutとcredit管理を使用します。
radio停止時は未完了commandを繰り返さず、AP/streamを停止して状態を確認してください。
フルセグ転送速度はチューナー取得、SDIO、radio TX、PC受信に依存し、保証値はありません。

## RSN実験機能

wpa_supplicant 2.12のRSN部分をソースからビルドします。
揮発性UART資格情報入力、EAPOL、MT5931鍵コマンド、AIS association試行の接続層を実装しています。
protectionと非zero RSCは未実装です。WPA2/IP接続が成立する機能として使用しないでください。

```powershell
python tools/wpa_uart.py --port COMx --ssid AP_NAME --bssid 02:11:22:33:44:55 --channel 6
python tools/wpa_uart.py --port COMx --join-trial
python tools/wpa_uart.py --port COMx --close
```

BSSIDとchannelは実際のAPを指定します。passwordは対話入力です。
PCでPBKDF2-SHA1によりPMKを作り、OSのentropyを利用します。
資格情報はSPI・通常logへ保存しません。protocol versionは1、targetは7B、credential packetは148Bです。
`--resync`でUART資格情報protocolを同期できます。

radioへの鍵削除転送だけでは削除ACKを確認したことにはなりません。
cleanup未解決の場合はfailure latchで再試行を拒否します。
`--join-trial`は試行後にsessionをcloseし、保護されたdata通信へ移行しません。

## 診断インターフェース

HTを有効にしてAP・転送を停止した状態で、`wifi-tx-ampdu`（UART byte `0x11`）は
送信AMPDUのenableを0/1で切り替えます。初期値は0です。
`python tools/uart.py wifi-tx-ampdu --port COM3 --log <log-path>`で操作します。
CID `0x23`の転送結果とenableを記録し、次のAP起動でも選択値を送ります。
`transferred`は命令転送のみを示し、実際のaggregationはreadbackできません。
受信ADDBAの拒否は維持します。HTを無効にする前にAMPDUを0へ戻してください。

TS転送停止時の`TS input`は、SPI/DMAで取得したbatchをWi-Fi転送前に一度だけ検査した
packet数、sync、TEI、adaptation、CCの集計です。取得中はこの検査からUARTを出しません。
PCの`ts_receive.py`は対応するJSONへ`target_input`を保存します。
停止時に未送信のbatchがあるため、入力packet数とPC受信packet数は一致するとは限りません。
CCはFIFO再同期でも飛びます。TEIはpacket headerのflagで、payloadの完全性検査ではありません。
`source=0`が実受信です。固定dummyなどTS以外の診断sourceではsync errorが出ます。

UART byte `0x0f`は、AP・STA・TS転送を停止し、送信creditがすべて戻った状態で
2.4GHz送信出力の相対補正を−6dB、−12dB、0dBの順に送ります。
CID `0x38`の32-byte bodyを使い、絶対出力の基板用テーブルは変更しません。
`reduction_half_db`は補正量の絶対値で、12は−6dB、24は−12dB、0は相対補正解除です。
`transferred`は命令転送のみを示し、実際のRF出力はreadbackできません。
起動時には自動送信しません。RAM applicationを再実行してもモジュール側の補正が
残る可能性があるため、解除時は0への転送をログで確認してください。
PCからは`python tools/uart.py wifi-tx-power --port COM3 --log <log-path>`で
一段ずつ切り替えます。指定したログで補正量と転送結果を確認してください。

チューナー・TS処理を使わない片方向UDP速度試験は、AP起動後に実行します。
送信試験は1,332バイトの既知パターンを10秒送り、PCで内容と欠落を検査します。
受信試験はPCから指定した速度で送り、application側の到達数を検査します。
両ツールは一時接続後、指定した既存Wi-Fi profileへ戻ります。

```powershell
python tools/wifi_tx_test.py --interface "Wi-Fi" --restore-profile EXISTING_PROFILE --uart-port COMx --output logs/wifi-tx.json
python tools/wifi_rx_test.py --interface "Wi-Fi" --restore-profile EXISTING_PROFILE --uart-port COMx --mbps 5 --seconds 10 --output logs/wifi-rx.json
```

送信側の完了数とPC到達数は別です。往復echoの速度も片方向帯域とは区別してください。
TX試験のUARTログには`WIFI TX bench timing`を出力します。
`kind=0`はSDIO書込み、`kind=1`は同時送信1件での書込み開始からクレジット返却までの時間です。
単位はtimer countで、`counts_per_tick`は1msあたりのcountです。
返却時間は書込み時間を含み、PCの受信時刻とは異なります。
別のTC1通信が混ざった試料は`credit_excluded`、終了時に返却未観測の試料は`credit_pending`へ示します。
複数件送信では`kind=1`を記録しません。`overflow`が非ゼロの統計は平均値に使わないでください。

`tools/uart.py --help`に全commandを列挙しています。
通常の省電力通知は`wifi-stats`の`WIFI power`に集計します。
通知ごとのUART出力は`wifi-verbose`で切り替えます。詳細出力は転送速度に影響します。
不正形式や別network/stationの省電力通知は通常モードでも出力します。

`wifi-stats`、`wifi-nic-stats`、`wifi-station-stats`、`wifi-link`は状態確認、
`scan`は受信scan、`wifi-rx-*`は受信診断です。
rate・HT・channel・queue・TX window・polling関連commandは実験用設定です。
運用条件を満たさない変更はtarget側で拒否します。設定選択の成功は通信成功や速度向上を保証しません。

[発振器の待ち時間設定](wifi-osc.md)は、AP停止中に明示的に送る診断commandです。


### 確認済みクレジットの再利用

AP停止中に`wifi-poll-reuse`を切り替え、`selected=00000001`を確認すると、
同じservice loopで確認した空きクレジットを単一・集約送信の双方で再利用します。
残数が0なら返却を読み直し、各HIF frameにつき1枠を予約します。既定は無効です。
`wifi-stats`の`reused`は再利用した回数で、PCへの到達数とは異なります。
TS開始ログの`aggregate`と`burst`で実際の送信設定を確認してください。

### TS送信中のタスク待機

`ts-pipeline`は、2つの32packetバッファで次のDMA取得と現在のWi-Fi送信を
重ねる実験用設定です。既定は無効です。TS停止中に長word DMAのループバックを
検証し、operand cacheを無効にしてから選択します。

```sh
python tools/uart.py ts-dma-long --port COMx --log <external-log-path>
python tools/uart.py ts-pipeline --port COMx --log <external-log-path>
```

DMAが完了したバッファだけを送信へ渡し、credit待ちで未送信データを上書きしません。
停止・エラー・UART recoveryではDMA要求を先に解除し、channel・routing・RSPI幅を戻します。
`TS pipeline reads`は完了した取得数、`elapsed_ticks`は取得開始から完了確認までの
累計時間です。Wi-Fi処理と重なるため、CPU占有時間ではありません。
通常の疑似TS設定ではDMAを使用しません。

`ts-dma-source`は、pipeline有効・長word DMA検証済み・operand cache無効の状態で
受信不要のRSPI内部ループバックを選択します（`test_source=00000002`）。
反転した既知TSパターンをDMA送信し、内部反転ループバックで戻った全byteを
送信前に照合します。異なるbyteがあれば送信せず停止します。
`TS DMA pattern checks/errors/first_offset`は取得バッファの照合結果です。
停止時にはループバックを解除します。もう一度選択すると実受信へ戻ります。

```sh
python tools/uart.py ts-dma-source --port COMx --log <external-log-path>
```

`ts-dma-fixed`は同じguardで固定アドレスのゼロwordをDMA送信し、内部ループバックで
得た全byteが`0xff`か照合します（`test_source=00000003`）。実受信のdummy TX DMAと
同じ非増分設定です。再選択で実受信へ戻ります。PC側は次で照合します。

```sh
python tools/uart.py ts-dma-fixed --port COMx --log <external-log-path>
python tools/ts_pattern_verify.py <capture.ts> --fixed-dummy
```

内部ループバック診断やSPI分周のprobeから実受信へ戻るときは、
`tuner-init`と選局を再実行し、`tmcc`のframe lockと`ts-output`の正常なFIFO応答を
確認してください。SoCのloopback解除・DMA解放だけでは外部チューナーの状態復旧を
保証しません。probeはチューナー初期化より先に実行します。

```sh
python tools/uart.py tuner-init --port COMx --log <external-log-path>
python tools/tune.py --port COMx --profile profiles/uhf-ch19-full.json --log <external-log-path>
python tools/uart.py tmcc --port COMx --log <external-log-path>
python tools/uart.py ts-output --port COMx --log <external-log-path>
```

この固定データはTS形式ではありません。通常のTS検査で出るsyncエラーは期待されるため、
固定データの全byte照合・UDP sequence/index・到達数で転送の正否を判断します。

PCに保存したTSは`python tools/ts_pattern_verify.py <capture.ts>`で
全byteとバッチ順を検査できます。受信機能・番組・映像の検証にはなりません。

`ts-burst`が有効な場合、送信が進んだ後は次のservice passを続けます。
各passでUSB・UART・radioを処理し、4ms経過またはcredit待ち・データなし・
エラーで進まなくなった場合に1tick待機して他のRTOS taskへ実行機会を渡します。
期限はpass間で確認し、実行中の転送には個別のtimeoutが適用されます。
通常の単発送信では従来どおり毎pass待機します。

### TS送信の完了通知

`wifi-ts-feedback`で16datagramごとのTX完了通知要求を切り替えます。
単一フレームとaggregateの双方に対応し、通常は無効です。

```sh
python tools/uart.py wifi-ts-feedback --port COMx --log <external-log-path>
python tools/uart.py wifi-stats --port COMx --log <external-log-path>
```

`requested`は要求数、`completed`は受信した通知数、`pending`は未通知数です。
radio firmwareがdataの通知を返さない場合もあり、通知なしを送信失敗と
断定しないでください。credit返却は無線送信やPC受信の成功を示しません。
aggregateのサンプル枠が満杯でもTS送信は継続します。

The direct UDP test accepts `--payload-bytes` with 64, 256, 512, 1024, 1332 (default), or 1472 bytes. UART byte 0x07 cycles these sizes while the sender, receive sink, and TS stream are stopped. The PC tool selects and verifies the requested size before starting. Each SDIO write remains 1536 bytes to compare wireless payload lengths with the same host transfer size. Payload size includes the 12-byte sequence header.

Use `--burst 1` (default), `4`, or `8` to limit direct UDP packets submitted per service pass. UART byte 0x08 cycles this limit. Each pass returns after no progress or four elapsed RTOS ticks; an in-progress SDIO transfer retains its existing timeout. Each packet reserves one validated credit, and uncertain writes stop the sender without a refund or retry. These passes send individual SDIO transactions. The PC receiver requests a 1MiB socket buffer and records the buffer size granted by the OS.

### 送信中の受信品質の有限観測

`quality-watch`でread-onlyサンプラを開始します。UART表示を止め、service passごとに
RIICで1レジスタだけを読み（個々のtransactionは既存のRTOS待機を含む）、1秒以上の間隔で最大16組・30秒以内に終了します。
`quality-watch-dump`は転送を止めて記録を表示します。正常時はサンプラからUARTを表示しませんが、RIIC失敗時は既存のfailure診断が出ます。
測定開始は転送を止めません。
`wifi_connect.py --quality-watch --ts-output ...`では転送直前に開始し、停止後に
`quality_watch_raw`としてPC統計へ保存します。疑似データ転送にも使えます。

raw配列はbank61の95,97,86,87,89,BF,C0,C1,8B,8E,90,91,92,93,C3,C4,C5,C6,C7,C8です。
again配列は97,BF,C0,C1,C3,C4,C5,C6,C7,C8の再読出しです。
changedはraw配列の対応bit、failed_readは1から始まる読出し番号（0は成功）です。
activeのbit0/bit1は取得開始/終了時のTS送信状態、tx_before/afterは送信packet数です。
各読出しは既存RIIC timeoutを使い、io_ticksはその占有時間の合計です。
観測は送信へ負荷を加えるため、実測速度も同時に確認してください。
設定・resetを書かないため、カウンタの選択条件はrawに記録した現状のままです。
再読出し一致は原子的なラッチの証拠ではなく、未検証のBER比率やdBへ変換しません。
