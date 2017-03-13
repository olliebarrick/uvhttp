from uvhttp.utils import start_loop
import uvhttp.http
import uvhttp.pool
import asyncio
import functools
import time

STATUS_404 = b'HTTP/1.1 404 Not Found'
STATUS_200 = b'HTTP/1.1 200 OK'
STATUS_301 = b'HTTP/1.1 301 Moved Permanently'

@start_loop
async def test_http_request(loop):
    pool_available = asyncio.Semaphore(1, loop=loop)

    conn = uvhttp.pool.Connection('127.0.0.1', 80, pool_available, loop)
    await conn.lock.acquire()

    assert conn.lock.locked()

    request = uvhttp.http.HTTPRequest(conn)
    await request.send(b'HEAD', b'/')
    response = await request.body()
    assert response[:len(STATUS_200)] == STATUS_200

    assert not conn.lock.locked()

@start_loop
async def test_http_connection_reuse(loop):
    pool_available = asyncio.Semaphore(1, loop=loop)

    conn = uvhttp.pool.Connection('127.0.0.1', 80, pool_available, loop)

    # Send an HTTP request
    await conn.lock.acquire()
    assert conn.lock.locked()

    request = uvhttp.http.HTTPRequest(conn)
    await request.send(b'HEAD', b'/')
    response = await request.body()
    assert response[:len(STATUS_200)] == STATUS_200

    assert not conn.lock.locked()

    # Send another HTTP request
    await conn.lock.acquire()
    assert conn.lock.locked()

    request = uvhttp.http.HTTPRequest(conn)
    await request.send(b'GET', b'/lol')
    response = await request.body()
    assert response[:len(STATUS_404)] == STATUS_404

    assert not conn.lock.locked()

    assert conn.connect_count == 1

@start_loop
async def test_session(loop):
    session = uvhttp.http.Session(1, loop)

    for _ in range(5):
        request = await session.request(b'HEAD', b'http://127.0.0.1/')
        response = await request.body()
        assert response[:len(STATUS_200)] == STATUS_200

        request = await session.request(b'GET', b'http://127.0.0.1/lol')
        response = await request.body()
        assert response[:len(STATUS_404)] == STATUS_404

        request = await session.request(b'GET', b'http://www.google.com/')
        response = await request.body()
        assert response[:len(STATUS_301)] == STATUS_301

    assert await session.connections() == 2

@start_loop
async def test_session_low_keepalives(loop):
    session = uvhttp.http.Session(1, loop)

    for _ in range(6):
        request = await session.request(b'HEAD', b'http://127.0.0.1/low_keepalive')
        response = await request.body()
        if not response:
            continue

        assert response[:len(STATUS_200)] == STATUS_200

    assert await session.connections() == 2

@start_loop
async def test_session_benchmark(loop):
    num_requests = 20000

    async def do_request(session):
        request = await session.request(b'HEAD', b'http://127.0.0.1/')
        response = await request.body()
        assert response[:len(STATUS_200)] == STATUS_200

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
