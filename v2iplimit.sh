#!/bin/bash
set -e

TMP_DIR="/tmp/dd-log_$$"
mkdir -p "$TMP_DIR"

echo "📦 Загрузка..."
curl -sSL https://github.com/dd-devgroup/ddlog-xray-forwarding/releases/download/v1.0/ddlog-xray-forwarding.bin -o "$TMP_DIR/ddlog-xray-forwarding.bin"

chmod +x "$TMP_DIR/ddlog-xray-forwarding.bin"

echo "🚀 Запуск..."
"$TMP_DIR/ddlog-xray-forwarding.bin"

# Опционально удалим после запуска
rm -rf "$TMP_DIR"
