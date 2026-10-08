# image配置・SPI書込み・復旧

## 配置

| image | 用途 |
| --- | --- |
| `build/boot.bin` | 先頭8KiB内に収まるraw loader |
| `build/app.bin` | SH726A applicationのraw payload |
| `build/app.img` | 32B header付きapplication。UART・USB転送入力 |
| `build/initial-spi.bin` | 初回SPI書込み用の8,388,608B image |
| `build/*.elf`、`build/*.map` | debug・配置確認用 |

serial flash bootはSPI先頭8KiBを内蔵RAM `0xfff80000`へロードします。
初期imageは先頭にloader、SPI offset `0x10000`にapplication headerとpayloadを配置し、残りを`0xff`で埋めます。
applicationのload・entry addressは`0x1c000000`、payload上限は`0xfc000`Bです。
領域、stack、vectorは各linker scriptで定義しています。

## 初回SPI書込み

1. `make`成功後、`build/manifest.json`を開きます。
2. 元のSPI NOR内容をプログラマで読出して保管します。
3. S25FL164K系、容量8MiBに対して`build/initial-spi.bin`をoffset 0から全体書込みします。
4. 全体を読戻し、imageとbyte単位で比較します。SHA256もmanifestと一致させます。
5. プログラマを外し、通常の給電とUART接続で起動します。初回はバッテリーを接続してください。

Windowsで書込み元を確認します。

```powershell
Get-FileHash build\initial-spi.bin -Algorithm SHA256
(Get-Item build\initial-spi.bin).Length
```

SPI全体を置き換えるimageです。`app.img`や解析用ELFをSPI先頭へ書かないでください。

## application header

32B、8個のbig-endian uint32です。

| offset | 内容 |
| --- | --- |
| 0 | magic `0x5455564c` |
| 4 | version `1` |
| 8 | load address `0x1c000000` |
| 12 | payload length。`0 < length <= 0xfc000` |
| 16 | payload CRC32 |
| 20 | entry `0x1c000000` |
| 24 | reserved `0` |
| 28 | 先行28BのCRC32 |

PC側とloader側でtarget、size、CRCを検査します。CRCは破損検知であり署名認証ではありません。

## RAM実行とSPI保存

起動時はrecoveryで待ちます。SPI applicationを自動実行しません。
RAM転送、SPI読出し、実行は明示操作です。[UARTコマンド](uart.md)を使用してください。
`cycle`はRAM転送・実行だけを行います。SPI保存はrecoveryで`upload`の後に`save`を実行します。

更新はloader内で実行し、SPI先頭64KiB `[0, 0x10000)`を保護します。
4KiB消去、page program、読戻し検査を行い、application headerを最後に書きます。
単一slotなので更新中断時の旧applicationへのrollbackはありません。
更新失敗時もloaderをUART recoveryとして利用できます。

## 復旧とhandoff

applicationが応答する場合は`recover`、停止している場合はリセットでrecoveryへ戻します。
転送中断後は正常なimageを再転送してください。`resume`は同じimageの未完了・エラーなし転送だけに使えます。
SPI applicationを読めない場合もRAM転送から再実行・保存できます。
loader自体を壊した場合は外部プログラマで初期imageまたは保存済み元imageを再書込みします。

loaderとapplicationは各startupでstack・例外入口・割込み環境を設定します。
handoff中のUSB session継続は保証しません。CPUリセットやRAM切替だけではMT5931の内部状態は消えません。
