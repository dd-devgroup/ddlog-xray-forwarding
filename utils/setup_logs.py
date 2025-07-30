import subprocess
import getpass
import paramiko
import threading
import os
import json
import socket

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip
    
NODES_FILE = "nodes.json"

CENTRAL_HOST = get_local_ip()
CENTRAL_PORT = 514

CONF_TEMPLATE = """
module(load="imfile")

input(type="imfile"
      File="/var/log/supervisor/xray.out.log"
      Tag="xray-{node}"
      Severity="info"
      Facility="local7"
      PersistStateInterval="200"
      PollingInterval="1")

*.* @@{central_host}:{central_port}
"""


def load_nodes():
    if os.path.exists(NODES_FILE):
        with open(NODES_FILE) as f:
            return json.load(f)
    return []

def save_nodes(nodes):
    with open(NODES_FILE, "w") as f:
        json.dump(nodes, f, indent=2)

def ssh_connect(host, user, port, use_key, key_path=None, password=None):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        if use_key:
            ssh.connect(hostname=host, port=port, username=user, key_filename=key_path, timeout=10)
        else:
            ssh.connect(hostname=host, port=port, username=user, password=password, timeout=10)
        return ssh
    except Exception as e:
        print(f"❌ Ошибка подключения к {host}: {e}")
        return None

def stream_logs_and_save(log_stream, filename):
    with open(filename, "a", encoding="utf-8") as logfile:
        try:
            for line in iter(log_stream.readline, ""):
                print(f"[{filename}] {line}", end="") 
                logfile.write(line)
                logfile.flush()
        except Exception as e:
            print(f"Ошибка в потоке логов {filename}: {e}")

def start_local_log_thread():
    proc = subprocess.Popen(
        ["docker", "exec", "remnanode", "tail", "-n", "+1", "-f", "/var/log/supervisor/xray.out.log"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    filename = "logs_xray_local.log"
    t = threading.Thread(target=stream_logs_and_save, args=(proc.stdout, filename), daemon=True)
    t.start()
    print("✅ Запущен фоновый поток локальных логов")

def start_ssh_log_thread(ssh, node_name):
    stdin, stdout, stderr = ssh.exec_command("tail -n +1 -f /var/log/supervisor/xray.out.log")
    filename = f"logs_xray_{node_name}.log"
    t = threading.Thread(target=stream_logs_and_save, args=(stdout, filename), daemon=True)
    t.start()
    print(f"✅ Запущен фоновый поток логов для ноды {node_name}")

def add_remote_node():
    host = input("IP ноды: ").strip()
    name = input("Название (уникальное): ").strip()
    user = input("SSH пользователь (по умолчанию root): ").strip() or "root"
    port_input = input("SSH порт (по умолчанию 22): ").strip()
    port = int(port_input) if port_input else 22

    auth_method = input("Аутентификация (1 - ключ, 2 - пароль): ").strip()
    use_key = auth_method == "1"

    if use_key:
        key_path = input("Путь к SSH-ключу (по умолчанию ~/.ssh/id_rsa): ").strip()
        if not key_path:
            key_path = os.path.expanduser("~/.ssh/id_rsa")
        password = None
    else:
        key_path = None
        password = getpass.getpass("Введите SSH пароль: ")

    ssh = ssh_connect(host, user, port, use_key, key_path, password)
    if not ssh:
        print("Не удалось подключиться. Попробуйте снова.")
        return

    try:
        print("Установка rsyslog и настройка конфигурации...")
        ssh.exec_command("apt update && apt install -y rsyslog")

        conf = CONF_TEMPLATE.format(node=name, central_host=CENTRAL_HOST, central_port=CENTRAL_PORT)
        remote_path = f"/etc/rsyslog.d/30-xray-{name}.conf"

        sftp = ssh.open_sftp()
        with sftp.file(remote_path, "w") as f:
            f.write(conf)
        sftp.close()

        ssh.exec_command("systemctl restart rsyslog")
        print(f"✅ Нода {name} успешно добавлена и настроена.")

        # Сохраняем ноду
        nodes = load_nodes()
        nodes.append({
            "host": host,
            "name": name,
            "user": user,
            "port": port,
            "auth_method": "key" if use_key else "password",
            "key_path": key_path if use_key else None
        })
        save_nodes(nodes)
        start_ssh_log_thread(ssh, name)

    except Exception as e:
        print(f"Ошибка настройки ноды: {e}")
    finally:
        pass

def show_nodes():
    nodes = load_nodes()
    if not nodes:
        print("Нет добавленных нод.")
        return
    for i, n in enumerate(nodes, 1):
        auth = "ключ" if n.get("auth_method") == "key" else "пароль"
        print(f"{i}. {n['name']} — {n['host']}:{n.get('port',22)} (пользователь {n.get('user','root')}, аутентификация: {auth})")

def tail_remote_logs_menu():
    nodes = load_nodes()
    if not nodes:
        print("Нет добавленных нод.")
        return
    print("Выберите ноду для просмотра логов:")
    for i, n in enumerate(nodes, 1):
        print(f"{i}. {n['name']} ({n['host']})")
    choice = input("Номер ноды: ").strip()
    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(nodes):
        print("Некорректный выбор.")
        return
    node = nodes[int(choice)-1]

    use_key = node.get("auth_method") == "key"
    password = None
    if not use_key:
        password = getpass.getpass(f"Введите SSH пароль для {node['user']}@{node['host']}: ")

    ssh = ssh_connect(node['host'], node.get("user","root"), node.get("port",22), use_key, node.get("key_path"), password)
    if not ssh:
        print("Не удалось подключиться к ноде.")
        return
    start_ssh_log_thread(ssh, node['name'])
    print("Фоновый сбор логов запущен. Чтобы выйти — прервите программу (Ctrl+C).")

def main():
    start_local_log_thread()

    while True:
        print("\n=== Главное меню ===")
        print("1. Добавить удалённую ноду")
        print("2. Посмотреть список нод")
        print("3. Просмотр локальных логов (фоновый поток запущен автоматически)")
        print("4. Запуск фонового сбора логов удалённой ноды")
        print("5. Выход")
        choice = input("Выбор: ").strip()

        if choice == "1":
            add_remote_node()
        elif choice == "2":
            show_nodes()
        elif choice == "3":
            print("Локальные логи собираются в файл logs_xray_local.log")
        elif choice == "4":
            tail_remote_logs_menu()
        elif choice == "5":
            print("Выход...")
            break
        else:
            print("Некорректный выбор.")
