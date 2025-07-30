import subprocess
import getpass
import paramiko
import threading
import os
import json
import socket
import sys

NODES_FILE = "nodes.json"

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

class Node:
    def __init__(self, name, host=None, user=None, port=22, auth_method=None, key_path=None):
        self.name = name
        self.host = host  # None для локальной ноды
        self.user = user
        self.port = port
        self.auth_method = auth_method  # "key" или "password" или None (для локальной)
        self.key_path = key_path
        self.password = None
        self.ssh = None
        self.local = host is None

    def connect_ssh(self):
        if self.local:
            return True
        if self.ssh:
            return True
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            if self.auth_method == "key":
                self.ssh.connect(self.host, port=self.port, username=self.user, key_filename=self.key_path, timeout=10)
            else:
                if self.password is None:
                    self.password = getpass.getpass(f"Введите SSH пароль для {self.user}@{self.host}: ")
                self.ssh.connect(self.host, port=self.port, username=self.user, password=self.password, timeout=10)
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения к {self.host}: {e}")
            return False

    def start_background_log_collection(self):
        """Запускает фоновый поток, который пишет логи в файл."""
        filename = f"logs_xray_{self.name}.log"
        if self.local:
            proc = subprocess.Popen(
                ["docker", "exec", "remnanode", "tail", "-n", "+1", "-f", "/var/log/supervisor/xray.out.log"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stream = proc.stdout
        else:
            if not self.connect_ssh():
                return
            _, stream, _ = self.ssh.exec_command("tail -n +1 -f /var/log/supervisor/xray.out.log")
        t = threading.Thread(target=self._stream_logs_and_save, args=(stream, filename), daemon=True)
        t.start()
        print(f"✅ Фоновый сбор логов запущен для узла '{self.name}' (сохраняется в {filename})")

    def _stream_logs_and_save(self, stream, filename):
        try:
            with open(filename, "a", encoding="utf-8") as logfile:
                for line in iter(stream.readline, ""):
                    logfile.write(line)
                    logfile.flush()
        except Exception as e:
            print(f"Ошибка в потоке логов узла '{self.name}': {e}")

    def tail_logs_realtime(self):
        """Показывает логи в реальном времени в консоли (без сохранения)."""
        if self.local:
            proc = subprocess.Popen(
                ["docker", "exec", "remnanode", "tail", "-n", "+1", "-f", "/var/log/supervisor/xray.out.log"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stream = proc.stdout
        else:
            if not self.connect_ssh():
                return
            _, stream, _ = self.ssh.exec_command("tail -n +1 -f /var/log/supervisor/xray.out.log")

        print(f"--- Просмотр логов узла '{self.name}' (нажмите Ctrl+C для выхода) ---")
        try:
            for line in iter(stream.readline, ""):
                print(line, end="")
        except KeyboardInterrupt:
            print("\nВыход из просмотра логов.")
        except Exception as e:
            print(f"Ошибка при просмотре логов узла '{self.name}': {e}")

def load_nodes():
    if os.path.exists(NODES_FILE):
        with open(NODES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            nodes = []
            for n in data:
                node = Node(
                    name=n["name"],
                    host=n.get("host"),
                    user=n.get("user"),
                    port=n.get("port", 22),
                    auth_method=n.get("auth_method"),
                    key_path=n.get("key_path"),
                )
                nodes.append(node)
            return nodes
    else:
        # Добавим локальную ноду по умолчанию
        local_node = Node(name="local")
        return [local_node]

def save_nodes(nodes):
    data = []
    for n in nodes:
        if n.local:
            # Не сохраняем локальную ноду в файл (или можно, если хотите)
            continue
        data.append({
            "name": n.name,
            "host": n.host,
            "user": n.user,
            "port": n.port,
            "auth_method": n.auth_method,
            "key_path": n.key_path,
        })
    with open(NODES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def add_remote_node(nodes):
    host = input("IP ноды: ").strip()
    name = input("Название (уникальное): ").strip()
    if any(n.name == name for n in nodes):
        print("Нода с таким именем уже есть.")
        return
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

    node = Node(name=name, host=host, user=user, port=port,
                auth_method="key" if use_key else "password", key_path=key_path)
    if not node.connect_ssh():
        print("Не удалось подключиться к удалённой ноде. Проверьте данные.")
        return

    # Настройка rsyslog (можно при необходимости)
    try:
        print("Установка rsyslog и настройка конфигурации на удалённой ноде...")
        stdin, stdout, stderr = node.ssh.exec_command("apt update && apt install -y rsyslog")
        stdout.channel.recv_exit_status()

        CENTRAL_HOST = get_local_ip()
        CENTRAL_PORT = 514
        CONF_TEMPLATE = f"""
module(load="imfile")

input(type="imfile"
      File="/var/log/supervisor/xray.out.log"
      Tag="xray-{name}"
      Severity="info"
      Facility="local7"
      PersistStateInterval="200"
      PollingInterval="1")

*.* @@{CENTRAL_HOST}:{CENTRAL_PORT}
"""
        remote_path = f"/etc/rsyslog.d/30-xray-{name}.conf"
        sftp = node.ssh.open_sftp()
        with sftp.file(remote_path, "w") as f:
            f.write(CONF_TEMPLATE)
        sftp.close()

        node.ssh.exec_command("systemctl restart rsyslog")
        print(f"✅ Нода {name} успешно настроена.")
    except Exception as e:
        print(f"Ошибка настройки rsyslog: {e}")

    nodes.append(node)
    save_nodes(nodes)
    node.start_background_log_collection()

def show_nodes(nodes):
    if not nodes:
        print("Нет добавленных нод.")
        return
    for i, n in enumerate(nodes, 1):
        typ = "локальная" if n.local else f"удалённая ({n.host})"
        print(f"{i}. {n.name} — {typ}")

def main():
    nodes = load_nodes()

    # Запускаем фоновый сбор логов для всех нод (локальной и удалённых)
    for node in nodes:
        node.start_background_log_collection()

    while True:
        print("\n=== Главное меню ===")
        print("1. Добавить удалённую ноду")
        print("2. Посмотреть список нод")
        print("3. Просмотр логов ноды в реальном времени")
        print("4. Выход")
        choice = input("Выбор: ").strip()

        if choice == "1":
            add_remote_node(nodes)
        elif choice == "2":
            show_nodes(nodes)
        elif choice == "3":
            if not nodes:
                print("Нет нод для просмотра.")
                continue
            show_nodes(nodes)
            sel = input("Выберите номер ноды для просмотра логов: ").strip()
            if not sel.isdigit() or int(sel) < 1 or int(sel) > len(nodes):
                print("Некорректный выбор.")
                continue
            node = nodes[int(sel) - 1]
            node.tail_logs_realtime()
        elif choice == "4":
            print("Выход...")
            sys.exit(0)
        else:
            print("Некорректный выбор.")

if __name__ == "__main__":
    main()
