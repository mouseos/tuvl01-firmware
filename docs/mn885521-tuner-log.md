# HTV31のチューナーログ入口とIQ調査

2026-10-14、既存APK調査の未確認範囲だったDEX側のnative宣言を確認し、FsDtvAppのログ制御入口をJNIのIPC要求まで追った。TUVL01のMN885521に直接移植できる設定ではなく、同チップ搭載機のメーカーソフトにある調査候補である。IQ信号源・形式・符号・レートは未確認。実機操作・Flash変更なし、Wi-Fiチップは解析対象外。

## DEXの有限監査

```console
python tools/apk_tuner_dex_audit.py --apk-root ../work --output dex-audit.json
```

623 APK、classes.dexおよびclasses2.dex以降660エントリ、SHA256重複排除後593 DEX。DEXヘッダー・バイト順・テーブル境界・LEB128境界を確認し、class_dataのdirect/virtual method列からaccess flagのnative=0100を持つ宣言を列挙した。重複排除後のnative宣言数は25768。parseエラー0、128MiB超スキップ0。

宣言のclassまたはmethodにtuner/dtv/isdb/oneseg/fullseg/mn885/pseqがあるものだけを記録し、英数字等の識別子文字に限定する。任意のDEX文字列は出力しない。全Javaコード、呼出しグラフ、動的ロード、フィルター外の名前、JNI実装全体、他のDEX形式の監査ではない。ネイティブ宣言名にIQ取得が現れないことからチップ機能の不存在を結論しない。

最初の列挙パターンがclasses10/11.dexを除外していたことを確認し、修正後に全APKを再解析した。追加対象はFacebook_Clientの2エントリで、最終660/593の数値には含まれる。未確認範囲を隠して初回658/591を最終値にはしない。

一致したAPKはHTV31 1.08/1.11/2.44のFsDtvApp、各89宣言。DtvServerProxyが84、DtvBmlServerProxyが5。1.08/1.11のDEX SHA256は`9b90a3ccfd3a6e96117d1dddeaa33b706bf39abf36ae816b9e6d4833625f4d01`、2.44は`941c0eee259043626b17ab002b789132a97606e4b8505c3228c478c84c81871d`。

デバッグ関連の候補はDtvSvLib_SetTunerLog / DtvSvLib_GetTunerLogStatus / DtvSvLib_ControlErrBit / DtvSvLib_ControlIntLNA。最後の2つは名称だけでADC/IQ経路と解釈しない。今回はログ2関数を追った。

公開パーサーで2.44の実DEXの89宣言とログ2宣言を再取得し、独立したJNI表の名称とも照合。短すぎるDEX2ケース・異常に大きいmethod table1ケースの拒否を確認した。APKそのものや全宣言の原ログは公開しない。

## JNIからサーバーへの要求

一次資料はHTV31 2.44のsystem/lib/libDtv_jni.so、SHA256 `448a851a3353680379e256b128673190f7c54b09dfdba38dfde35b3fb3deac0b`。ARM32 ELF、ELF仮想アドレスで記載する。1.08/1.11版は別SHA256 `db6e1a7c54394928764c0e76d31b3a09e9411dda4f18e58946694bc6dda2600d`であり、以下のアドレスをそのまま適用しない。

| 宣言 | 登録表候補のアドレス | Java署名 | Thumb関数ポインタ / 命令開始 |
| --- | --- | --- | --- |
| DtvSvLib_SetTunerLog | 402F0 | (II) → BG_TE_DTVSVLIB_RESULT | C319 / C318 |
| DtvSvLib_GetTunerLogStatus | 402FC | (I) → BG_TE_DTVSVLIB_RESULT | C21D / C21C |

表のname/signature/functionの3ポインタと、実際の関数が引数をパックして返却結果を作る命令を照合した。低bit1はThumb指定。名前は公開dynsymには現れず、raw文字列とデータ表を対応付けた。.rel.dynはAPS2形式で通常のRELテーブルではないため、単純なrelocation parserで解決済みとは主張しない。

