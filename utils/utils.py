import socket
import os
import json

def get_local_ip():
    """
    Получить локальный IP-адрес, используемый по умолчанию.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        print(f"Ошибка получения локального IP: {e}")
        return "127.0.0.1"

def convert_old_xray_log_to_json(log_path, json_path):
    """
    Конвертировать старый формат xray.out.log в JSON-формат с сохранением.
    """
    if not os.path.exists(log_path):
        print(f"Файл лога {log_path} не найден.")
        return False

    if os.path.exists(json_path):
        print(f"JSON файл уже существует: {json_path}")
        return True

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        entries = []
        for line in lines:
            entries.append({"timestamp": None, "message": line.strip()})

        with open(json_path, "w", encoding="utf-8") as f:
            for entry in entries:
                json.dump(entry, f, ensure_ascii=False)
                f.write("\n")
        print(f"Конвертация выполнена: {json_path}")
        return True
    except Exception as e:
        print(f"Ошибка конвертации лога: {e}")
        return False
