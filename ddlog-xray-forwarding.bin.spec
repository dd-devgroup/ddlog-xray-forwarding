block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'encodings',
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
    noarchive=True,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # ВАЖНО
    name='ddlog-xray-forwarding.bin',
    debug=False,
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
    name='ddlog-xray-forwarding.bin',
)
