TOOLCHAIN ?= $(HOME)/.cache/tuvl01-independent/gcc13/install
CC = $(TOOLCHAIN)/bin/sh-elf-gcc
OBJCOPY = sh-elf-objcopy
RADIO_FILE ?= firmware/mt5931.bin
RADIO_SHA256 ?= 06d43badbb669700c7cf94924c43a40779b428f3ceec8756813b0aaec2b4a68d
KERNEL = third_party/FreeRTOS-Kernel
CFLAGS = -m2a-nofpu -mb -Os -g -ffreestanding -fno-builtin -fno-common -ffunction-sections -fdata-sections -Wall -Wextra -Werror -Iinclude -Ibuild -Irtos/port -I$(KERNEL)/include
AUTOSERVE ?= 0
ifeq ($(AUTOSERVE),1)
CFLAGS += -DTUVL01_AUTOSERVE=1
endif
LDFLAGS = -nostdlib -Wl,--gc-sections,--build-id=none
INTEGER_RUNTIME = $(TOOLCHAIN)/lib/tuvl01/libgcc-sh2a-be.a
COMMON = src/startup.S src/board.c src/runtime.c src/usb.c
BOOT = $(COMMON) src/boot.c src/image.c src/flash.c
APP = $(COMMON) src/app.c src/cache.c src/cache_control.S src/image.c src/flash.c src/sdio.c src/wifi_board.c src/wifi_mgmt.c src/wifi_hif.c src/wifi_net.c src/wifi_tx_feedback.c src/wifi_statistics.c src/tuner.c src/tuner_ts.c src/ts_protocol.c src/ts_check.c src/tuner_profile.c src/tuner_profile_protocol.c src/tuner_monitor.c src/tuner_monitor_protocol.c src/tuner_tmcc.c src/tuner_tmcc_protocol.c src/radio.S rtos/port/port.c rtos/port/portasm.S $(KERNEL)/tasks.c $(KERNEL)/list.c
APP += src/wifi_link.c
APP += src/wifi_ts_tx.c
APP += src/wifi_ctl.c
APP += src/tuner_uhf.c src/tuner_uhf_table.c src/tuner_serve.c src/loader_update.c src/loader_update_cmd.c src/board_led.c src/board_led_cmd.c
APP += src/wifi_status.c
APP += src/sdio_irq.c
APP += src/wifi_queue.c
APP += src/ts_pattern.c
APP += src/wifi_fw_query.c
APP += src/wifi_tx_timing.c
APP += src/wifi_rates.c
APP += src/wifi_rx_sink.c
APP += src/wifi_ht.c
APP += src/wifi_io_timing.c
APP += src/time_counts.c
APP += src/wifi_service_timing.c
APP += src/wifi_raw_tx.c
APP += src/wifi_fixed_rate.c
APP += src/wifi_channel.c
APP += src/wifi_power_events.c
APP += src/wifi_ais_mgmt.c
APP += src/wifi_station.c src/wifi_ais_bss.c
APP += src/wifi_ais_beacon.c
APP += src/wifi_scan.c
APP += src/wifi_scan_cache.c
APP += src/wifi_ais_rsn.c
APP += src/wifi_ais_join.c
APP += src/ts_benchmark_protocol.c
APP += src/tuner_quality_watch.c
APP += src/tuner_program_probe.c
APP += src/wifi_tx_power.c
HEADERS = $(wildcard include/*.h rtos/port/*.h $(KERNEL)/include/*.h)
WPA_INPUTS = $(shell python3 tools/wpa_build.py --inputs)
.PHONY: all clean wifi-app FORCE
FORCE:
build/radio-config.h: FORCE tools/verify_radio.py $(RADIO_FILE)
	python3 tools/verify_radio.py --radio "$(RADIO_FILE)" --sha256 "$(RADIO_SHA256)"
.DEFAULT_GOAL := all
all: build/app.bin build/boot.bin build/initial-spi.bin build/app.img
build/boot.elf: $(BOOT) linker/boot.ld $(HEADERS)
	mkdir -p build
	$(CC) $(CFLAGS) $(LDFLAGS) -T linker/boot.ld -Wl,-Map,build/boot.map $(BOOT) -o $@
build/boot.bin: build/boot.elf
	$(OBJCOPY) -O binary $< $@
build/initial-spi.bin build/app.img &: build/boot.bin build/app.bin tools/images.py
	python3 tools/images.py
build/tuner_pseq.h: firmware/mn885521-pseq.bin firmware/mn885521-pseq.json tools/pseq.py
	mkdir -p build
	python3 tools/pseq.py
$(INTEGER_RUNTIME): tools/runtime_libgcc.py
	TUVL_TOOLCHAIN_DIR=$(abspath $(TOOLCHAIN)/..) python3 tools/runtime_libgcc.py
build/wpa/rsn-core.o: $(WPA_INPUTS) tools/wpa_build.py
	python3 tools/wpa_build.py --cc $(CC)
# Changing AUTOSERVE must rebuild the application: record the value and depend on it.
build/autoserve.flag: FORCE
	mkdir -p build
	@echo $(AUTOSERVE) | cmp -s - $@ || echo $(AUTOSERVE) > $@
build/app.elf: $(APP) linker/app.ld $(HEADERS) build/radio-config.h build/tuner_pseq.h $(INTEGER_RUNTIME) build/wpa/rsn-core.o build/autoserve.flag
	mkdir -p build
	$(CC) $(CFLAGS) $(LDFLAGS) -T linker/app.ld -Wl,-Map,build/app.map $(APP) build/wpa/rsn-core.o $(INTEGER_RUNTIME) -o $@
build/app.bin: build/app.elf
	$(OBJCOPY) --gap-fill 0xff -O binary $< $@
wifi-app: build/app.img
	cp build/app.img build/wifi-app.img
clean:
	rm -f build/*.elf build/*.bin build/*.map build/*.json
