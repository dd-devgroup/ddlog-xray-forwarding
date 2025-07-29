import json
import os
import paramiko

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

def add_node():
    host = input("IP ноды: ")
    name = input("Название (уникальное): ")
    ssh_key = input("Путь к SSH-ключу (по умолчанию ~/.ssh/id_rsa): ") or os.path.expanduser("~/.ssh/id_rsa")

    node = {"host": host, "name": name, "ssh_key": ssh_key, "user": "root"}

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username="root", key_filename=ssh_key)

        # Установка rsyslog
        ssh.exec_command("apt update && apt install -y rsyslog")

        conf = CONF_TEMPLATE.format(node=name, central_host=CENTRAL_HOST, central_port=CENTRAL_PORT)
        path = f"/etc/rsyslog.d/30-xray-{name}.conf"

        sftp = ssh.open_sftp()
        with sftp.file(path, "w") as f:
            f.write(conf)
        sftp.close()

        ssh.exec_command("systemctl restart rsyslog")
        print(f"✅ Нода {name} добавлена и настроена.")

        nodes = load_nodes()
        nodes.append(node)
        save_nodes(nodes)

    except Exception as e:
        print(f"❌ Ошибка: {e}")

def show_nodes():
    nodes = load_nodes()
    if not nodes:
        print("Нет добавленных нод.")
        return
    for i, n in enumerate(nodes, 1):
        print(f"{i}. {n['name']} — {n['host']}")

def main():
    while True:
        print("\n=== Меню ===")
        print("1. Добавить ноду")
        print("2. Посмотреть список нод")
        print("3. Выход")
        choice = input("Выбор: ").strip()

        if choice == "1":
            add_node()
        elif choice == "2":
            show_nodes()
        elif choice == "3":
            break
        else:
            print("Некорректный выбор.")

if __name__ == "__main__":
    main()
