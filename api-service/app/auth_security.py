import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException


def authenticate(database, login_id, ip, verify):
    """Serialize both scopes; commit failure counts before returning an HTTP error."""
    scopes = [('id', login_id), ('ip', ip)]
    now = datetime.now(timezone.utc)
    with database.connection() as connection, connection.cursor() as cursor:
        for scope, value in sorted(scopes):
            digest = int.from_bytes(hashlib.sha256(f'auth:{scope}:{value}'.encode()).digest()[:8], 'big', signed=True)
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', (digest,))
        rows = []
        for scope, value in scopes:
            cursor.execute('SELECT * FROM auth_attempts WHERE scope=%s AND subject=%s FOR UPDATE', (scope,value))
            row = cursor.fetchone()
            if row and row['locked_until'] and row['locked_until'] > now:
                raise HTTPException(429, '잠시 후 다시 시도')
            rows.append(row)
        user = verify()
        if user:
            cursor.execute("DELETE FROM auth_attempts WHERE scope='id' AND subject=%s", (login_id,))
        else:
            for (scope,value),row in zip(scopes,rows):
                fresh = not row or row['window_started_at'] <= now-timedelta(minutes=15)
                failures = 1 if fresh else row['failures']+1
                start = now if fresh else row['window_started_at']
                threshold = 20 if scope == 'id' else 5
                locked_until = now+timedelta(minutes=15) if failures >= threshold else None
                cursor.execute('''INSERT INTO auth_attempts(scope,subject,failures,window_started_at,locked_until)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT(scope,subject) DO UPDATE SET
                    failures=EXCLUDED.failures,window_started_at=EXCLUDED.window_started_at,
                    locked_until=EXCLUDED.locked_until''', (scope,value,failures,start,locked_until))
    return user
