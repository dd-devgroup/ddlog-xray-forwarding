import sys
from utils.nodes import load_nodes, save_nodes, add_remote_node
from utils.rsyslog_setup import setup_central_rsyslog

def main():
    setup_central_rsyslog()

    nodes = load_nodes()

    while True:
        print("\n=== Главное меню ===")
        print("1. Добавить удалённую ноду")
        print("2. Посмотреть список нод")
        print("3. Просмотр логов ноды в реальном времени")
        print("4. Выход")
        choice = input("Выбор: ").strip()

        if choice == "1":
            add_remote_node(nodes)
            save_nodes(nodes)
        elif choice == "2":
            for i, node in enumerate(nodes, 1):
                print(f"{i}. {node.name} ({'локальная' if node.local else node.host})")
        elif choice == "3":
            if not nodes:
                print("Нет нод для просмотра.")
                continue
            for i, node in enumerate(nodes, 1):
                print(f"{i}. {node.name} ({'локальная' if node.local else node.host})")
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
