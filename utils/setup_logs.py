import subprocess
import getpass
import paramiko
import threading
import os
import json
import socket
import sys
import logging
import time

NODES_FILE = "nodes.json"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("nodes_manager.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception as e:
        logging.warning(f"Не удалось определить локальный IP, fallback на 127.0.0.1: {e}")
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
        self._stop_event = threading.Event()
        self._log_thread = None

    def connect_ssh(self):
        if self.local:
            return True
        if self.ssh and self.ssh.get_transport() and self.ssh.get_transport().is_active():
            return True
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            if self.auth_method == "key":
                if not self.key_path or not os.path.isfile(os.path.expanduser(self.key_path)):
                    logging.error(f"SSH ключ не найден: {self.key_path}")
                    return False
                self.ssh.connect(
                    self.host,
                    port=self.port,
                    username=self.user,
                    key_filename=os.path.expanduser(self.key_path),
                    timeout=10,
                    banner_timeout=10,
                    auth_timeout=10,
                )
            else:
                if self.password is None:
                    try:
                        self.password = getpass.getpass(f"Введите SSH пароль для {self.user}@{self.host}: ")
                    except Exception as e:
                        logging.error(f"Ошибка при вводе пароля: {e}")
                        return False
                self.ssh.connect(
                    self.host,
                    port=self.port,
                    username=self.user,
                    password=self.password,
                    timeout=10,
                    banner_timeout=10,
                    auth_timeout=10,
                )
            logging.info(f"Успешное подключение к {self.host}")
            return True
        except paramiko.AuthenticationException:
            logging.error(f"Ошибка аутентификации для {self.host}")
        except paramiko.SSHException as e:
            logging.error(f"SSH ошибка при подключении к {self.host}: {e}")
        except socket.timeout:
            logging.error(f"Таймаут подключения к {self.host}")
        except Exception as e:
            logging.error(f"Неизвестная ошибка подключения к {self.host}: {e}")
        return False

    def _check_docker_container(self, container_name="remnanode"):
        """Проверяем, что локально есть docker и запущен контейнер remnanode."""
        try:
            subprocess.run(["docker", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logging.error("Docker не установлен или недоступен локально.")
            return False

        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            containers = result.stdout.strip().splitlines()
            if container_name not in containers:
                logging.error(f"Контейнер '{container_name}' не запущен локально.")
                return False
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Ошибка при проверке контейнеров Docker: {e}")
            return False

    def start_background_log_collection(self):
        """Запускает фоновый поток, который пишет логи в файл."""
        filename = f"logs_xray_{self.name}.log"
        if self._log_thread and self._log_thread.is_alive():
            logging.info(f"Фоновый сбор логов для узла '{self.name}' уже запущен.")
            return
        if self.local:
            if not self._check_docker_container():
                logging.error("Невозможно собрать логи локально — Docker контейнер не доступен.")
                return
            proc = subprocess.Popen(
                ["docker", "exec", "remnanode", "tail", "-n", "+1", "-f", "/var/log/supervisor/xray.out.log"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stream = proc.stdout
            # Можно добавить хранение proc, чтобы завершать позже, если нужно
        else:
            if not self.connect_ssh():
                return
            try:
                _, stream, _ = self.ssh.exec_command(
                    "tail -n +1 -f /var/log/supervisor/xray.out.log",
                    timeout=3600
                )
            except Exception as e:
                logging.error(f"Ошибка запуска команды tail на {self.host}: {e}")
                return

        self._stop_event.clear()
        self._log_thread = threading.Thread(
            target=self._stream_logs_and_save, args=(stream, filename), daemon=True
        )
        self._log_thread.start()
        logging.info(f"Фоновый сбор логов запущен для узла '{self.name}', сохраняется в {filename}")

    def stop_background_log_collection(self):
        """Попытка остановить поток сбора логов (не гарантированно, зависит от реализации)."""
        if self._log_thread and self._log_thread.is_alive():
            logging.info(f"Остановка фонового сбора логов для узла '{self.name}'")
            self._stop_event.set()
            self._log_thread.join(timeout=5)

    def _stream_logs_and_save(self, stream, filename):
        try:
            with open(filename, "a", encoding="utf-8") as logfile:
                while not self._stop_event.is_set():
                    line = stream.readline()
                    if not line:
                        # Поток закончился или соединение прервано
                        time.sleep(0.5)
                        continue
                    logfile.write(line)
                    logfile.flush()
        except Exception as e:
            logging.error(f"Ошибка в потоке логов узла '{self.name}': {e}")

    def tail_logs_realtime(self):
        """Показывает логи в реальном времени в консоли (без сохранения)."""
        if self.local:
            if not self._check_docker_container():
                logging.error("Невозможно просмотреть логи локально — Docker контейнер не доступен.")
                return
            proc = subprocess.Popen(
                ["docker", "exec", "remnanode", "tail", "-n", "+1", "-f", "/var/log/supervisor/xray.out.log"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stream = proc.stdout
        else:
            if not self.connect_ssh():
                return
            try:
                _, stream, _ = self.ssh.exec_command(
                    "tail -n +1 -f /var/log/supervisor/xray.out.log",
                    timeout=3600
                )
            except Exception as e:
                logging.error(f"Ошибка запуска команды tail на {self.host}: {e}")
                return

        logging.info(f"--- Просмотр логов узла '{self.name}' (Ctrl+C для выхода) ---")
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    time.sleep(0.5)
                    continue
                print(line, end="")
        except KeyboardInterrupt:
            logging.info("Выход из просмотра логов.")
        except Exception as e:
            logging.error(f"Ошибка при просмотре логов узла '{self.name}': {e}")

def load_nodes():
    if os.path.exists(NODES_FILE):
        try:
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
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Ошибка загрузки файла {NODES_FILE}: {e}")
            return []
    else:
        # Добавим локальную ноду по умолчанию
        local_node = Node(name="local")
        return [local_node]

def save_nodes(nodes):
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
    try:
        with open(NODES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except IOError as e:
        logging.error(f"Ошибка сохранения файла {NODES_FILE}: {e}")

def add_remote_node(nodes):
    host = input("IP ноды: ").strip()
    name = input("Название (уникальное): ").strip()
    if any(n.name == name for n in nodes):
        logging.warning("Нода с таким именем уже есть.")
        return
    user = input("SSH пользователь (по умолчанию root): ").strip() or "root"
    port_input = input("SSH порт (по умолчанию 22): ").strip()
    try:
        port = int(port_input) if port_input else 22
    except ValueError:
        logging.warning("Некорректный номер порта. Используется 22.")
        port = 22

    auth_method = input("Аутентификация (1 - ключ, 2 - пароль): ").strip()
    use_key = auth_method == "1"

    if use_key:
        key_path = input("Путь к SSH-ключу (по умолчанию ~/.ssh/id_rsa): ").strip()
        if not key_path:
            key_path = os.path.expanduser("~/.ssh/id_rsa")
        password = None
    else:
        key_path = None
        try:
            password = getpass.getpass("Введите SSH пароль: ")
        except Exception as e:
            logging.error(f"Ошибка при вводе пароля: {e}")
            return

    node = Node(name=name, host=host, user=user, port=port,
                auth_method="key" if use_key else "password", key_path=key_path)
    if not node.connect_ssh():
        logging.error("Не удалось подключиться к удалённой ноде. Проверьте данные.")
        return

    # Настройка rsyslog
    try:
        logging.info("Установка rsyslog и настройка конфигурации на удалённой ноде...")
        stdin, stdout, stderr = node.ssh.exec_command("apt update && apt install -y rsyslog")
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            err = stderr.read().decode()
            logging.error(f"Ошибка установки rsyslog: {err}")
            return

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

        try:
            sftp = node.ssh.open_sftp()
            with sftp.file(remote_path, "w") as f:
                f.write(CONF_TEMPLATE)
            sftp.close()
        except IOError as e:
            logging.error(f"Ошибка записи конфигурации rsyslog (нужны root-права?): {e}")
            return

        stdin, stdout, stderr = node.ssh.exec_command("systemctl restart rsyslog")
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            err = stderr.read().decode()
            logging.error(f"Ошибка перезапуска rsyslog: {err}")
            return

        logging.info(f"Нода {name} успешно настроена.")
    except Exception as e:
        logging.error(f"Ошибка при настройке rsyslog на ноде {name}: {e}")
        return

    nodes.append(node)
    save_nodes(nodes)

def main():
    nodes = load_nodes()

    while True:
        print("\n== Менеджер нод ==")
        for idx, n in enumerate(nodes, 1):
            print(f"{idx}. {n.name} (локальная)" if n.local else f"{idx}. {n.name} ({n.host})")
        print("a - Добавить удалённую ноду")
        print("q - Выход")
        choice = input("Выберите действие: ").strip().lower()
        if choice == "q":
            logging.info("Выход из программы.")
            # Остановка всех фоновых потоков
            for n in nodes:
                n.stop_background_log_collection()
            break
        elif choice == "a":
            add_remote_node(nodes)
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(nodes):
                    node = nodes[idx]
                    print(f"Выбрана нода '{node.name}'")
                    print("1. Просмотреть логи в реальном времени")
                    print("2. Запустить фоновый сбор логов с записью в файл")
                    print("3. Остановить фоновый сбор логов")
                    action = input("Выберите действие: ").strip()
                    if action == "1":
                        node.tail_logs_realtime()
                    elif action == "2":
                        node.start_background_log_collection()
                    elif action == "3":
                        node.stop_background_log_collection()
                    else:
                        logging.warning("Неверное действие.")
                else:
                    logging.warning("Неверный номер ноды.")
            except ValueError:
                logging.warning("Неверный ввод.")

if __name__ == "__main__":
    main()
