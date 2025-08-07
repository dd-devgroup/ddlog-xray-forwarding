import subprocess

def setup_central_rsyslog():
    import os
    if os.geteuid() != 0:
        print("⚠️ Для настройки центрального rsyslog нужно запускать скрипт с правами root.")
        return

    conf_path = "/etc/rsyslog.d/10-remote-xray.conf"
    conf_content = """
module(load="imtcp")
input(type="imtcp" port="514")

if $syslogtag contains 'xray-' then /var/log/xray.log
& stop
"""

    try:
        with open(conf_path, "w", encoding="utf-8") as f:
            f.write(conf_content)
        print(f"✅ Конфиг центрального rsyslog записан в {conf_path}")

        subprocess.run(["systemctl", "restart", "rsyslog"], check=True)
        print("✅ rsyslog на центральном сервере перезапущен и готов принимать логи.")
    except Exception as e:
        print(f"❌ Ошибка при настройке центрального rsyslog: {e}")

def setup_remote_rsyslog(node, central_host):
    """Настройка rsyslog на удалённой ноде для отправки логов на центральный сервер."""

    # Установка rsyslog
    stdin, stdout, stderr = node.ssh.exec_command("apt update && apt install -y rsyslog")
    stdout.channel.recv_exit_status()

    conf_template = f"""
module(load="imfile")

input(type="imfile"
    File="/var/log/supervisor/xray.out.log"
    Tag="xray-{node.name}"
    Severity="info"
    Facility="local7"
    PersistStateInterval="200"
    PollingInterval="1")

*.* @@{central_host}:514
"""

    remote_path = f"/etc/rsyslog.d/30-xray-{node.name}.conf"
    sftp = node.ssh.open_sftp()
    with sftp.file(remote_path, "w") as f:
        f.write(conf_template)
    sftp.close()

    node.ssh.exec_command("systemctl restart rsyslog")
