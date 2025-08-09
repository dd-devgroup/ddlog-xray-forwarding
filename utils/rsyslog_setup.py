import subprocess
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
    """
    Настройка центрального rsyslog-сервера.
    Требуется запускать с root.
    """
    conf_path = "/etc/rsyslog.d/30-xray-remote.conf"
    config_content = """
module(load="imudp")
input(type="imudp" port="514")
module(load="imtcp")
input(type="imtcp" port="514")

$template RemoteLogs,"/var/log/remote/%HOSTNAME%/%PROGRAMNAME%.log"
*.* ?RemoteLogs
& ~
"""
    try:
        with open(conf_path, "w", encoding="utf-8") as f:
            f.write(config_content.strip() + "\n")
        subprocess.run(["systemctl", "restart", "rsyslog"], check=True)
        print("✅ Центральный rsyslog настроен и перезапущен.")
    except PermissionError:
        print("❌ Требуются права root для настройки центрального rsyslog.")
    except Exception as e:
        print(f"❌ Ошибка настройки центрального rsyslog: {e}")

def setup_remote_rsyslog(node, central_server_ip=None):
    """
    Настройка rsyslog на удалённой ноде для отправки логов на центральный сервер.
    central_server_ip - IP или hostname центрального rsyslog.
    """
    if central_server_ip is None:
        print("❌ Не указан IP центрального сервера для rsyslog.")
        return

    conf_path = f"/etc/rsyslog.d/30-xray-{node.name}.conf"
    config_content = f"""
module(load="imfile")
input(type="imfile"
      File="/var/log/remnanode/xray.out.log"
      Tag="xray-node-{node.name}"
      Severity="info"
      Facility="local7")
*.* @@{central_server_ip}:514
"""
    if not node.connect_ssh():
        print(f"❌ Не удалось подключиться к {node.host} для настройки rsyslog.")
        return
    try:
        sftp = node.ssh.open_sftp()
        with sftp.file(conf_path, "w", encoding="utf-8") as f:
            f.write(config_content.strip() + "\n")
        sftp.close()
        stdin, stdout, stderr = node.ssh.exec_command("systemctl restart rsyslog")
        exit_status = stdout.channel.recv_exit_status()
        if exit_status == 0:
            print(f"✅ rsyslog настроен на удалённой ноде {node.name}.")
        else:
            err = stderr.read().decode()
            print(f"❌ Ошибка перезапуска rsyslog на {node.name}: {err}")
    except Exception as e:
        print(f"❌ Ошибка настройки rsyslog на {node.name}: {e}")

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
