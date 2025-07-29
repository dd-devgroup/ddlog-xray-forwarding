#!/bin/bash
set -e

TMP_DIR="/tmp/dd-log_$$"
mkdir -p "$TMP_DIR"

echo "📦 Загрузка..."
curl -sSL https://github.com/dd-devgroup/ddlog-xray-forwarding/releases/download/v1.0/ddlog-xray-forwarding.bin -o "$TMP_DIR/dd-log_xray_forwarding.bin"

echo "📂 Распаковка..."
tar -xf "$TMP_DIR/dd-log_xray_forwarding.bin" -C "$TMP_DIR"

echo "🐍 Установка зависимостей..."
python3 -m pip install --upgrade pip
python3 -m pip install -r "$TMP_DIR/dd-log_xray_forwarding/requirements.txt"

echo "🚀 Запуск..."
python3 "$TMP_DIR/dd-log_xray_forwarding/setup_logs.py"

rm -rf "$TMP_DIR"