両関数はPLT6254を呼び、.rel.pltのシンボルとの照合から`android::DtvSvLibListener::sendEventToServer(int, void*, int, void*, int*)`に対応する。

| 入口 | IPC command | 送信サイズ | 命令上の根拠 |
| --- | --- | --- | --- |
| SetTunerLog | 1000001F | 4 bytes | C3D8のr1 literal、C3DAのr3=4、C3E0のcall |
| GetTunerLogStatus | 10000020 | 2 bytes | C296のr1 literal、C298のr3=2、C29Eのcall |

SetはC356〜C35Eで第2Java引数−1をunsignedで1と比較し、1/2だけを受け付ける。1=開始/2=停止という意味はまだ未確認。C35Aで第1Java引数をhalfword、C392で第2引数をbyteとして送信領域へ格納する。4バイト中の残り1バイトの意味はこの範囲では未確認。GetはC254で引数をhalfwordとして2バイトの送信領域へ格納する。引数の名称・ログ種別は推測で補完しない。

どちらもsendEventToServerの出力ポインタと出力長ポインタに0を渡す命令がある。戻り値を判定してA930の結果オブジェクト作成処理へ進み、Javaの戻り型はBG_TE_DTVSVLIB_RESULT。このJNI関数自身はI/Q配列を直接返す入口としては確認できない。サーバーの非同期処理、別のログファイルやコールバックによるデータ生成まで否定しない。

## 残る追跡

次はdtvserverの1000001F/10000020のディスパッチと処理先を追い、記録内容・下位チューナー呼出し・ログファイル／返却イベントを確認する。HTV31 2.44のdtvserver SHA256は`a31cd4ea9713e6674fb1966ace27950a3d2984f00949d1ed81d45967afeb172b`。1.08/1.11版は`015096d98fed6f27c1275e5c6f04ad5457a0abf241e5a112b64fc461e2c815cc`。同名文字列だけをIQキャプチャ機能と扱わず、実行経路から判断する。

ローカル原証跡はanalysis/firmware/iq-output-memoryのapk-tuner-dex-audit.json、dtv-tuner-log-{symbol-audit,string-audit,jni-map,jni-disassembly,jni-command}.json。逆アセンブル原文・メーカーAPK/ELFは公開しない。TUVL01の最新実機状態は[選択窓の検証記録](mn885521-d4-d5.md)に保持しており、この静的解析でTS品質やIQ取得が回復・完了したとは扱わない。

## サーバー入口から内部タスク要求まで

同じ2.44 dtvserverを読み取り専用で追跡した。SHA256は上記と同一。再現用の固定モチーフ検証を追加した。

```console
python tools/tuner_log_server_flow.py --server /path/to/htv31-2.44/dtvserver --output server-flow.json
```

ツールは正確なSHA256・ARM32 little-endian ELFを要求し、PT_LOADでファイルoffsetとVAを変換する。コマンド表候補の値と直前のThumbポインタ、9箇所の直接BL先、内部コマンドliteral、送信サイズの命令を照合する。サーバーを起動せず、完全なディスアセンブラや実行経路の網羅検証でもない。

| JNIコマンド | サーバー表候補 VA / file offset | 直前Thumb pointer / 命令開始 | 要求保存呼出し | 内部イベント候補 |
| --- | --- | --- | --- | --- |
| 1000001F | 437A58 / 436A58 | 4B259 / 4B258 | 4B28A → 610AC | 4B29Cで25、4B2A0 → 49134 |
| 10000020 | 437A74 / 436A74 | 4B309 / 4B308 | 4B33A → 6117C | 4B34Cで26、4B350 → 49134 |

表の前後はコマンド・ポインタ・状態候補の反復構造。表を読むディスパッチャーの全制御条件を解読済みとは扱わない。各入口は[r5+8]の要求領域を保存処理へ渡し、627ECの返り値から3を引いたbyteが0/1の場合にイベント処理を呼ぶ。状態値3/4の名称は不明。保存処理610ACは内部オブジェクト+46Cへ要求wordを保存、6117Cは+470へ保存する候補で、IQ列の格納とは確認できない。

