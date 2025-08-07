import subprocess
import threading
import getpass
import paramiko
import os

from utils.utils import get_local_ip
from utils.rsyslog_setup import setup_remote_rsyslog

class Node:
    def __init__(self, name, host=None, user=None, port=22, auth_method=None, key_path=None):
        self.name = name
        self.host = host  # None для локальной ноды
        self.user = user
        self.port = port
        self.auth_method = auth_method
        self.key_path = key_path
        self.password = None
        self.ssh = None
        self.local = host is None

    def connect_ssh(self):
        if self.local or self.ssh:
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
    import json

    NODES_FILE = "nodes.json"
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
    import json

    NODES_FILE = "nodes.json"
    data = []
    for n in nodes:
        if n.local:
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
    port = int(input("SSH порт (по умолчанию 22): ").strip() or "22")

    auth_method = input("Аутентификация (1 - ключ, 2 - пароль): ").strip()
    use_key = auth_method == "1"

    key_path = None
    password = None
    if use_key:
        key_path = input("Путь к SSH-ключу (по умолчанию ~/.ssh/id_rsa): ").strip() or os.path.expanduser("~/.ssh/id_rsa")
    else:
        password = getpass.getpass("Введите SSH пароль: ")

    node = Node(name=name, host=host, user=user, port=port,
                auth_method="key" if use_key else "password", key_path=key_path)
    if not node.connect_ssh():
        print("Не удалось подключиться к удалённой ноде.")
        return

    try:
        setup_remote_rsyslog(node, get_local_ip())
        print(f"✅ rsyslog настроен для {name}.")
    except Exception as e:
        print(f"❌ Ошибка при настройке rsyslog: {e}")

    nodes.append(node)
