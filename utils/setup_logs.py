import subprocess
import getpass
import paramiko
import threading
import os
import json

NODES_FILE = "nodes.json"

CENTRAL_HOST = "89.39.121.249"
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

def run_local_logs():
    print("Запуск логов локальной ноды (ctrl+c для выхода)...")
    try:
        subprocess.run(["docker", "exec", "-it", "remnanode", "tail", "-n", "+1", "-f", "/var/log/supervisor/xray.out.log"])
    except KeyboardInterrupt:
        print("\nВыход из просмотра логов.")

def run_ssh_logs(ssh):
    try:
        stdin, stdout, stderr = ssh.exec_command("tail -n +1 -f /var/log/supervisor/xray.out.log")
        print("Просмотр логов удалённой ноды (ctrl+c для выхода)...")
        for line in iter(stdout.readline, ""):
            print(line, end="")
    except KeyboardInterrupt:
        print("\nВыход из просмотра логов.")

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

    except Exception as e:
        print(f"Ошибка настройки ноды: {e}")
    finally:
        ssh.close()

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
    run_ssh_logs(ssh)
    ssh.close()

def main():
    while True:
        print("\n=== Главное меню ===")
        print("1. Добавить удалённую ноду")
        print("2. Посмотреть список нод")
        print("3. Просмотр логов локальной ноды")
        print("4. Просмотр логов удалённой ноды")
        print("5. Выход")
        choice = input("Выбор: ").strip()

        if choice == "1":
            add_remote_node()
        elif choice == "2":
            show_nodes()
        elif choice == "3":
            run_local_logs()
        elif choice == "4":
            tail_remote_logs_menu()
        elif choice == "5":
            print("Выход...")
            break
        else:
            print("Некорректный выбор.")

if __name__ == "__main__":
    main()