| 後段の処理候補 | 呼出し先 | 組み直した内部要求 | 送信サイズ |
| --- | --- | --- | --- |
| 4B6F0（Set、4B726のcall） | 52CAC | 10030024 | 8 bytes |
| 4B774（Get、4B7AAのcall） | 52DF8 | 10030025 | 2 bytes |

Setの52CACは元message IDを1000001Fと比較（52CE8〜52CFA）。保存要求を63B94で読み戻し（52D00）、要求中byte[2]を32bitへ拡張して送信領域+4へ格納（52D04/52D10）。別のmessage halfword[r7+10]を送信領域先頭へ格納（52CEC/52CF6）。8バイト領域は事前に0で初期化され、52D0Aでサイズ8、52D0Cのliteralからコマンド10030024を渡す。halfwordの意味とモード1/2の開始・停止への対応は未確認。

Getの52DF8はmessage halfword[r5+10]を2バイト領域へ格納（52E2C〜52E34）、52E32のliteralから10030025、52E38でサイズ2。これらの送信領域は設定・要求データであり、チップのIQサンプルを運ぶバッファとして確認されたものではない。

両方とも40DD4へ進む（Set52D14/Get52E3A）。40DD4は63324で宛先関連値を得て、40CC4を経由し、40E46でPLT3DD30を呼ぶ。.rel.pltからcalleeは`DtvSvCom_SendMsg(unsigned long, unsigned long, unsigned long, unsigned long, void*, TS_DTVSV_COM_DATA*)`。同じ関数にはRecvMsgMemFreeへの呼出しもあり、メッセージを運ぶ共通経路と整合する。ここから下位チューナーのレジスタ書込みを実行したという証拠はまだない。

libDtv.soにはDTVSV_MSGID_AIR_SET_TUNER_LOG_REQ / AIR_GET_TUNER_LOG_STATUS_REQと対応するREPLYの名称がある。JNI側にも`BG_EV_DTVSV_SET_TUNER_LOG_REPLY` / `BG_EV_DTVSV_GET_TUNER_LOG_STATUS_REPLY`の非同期返却イベント名がある。名称だけで返却データの型・ログファイルの内容・IQ機能を決めない。次は10030024/25の受信側タスクのdispatcher・処理関数とログ書込み先、reply payloadを追う。

中間の文字列xref探索は候補の位置出しにだけ使用した。ARM.exidxの範囲が複数の小関数をまとめる場合があるため、unwind範囲の開始を個々の関数開始と同一視しない。文字列ロードの候補だけで関数名や完全なフローを確定しない。公開ツールは表ポインタ・直接call・literalの独立照合に限定した。

実資料で全9call先と2内部ID・送信サイズが一致し、誤ったsource hashは拒否されることを確認した。原証跡はdtv-tuner-log-server-{disassembly,send-disassembly,xrefs,flow}.jsonとdtv-tuner-log-{air-symbols,lowercase-strings}.json。原逆アセンブルはローカルだけに保持。今回の調査はログ内容を確定しておらず、IQ信号源・形式・符号・サンプルレートは未確認。実機操作・RAM再転送・Flash保存なし。

## AIR受信側の受付表と無効なログ要求

HTV31 2.44の内部要求10030024/25を受けるAIR側を静的に追跡した。結論は、この版の通常MAIN発のログ要求に対する受付フラグが全状態で0であり、同じ表の処理ポインタも0ということ。JNI/API名称が存在することだけでは、実装されたチューナーロガーやIQ取得機能の証拠にならない。MN885521自体のIQ機能の不存在は示していない。

libDtv.soのSHA256は`33a1efb1e73b981f72ee71b86798938447ff517f79d86b659acfa36f076259de`。exportされたtbl_DtvSvCom_TaskListはVA300A0、420バイト。g_DtvSvCom_TaskList_Num（30278）のuint16は15で、28バイト×15行として読む。行2は名称AIR（name pointer1E5A5）、task ID8A101003。初期探索の「15 wordごとの行」という分割は誤りで、最終解析には使用しない。

