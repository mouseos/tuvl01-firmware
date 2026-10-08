# ライセンスと依存関係

| 対象 | ライセンス・固定版 |
| --- | --- |
| 独立MCU実装とPCツール | MIT。rootのLICENSE |
| FreeRTOS Kernel | V11.1.0、MIT。submodule commit `dbf70559b27d39c1fdb68dfb9a32140b6a6777a0` |
| wpa_supplicant RSN部分 | 2.12、BSD-3-Clause。`third_party/wpa_supplicant/COPYING` |
| nanoprintf | commit `bebaecbeaf430e36a2d30d31a2fed4e098388c93`、同梱dual licenseから0BSDを選択 |
| GCC 13.3.0 | GPL等。整数runtimeはGCC Runtime Library Exceptionの適用条件に従う |
| GNU binutils | GPL。host側のビルドツール |
| pyserial 3.5、PyUSB 1.3.1 | BSD-3-Clause。PC側のみ |
| libusb-package 1.0.26.4 | packagingはApache-2.0、libusbはLGPL-2.1-or-later。PC側のみ |
| MT5931・MN885521データ | メーカーbinary。MIT適用外。[NOTICE](../firmware/NOTICE.md) |

依存ソースのcopyrightとlicenseを保持します。
wpa_supplicantとnanoprintfの各manifestにsource URLとfile hashを記載します。
GCC archiveのSHA256は`0845e9621c9543a13f484e94584a49ffc0129970e9914624235fc1d061a0c083`です。
SH726A用純正実行コードとHI7000/4は含めません。

一次資料:

- [FreeRTOS Kernel](https://github.com/FreeRTOS/FreeRTOS-Kernel/tree/V11.1.0)
- [GCC 13.3.0](https://ftp.gnu.org/gnu/gcc/gcc-13.3.0/)
- [GCC Runtime Library Exception](https://www.gnu.org/licenses/gcc-exception-3.1.html)
- [wpa_supplicant](https://w1.fi/wpa_supplicant/)
- [nanoprintf](https://github.com/charlesnicholson/nanoprintf)
- [pyserial](https://github.com/pyserial/pyserial)、[PyUSB](https://github.com/pyusb/pyusb)
- [libusb-package](https://github.com/pyocd/libusb-package)、[libusb](https://github.com/libusb/libusb)
