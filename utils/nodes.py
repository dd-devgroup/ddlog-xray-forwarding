import subprocess
import threading
import getpass
import paramiko
import os
import json
import shlex
from datetime import datetime
from utils.utils import get_local_ip, convert_old_xray_log_to_json
from utils.rsyslog_setup import setup_remote_rsyslog

class Node:
    def __init__(self, name, host=None, user=None, port=22, auth_method=None, key_path=None):
        self.name = name
        self.host = host
        self.user = user
        self.port = port
        self.auth_method = auth_method
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
            self.ssh = None
            return False

    def get_log_tail_command(self):
        if self.local:
            return ["stdbuf", "-oL", "tail", "-n", "+1", "-F", "/var/log/remnanode/xray.out.log"]
        else:
            return "tail -n +1 -F /var/log/remnanode/xray.out.log"

    def start_background_log_collection(self):
        filename = f"/var/log/xray_{self.name}.json"

        if self.local:
            self.convert_old_log_to_json()

            cmd = f"nohup tail -n +1 -F /var/log/remnanode/xray.out.log >> {filename} 2>&1 &"
            subprocess.Popen(shlex.split(cmd))
            print(f"✅ Локальный tail запущен в фоне для '{self.name}' → {filename}")
        else:
            if not self.connect_ssh():
                return
            _, stream, _ = self.ssh.exec_command(self.get_log_tail_command())
            t = threading.Thread(target=self._stream_logs_and_save, args=(stream, filename), daemon=True)
            t.start()
            print(f"✅ Фоновый сбор логов запущен для '{self.name}' → {filename}")

    def _stream_logs_and_save(self, stream, filename):
        try:
            with open(filename, "a", encoding="utf-8") as logfile:
                for line in iter(stream.readline, ""):
                    entry = {
                        "timestamp": datetime.utcnow().isoformat(),
                        "node": self.name,
                        "message": line.strip()
                    }
                    logfile.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    logfile.flush()
        except Exception as e:
            print(f"Ошибка в потоке логов узла '{self.name}': {e}")

    def tail_logs_realtime(self):
        if self.local:
            proc = subprocess.Popen(self.get_log_tail_command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stream = proc.stdout
        else:
            if not self.connect_ssh():
                return
            _, stream, _ = self.ssh.exec_command(self.get_log_tail_command())

        print(f"--- Просмотр логов '{self.name}' (Ctrl+C для выхода) ---")
        try:
            for line in iter(stream.readline, ""):
                print(line, end="")
        except KeyboardInterrupt:
            print("\nВыход.")
        except Exception as e:
            print(f"Ошибка при просмотре: {e}")

    def remove_rsyslog_config(self):
        if self.local:
            print(f"Локальную ноду '{self.name}' удалять вручную.")
            return
        if not self.connect_ssh():
            return
        conf_path = f"/etc/rsyslog.d/30-xray-{self.name}.conf"
        try:
            self.ssh.exec_command(f"rm -f {conf_path} && systemctl restart rsyslog")
            print(f"❌ Конфиг rsyslog удалён на {self.host}")
        except Exception as e:
            print(f"Ошибка при удалении конфига rsyslog на {self.host}: {e}")

    def run_remote_binary(self, bin_path="/usr/local/bin/ddlog-xray-forwarding.bin"):
        if not self.connect_ssh():
            return
        cmd = f"nohup {bin_path} > /var/log/ddlog-forwarder.log 2>&1 &"
        try:
            self.ssh.exec_command(cmd)
            print(f"✅ Запущен бинарник на {self.host} в фоне.")
        except Exception as e:
            print(f"Ошибка запуска бинарника на {self.host}: {e}")

    def convert_old_log_to_json(self):
        if self.local:
            log_path = "/var/log/remnanode/xray.out.log"
            json_path = f"/var/log/xray_{self.name}.json"
            return convert_old_xray_log_to_json(log_path, json_path)
        else:
            print(f"Конвертация доступна только для локальной ноды '{self.name}'")
            return False

def load_nodes():
    if os.path.exists("nodes.json"):
        with open("nodes.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return [Node(**n) for n in data]
    return []

def save_nodes(nodes):
    with open("nodes.json", "w", encoding="utf-8") as f:
        json.dump([{
            "name": n.name,
            "host": n.host,
            "user": n.user,
            "port": n.port,
            "auth_method": n.auth_method,
            "key_path": n.key_path
        } for n in nodes], f, ensure_ascii=False, indent=2)

def add_remote_node(nodes):
    print("Добавление удалённой ноды:")
    name = input("Имя ноды: ").strip()
    host = input("IP или hostname: ").strip()
    user = input("Пользователь SSH: ").strip()
    port_str = input("Порт SSH (по умолчанию 22): ").strip()
    port = int(port_str) if port_str.isdigit() else 22
    print("Выберите метод аутентификации:\n1) SSH key\n2) Пароль")
    auth_choice = input("Выбор (1/2): ").strip()
    if auth_choice == "1":
        auth_method = "key"
        key_path = input("Путь к SSH private key (например ~/.ssh/id_rsa): ").strip()
    else:
        auth_method = "password"
        key_path = None

    node = Node(name=name, host=host, user=user, port=port, auth_method=auth_method, key_path=key_path)
    if node.connect_ssh():
        print("Настройка rsyslog на удалённой ноде...")
        setup_remote_rsyslog(node)
        node.start_background_log_collection()
        nodes.append(node)
        print(f"✅ Нода '{name}' добавлена и настроена.")
    else:
        print("❌ Не удалось подключиться и настроить ноду.")

def remove_remote_node(node):
    print(f"Удаляем конфиг rsyslog и удаляем ноду {node.name}...")
    node.remove_rsyslog_config()
    print(f"Удалено.")