サーバーの678C8にも8A101003。6788CのCreateTaskThread呼出しに渡すcallbackは、678F0のliteralを67888のADD PC（PC6788C）に足して67A91（Thumb entry67A90）。AIR entryの67ADCは92108を反復呼出しする。92166のReceive側呼出しにもliteral92338から8A101003を渡す。92108は922D4で91A08の受付判定へ進み、受理時は922E6で91FF4へ進む。

91A08はmessage sourceと8A101003／8A101002を比較し、MAIN由来を分類1として受付表へ進める。91AC0/91AC4はcommand−10030000を計算し、91AC8で状態候補を取得。91AD2/91AD6はtable[12×command_index+state]のbyteを読み、1との一致を判定する。状態の名称は未確認。実行router91C18にも同じcommand正規化があり、状態0〜5を分岐する。

受付・処理ポインタ・次状態の3箇所から、同じGOT VA442C48、表VA445150を独立に照合した。処理呼出し側9C798は12×index+table+8からポインタを読み、9C7E0でnullを判定する。非nullのときだけ9C7E4で間接callする。91C18内のこの経路への直接callは91CF0。別分岐の全挙動まで解読済みとはしない。次状態はrecord+6のhalfwordで、FFFFと比較して更新を省く経路がある。

| 要求 | index | record VA / file offset | 先頭6受付byte | +6 halfword | +8 Thumb pointer |
| --- | --- | --- | --- | --- | --- |
| 10030024 | 24 | 445300 / 444300 | 00 00 00 00 00 00 | FFFF | 00000000 |
| 10030025 | 25 | 44530C / 44430C | 00 00 00 00 00 00 | FFFF | 00000000 |
| 隣接10030026（形式照合用） | 26 | 445318 / 444318 | 00 01 00 01 01 01 | FFFF | 000A13A9 |

AIR自身からのmessageは受付表の判定を迂回する分岐がある。したがって「全ての発信元・全ての分岐で同一のエラーを返す」とは主張しない。通常MAIN発の受付が0であることと、追跡した処理表のログ2行に関数がないことを結論とする。エラーreplyの具体的な意味・payloadと、別経路のログ内容は未確認。

### 手元の旧版との比較

1.08と1.11のdtvserverは同じSHA256 `015096d98fed6f27c1275e5c6f04ad5457a0abf241e5a112b64fc461e2c815cc`。旧版では926F4〜92706でAIR／MAINのsource IDを判定、9270E/92712で同じcommand−10030000、92720/92724で12×index+stateのbyteを読む。GOTの計算方法は異なり、GOT base4446A0＋literalFFFFE544→442BE4、参照先table445150。ログ2行の先頭6byteは全0、+6はFFFF、+8のwordは0。隣接26行の+8は000A221Dで、非zero行もある。

旧版は受付表までの比較に限定した。JNIからqueue、callback、間接handlerまでを旧版について全面的に再追跡したものではない。それでも、手元の旧版へ切り替えれば通常ログ要求を受け付けるという根拠は得られない。

### 再現と次の調査

```console
python tools/tuner_log_server_flow.py --server /path/to/2.44/dtvserver --common /path/to/2.44/libDtv.so --comparison-server /path/to/1.08/dtvserver --output air-flow.json
```

追加オプションを省略しても2.44受信側の固定モチーフを検証する。--commonはAIR名称／task IDを追加照合、--comparison-serverは旧版の受付表を照合する。正確な入力SHA256、PT_LOAD対応、命令モチーフ、7追加直接call、3独立表参照、ログ2行と非zero隣接行を検証。実資料3ファイルで成功し、各解析関数が異なるSHA256の入力を拒否することを確認した。ツールは動的検証や完全な逆アセンブラではない。

今回の原証跡はローカルdtv-air-receiver-flow.jsonとdtv-old-{normalization-candidates,air-table-candidates}.json。メーカーELF・原逆アセンブルは公開しない。実機操作・RAM転送・Flash書込みは行っていない。IQ信号源・形式・符号・サンプルレートは引き続き未確認、最新TS品質は未復帰。次はログAPIから離れ、下位チューナーの直接操作経路で出力設定／内部メモリ読出しを探す。
