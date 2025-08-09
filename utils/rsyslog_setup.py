import subprocess
import os
import paramiko

def run_cmd(cmd):
    """Запуск shell команды, вывод результата."""
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка команды '{cmd}': {e.stderr.strip()}")
        return None

def setup_central_rsyslog():
    if os.geteuid() != 0:
        print("⚠️ Для настройки центрального rsyslog нужно запускать скрипт с правами root.")
        return

    conf_path = "/etc/rsyslog.d/10-remote-xray.conf"
    conf_content = """
module(load="imtcp")
input(type="imtcp" port="514" ruleset="xray-logs")

ruleset(name="xray-logs") {
    if ($syslogtag contains "xray-") then {
        action(type="omfile" file="/var/log/xray.log" flushOnTXEnd="on")
        stop
    }
}
"""

    try:
        with open(conf_path, "w", encoding="utf-8") as f:
            f.write(conf_content.lstrip())  # убираем лишний ведущий перевод строки
        print(f"✅ Конфиг центрального rsyslog записан в {conf_path}")

        subprocess.run(["systemctl", "restart", "rsyslog"], check=True)
        print("✅ rsyslog на центральном сервере перезапущен и готов принимать логи.")
    except Exception as e:
        print(f"❌ Ошибка при настройке центрального rsyslog: {e}")

def setup_remote_rsyslog(node, central_host):
    """Настройка rsyslog на удалённой ноде для отправки логов на центральный сервер."""
    if not node.connect_ssh():
        print(f"❌ Нет SSH соединения с {node.host}")
        return

    # Установка rsyslog (non-interactive)
    try:
        cmd = "DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y rsyslog"
        stdin, stdout, stderr = node.ssh.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            err = stderr.read().decode().strip()
            print(f"❌ Не удалось установить rsyslog на {node.host}: {err}")
            # можно продолжить, если rsyslog уже установлен
    except Exception as e:
        print(f"❌ Ошибка при установке rsyslog на {node.host}: {e}")

    # подготовка конфигурации (вставляем central_host)
    conf_template = f"""
module(load="imfile")

input(type="imfile"
      File="/var/log/remnanode/xray.out.log"
      Tag="xray-node-{node.name}"
      Severity="info"
      Facility="local7"
      PersistStateInterval="200"
      PollingInterval="1")

*.* @@{central_host}:514
"""

    remote_path = f"/etc/rsyslog.d/30-xray-{node.name}.conf"
    try:
        sftp = node.ssh.open_sftp()
        # удалить старый конфиг, если есть
        try:
            sftp.remove(remote_path)
        except IOError:
            pass
        # записать новый
        with sftp.open(remote_path, "w") as f:
            f.write(conf_template.lstrip())
        sftp.close()
    except Exception as e:
        print(f"❌ Ошибка записи конфига на {node.host}: {e}")
        return

    # перезапуск rsyslog на удалённой ноде и проверка
    try:
        stdin, stdout, stderr = node.ssh.exec_command("systemctl restart rsyslog")
        exit_status = stdout.channel.recv_exit_status()
        if exit_status == 0:
            print(f"✅ rsyslog настроен на удалённой ноде {node.name}.")
        else:
            err = stderr.read().decode().strip()
            print(f"❌ Ошибка перезапуска rsyslog на {node.name}: {err}")
    except Exception as e:
        print(f"❌ Ошибка при перезапуске rsyslog на {node.host}: {e}")


def setup_ufw_central(allowed_ips: list[str]):
    """
    На центральном сервере разрешить вход на порт 514 (tcp и udp) только с allowed_ips.
    """
    print("⚙️ Настройка UFW на центральном сервере...")
    for ip in allowed_ips:
        cmd_tcp = f"ufw allow from {ip} to any port 514 proto tcp"
        cmd_udp = f"ufw allow from {ip} to any port 514 proto udp"
        print(f"-> {cmd_tcp}")
        run_cmd(cmd_tcp)
        print(f"-> {cmd_udp}")
        run_cmd(cmd_udp)
    print("✅ UFW настроен на центральном сервере.")

def setup_ufw_remote(node, central_server_ip: str):
    """
    На удалённой ноде разрешить исходящие подключения на порт 514 (tcp и udp) к центральному серверу.
    """
    print(f"⚙️ Настройка UFW на удалённой ноде {node.name}...")
    if not node.connect_ssh():
        print(f"❌ Не удалось подключиться к {node.host} для настройки UFW.")
        return

    cmds = [
        f"ufw allow out to {central_server_ip} port 514 proto tcp",
        f"ufw allow out to {central_server_ip} port 514 proto udp",
    ]

    try:
        for cmd in cmds:
            print(f"-> {cmd}")
            stdin, stdout, stderr = node.ssh.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                err = stderr.read().decode().strip()
                print(f"❌ Ошибка команды '{cmd}': {err}")
        print(f"✅ UFW настроен на удалённой ноде {node.name}.")
    except Exception as e:
        print(f"❌ Ошибка настройки UFW на {node.name}: {e}")

def remove_rsyslog_config(node):
    if not node.connect_ssh():
        return
    conf_path = f"/etc/rsyslog.d/30-xray-{node.name}.conf"
    try:
        node.ssh.exec_command(f"rm -f {conf_path} && systemctl restart rsyslog")
        print(f"❌ Конфиг rsyslog удалён на {node.host}")
    except Exception as e:
        print(f"Ошибка при удалении конфига rsyslog на {node.host}: {e}")

def remove_ufw_rules(node, central_server_ip):
    if not node.connect_ssh():
        return
    cmds = [
        f"ufw delete allow out to {central_server_ip} port 514 proto tcp",
        f"ufw delete allow out to {central_server_ip} port 514 proto udp",
    ]
    for cmd in cmds:
        try:
            stdin, stdout, stderr = node.ssh.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0:
                print(f"Удалено правило ufw: {cmd}")
            else:
                err = stderr.read().decode().strip()
                print(f"Ошибка при удалении правила ufw '{cmd}': {err}")
        except Exception as e:
            print(f"Ошибка при выполнении команды '{cmd}': {e}")
