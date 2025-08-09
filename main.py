import sys
from utils.nodes import (
    load_nodes,
    save_nodes,
    add_remote_node,
    remove_remote_node,
)
from utils.rsyslog_setup import setup_central_rsyslog
from rich.console import Console
from rich.table import Table

console = Console()

def show_nodes(nodes):
    table = Table(title="Список нод")
    table.add_column("№", style="cyan", justify="right")
    table.add_column("Имя", style="green")
    table.add_column("Хост", style="yellow")
    table.add_column("Тип", style="magenta")
    for i, node in enumerate(nodes, 1):
        table.add_row(str(i), node.name, node.host or "-", "локальная" if node.local else "удалённая")
    console.print(table)

def main():
    try:
        console.print("[bold cyan]Запускаем setup_central_rsyslog()...[/bold cyan]")
        setup_central_rsyslog()

        console.print("[bold cyan]Загружаем ноды...[/bold cyan]")
        nodes = load_nodes()
        console.print(f"[bold green]Загружено нод:[/bold green] {len(nodes)}")

        for node in nodes:
            console.print(f"[bold yellow]Запускаем фоновый сбор логов:[/bold yellow] {node.name}")
            node.start_background_log_collection()

        while True:
            console.print("\n[bold magenta]=== Главное меню ===[/bold magenta]")
            console.print("1. Добавить удалённую ноду")
            console.print("2. Посмотреть список нод")
            console.print("3. Просмотр логов ноды в реальном времени")
            console.print("4. Удалить ноду")
            console.print("5. Выход")
            choice = input("Выбор: ").strip()

            if choice == "1":
                add_remote_node(nodes)
                save_nodes(nodes)
            elif choice == "2":
                if not nodes:
                    console.print("[red]Нет добавленных нод.[/red]")
                else:
                    show_nodes(nodes)
            elif choice == "3":
                if not nodes:
                    console.print("[red]Нет нод для просмотра.[/red]")
                    continue
                show_nodes(nodes)
                sel = input("Выберите номер ноды: ").strip()
                if sel.isdigit() and 1 <= int(sel) <= len(nodes):
                    nodes[int(sel) - 1].tail_logs_realtime()
                else:
                    console.print("[red]Некорректный выбор.[/red]")
            elif choice == "4":
                if not nodes:
                    console.print("[red]Нет нод для удаления.[/red]")
                    continue
                show_nodes(nodes)
                sel = input("Выберите номер ноды для удаления: ").strip()
                if sel.isdigit() and 1 <= int(sel) <= len(nodes):
                    node = nodes[int(sel) - 1]
                    confirm = input(f"Точно удалить {node.name}? (y/N): ").strip().lower()
                    if confirm == "y":
                        remove_remote_node(node)
                        nodes.pop(int(sel) - 1)
                        save_nodes(nodes)
                        console.print(f"[green]✅ Нода '{node.name}' удалена.[/green]")
                else:
                    console.print("[red]Некорректный выбор.[/red]")
            elif choice == "5":
                console.print("[bold red]Выход...[/bold red]")
                break
            else:
                console.print("[red]Некорректный выбор.[/red]")
    except KeyboardInterrupt:
        console.print("\n[bold red]Выход по Ctrl+C[/bold red]")
    except Exception as e:
        console.print(f"[bold red]Ошибка в main():[/bold red] {e}")

if __name__ == "__main__":
    main()
