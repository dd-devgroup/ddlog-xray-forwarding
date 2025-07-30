# ddlog-xray-forwarding.bin.spec

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'paramiko',
        'cryptography',
        'cryptography.hazmat.bindings._openssl',
        'bcrypt',
        'six',
        'paramiko.transport',
        'paramiko.ssh_exception',
        'paramiko.message',
        'paramiko.rsakey',
        'paramiko.dsskey',
        'paramiko.ecdsakey',
        'paramiko.agent',
        'paramiko.pkey',
        'paramiko.py3compat',
        'paramiko.common',
        'paramiko.buffered_pipe',
        'paramiko.sftp',
        'paramiko.sftp_client',
        'paramiko.sftp_attr',
        'paramiko.sftp_server',
        'paramiko.sftp_handle',
        'paramiko.sftp_file',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,        # Включаем бинарники сюда
    exclude_binaries=False,  # Обязательно False
    name='ddlog-xray-forwarding.bin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

