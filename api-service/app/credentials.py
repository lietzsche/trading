import base64
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException

PREFIX='fernet:v1:'

def key_cipher(secret, user_id):
    if len(secret)<32:raise HTTPException(503,'서버 암호화 설정을 확인해 주세요.')
    key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'trading-ai-credentials-v1',
             info=f'deepseek-owner:{user_id}'.encode()).derive(secret.encode())
    return Fernet(base64.urlsafe_b64encode(key))

def encrypt_upbit(secret, owner, value):
    return PREFIX+key_cipher(secret,f'upbit:{owner}').encrypt(value.encode()).decode()

def upbit_credentials(secret, owner, row):
    """The only Upbit decrypt boundary; never replace the stored comparison values."""
    result=[]
    for field in ('access_key','secret_key'):
        value=row[field]
        if value.startswith(PREFIX):
            try:value=key_cipher(secret,f'upbit:{owner}').decrypt(value[len(PREFIX):].encode()).decode()
            except InvalidToken:raise HTTPException(503,'Upbit 키를 다시 등록해 주세요.') from None
        result.append(value)
    return tuple(result)

def migrate_upbit_credentials(database,secret):
    converted=0
    with database.connection() as connection,connection.cursor() as cursor:
        cursor.execute('SELECT id,user_login_id,access_key,secret_key FROM tb_upbit_key FOR UPDATE')
        for row in cursor.fetchall():
            values=[row[field] if row[field].startswith(PREFIX) else encrypt_upbit(secret,row['user_login_id'],row[field])
                    for field in ('access_key','secret_key')]
            if values!=[row['access_key'],row['secret_key']]:
                cursor.execute('UPDATE tb_upbit_key SET access_key=%s,secret_key=%s WHERE id=%s',(*values,row['id']))
                converted+=1
    return converted
