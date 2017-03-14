from uvhttp.utils import start_loop
import uvhttp.http
import uvhttp.pool
import asyncio
import functools
import time
import hashlib
import zlib

MD5_404 = '9ba2182fb48f050de4fe3d1b36dd4075'

def md5(data):
    return hashlib.md5(data).hexdigest()

@start_loop
async def test_http_request(loop):
    pool_available = asyncio.Semaphore(1, loop=loop)

    conn = uvhttp.pool.Connection('127.0.0.1', 80, pool_available, loop)
    conn.locked = True

    assert conn.locked

    request = uvhttp.http.HTTPRequest(conn)
    await request.send(b'HEAD', b'127.0.0.1', b'/')
    assert request.status_code == 200

    assert b"nginx" in request.headers[b"Server"]

    assert not conn.locked

@start_loop
async def test_gzipped_http_request(loop):
    pool_available = asyncio.Semaphore(1, loop=loop)

    conn = uvhttp.pool.Connection('127.0.0.1', 80, pool_available, loop)

    for _ in range(6):
        conn.locked = True

        assert conn.locked

        request = uvhttp.http.HTTPRequest(conn)
        await request.send(b'GET', b'127.0.0.1', b'/index.html', headers={
            b'Accept-Encoding': b'gzip'
        })

        assert request.status_code == 200

        assert b'nginx' in request.headers[b'Server']
        assert b'gzip' in request.headers[b'Content-Encoding']

        assert md5(request.text.encode()) == 'e3eb0a1df437f3f97a64aca5952c8ea0'

        assert not conn.locked

@start_loop
async def test_http_connection_reuse(loop):
    pool_available = asyncio.Semaphore(1, loop=loop)

    conn = uvhttp.pool.Connection('127.0.0.1', 80, pool_available, loop)

    # Send an HTTP request
    conn.locked = True
    assert conn.locked

    request = uvhttp.http.HTTPRequest(conn)
    await request.send(b'HEAD', b'127.0.0.1', b'/')
    assert request.status_code == 200

    assert not conn.locked

    # Send another HTTP request
    conn.locked = True
    assert conn.locked

    request = uvhttp.http.HTTPRequest(conn)
    await request.send(b'GET', b'127.0.0.1', b'/lol')
    assert request.status_code == 404
    assert md5(request.content) == MD5_404

    assert not conn.locked

    assert conn.connect_count == 1

@start_loop
async def test_session(loop):
    session = uvhttp.http.Session(1, loop)

    for _ in range(5):
        try:
            response = await session.request(b'HEAD', b'http://127.0.0.1/')
            assert response.status_code == 200
        except uvhttp.http.EOFError:
            pass

        try:
            response = await session.request(b'GET', b'http://127.0.0.1/lol')
            assert response.status_code == 404
            assert md5(response.content) == MD5_404
        except uvhttp.http.EOFError:
            pass

        try:
            response = await session.request(b'GET', b'http://www.google.com/')
            assert response.status_code == 302
            assert b"The document has moved" in response.content
        except uvhttp.http.EOFError:
            pass

        try:
            response = await session.request(b'GET', b'http://imgur.com/')
            assert response.status_code == 200
            assert len(response.content) > 100000
        except uvhttp.http.EOFError:
            pass

        try:
            response = await session.request(b'GET', b'http://imgur.com/', headers={
                b"Accept-Encoding": b"gzip"
            })
            assert response.status_code == 200
            assert len(response.content) > 10000
        except uvhttp.http.EOFError:
            pass

    assert await session.connections() == 3

@start_loop
async def test_session_low_keepalives(loop):
    session = uvhttp.http.Session(1, loop)

    for _ in range(6):
        try:
            response = await session.request(b'HEAD', b'http://127.0.0.1/low_keepalive')
        except uvhttp.http.EOFError:
            continue

        assert response.status_code == 200

    assert await session.connections() == 2

@start_loop
async def test_session_benchmark(loop):
    num_requests = 20000

    async def do_request(session):
        response = await session.request(b'HEAD', b'http://127.0.0.1/')
        assert response.status_code == 200

    session = uvhttp.http.Session(10, loop)
    start_time = time.time()

    tasks = []
    for j in range(num_requests):
        task = do_request(session)
        task = asyncio.ensure_future(task)
        tasks.append(task)

    await asyncio.wait(tasks)

    duration = time.time() - start_time
    print('Test time: {}s, {} rps'.format(duration, num_requests / duration))

    assert await session.connections() == 10

@start_loop
async def test_json_body(loop):
    session = uvhttp.http.Session(10, loop)

    response = await session.request(b'GET', b'http://127.0.0.1/test.json')

    assert response.json() == [{"this is a json": "Body!"}]
