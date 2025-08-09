import subprocess
import threading
import getpass
import paramiko
import os
import json
import shlex
from datetime import datetime
from utils.utils import get_local_ip, convert_old_xray_log_to_json
from utils.rsyslog_setup import remove_rsyslog_config, remove_ufw_rules

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

    def start_local_tail_in_background(self):
        """Для локальной ноды запускаем tail -F в фоне, который пишет логи в json."""
        filename = f"/var/log/xray_{self.name}.json"
        self.convert_old_log_to_json()

        # Проверяем, не запущен ли уже tail (по файлу pid, или по процессам — можно добавить)
        # Для простоты — просто запускаем nohup tail
        cmd = f"nohup tail -n +1 -F /var/log/remnanode/xray.out.log >> {filename} 2>&1 &"
        subprocess.Popen(shlex.split(cmd))
        print(f"✅ Локальный tail запущен в фоне для '{self.name}' → {filename}")

    def start_remote_log_forwarding(self):
        """Для удалённой ноды настраиваем rsyslog + запускаем форвардер."""
        if not self.connect_ssh():
            return
        print(f"Настройка rsyslog для удалённой ноды {self.name} ({self.host})...")
        setup_remote_rsyslog(self)
        print(f"Запуск бинарника форвардера...")
        self.run_remote_binary()

    def start_background_log_collection(self):
        if self.local:
            self.start_local_tail_in_background()
        else:
            self.start_remote_log_forwarding()

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

    def tail_logs_realtime(self):
        """Просмотр логов в реальном времени — локально или по SSH."""
        if self.local:
            cmd = ["tail", "-n", "+1", "-F", "/var/log/remnanode/xray.out.log"]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stream = proc.stdout
        else:
            if not self.connect_ssh():
                return
            _, stream, _ = self.ssh.exec_command("tail -n +1 -F /var/log/remnanode/xray.out.log")

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

def add_node(nodes):
    print("Добавление ноды:")
    node_type = input("Выберите тип ноды:\n1) Локальная\n2) Удалённая\nВыбор (1/2): ").strip()

    if node_type == "1":
        # Локальная нода - хост, пользователь, ssh не нужны
        name = input("Имя локальной ноды: ").strip()
        node = Node(name=name)  # host=None значит локальная
        node.convert_old_log_to_json()  # если нужно сразу конвертировать логи локальной ноды
        node.start_background_log_collection()
        nodes.append(node)
        print(f"✅ Локальная нода '{name}' добавлена и настроена.")
    elif node_type == "2":
        # Добавляем удалённую ноду
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
            print(f"✅ Удалённая нода '{name}' добавлена и настроена.")
        else:
            print("❌ Не удалось подключиться и настроить ноду.")
    else:
        print("❌ Некорректный выбор, нода не добавлена.")


def remove_remote_node(node, central_server_ip):
    print(f"Удаляем конфиг rsyslog и ufw правила на ноде {node.name}...")
    remove_rsyslog_config(node)
    remove_ufw_rules(node, central_server_ip)
    print(f"Удалено.")