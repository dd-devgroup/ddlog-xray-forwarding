block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'encodings',  # Явно добавить
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
    noarchive=True,  # переключаем на True для избежания ошибок с encodings
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    exclude_binaries=False,  # нужно включать бинарники в exe
    name='ddlog-xray-forwarding.bin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ddlog-xray-forwarding.bin'
)
