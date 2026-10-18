# Test fixtures only. No real credentials or network requests.

import os, sys, json, tempfile, pathlib, pty, select, time, termios, subprocess
request = json.load(sys.stdin)
with tempfile.TemporaryDirectory() as directory:
    root = pathlib.Path(directory)
    (root / "eragon.sh").write_text(request["script"])
    curl = root / "curl"
    curl.write_text(r"""#!/usr/bin/env python3
import os, sys
assert all('fixture-secret' not in arg for arg in sys.argv)
assert os.environ.get('EXPECT_NO_CATALOGUE') != '1'
assert sys.argv[1] == '-q'
assert sys.argv[sys.argv.index('--url') + 1] == os.environ['EXPECTED_ENDPOINT'] + '/v1/models'
assert '--location' not in sys.argv and '-L' not in sys.argv
assert sys.stdin.read() == 'Authorization: Bearer fixture-secret\n'
assert 'eragon_key' not in os.environ
assert 'ERAGON_API_KEY' not in os.environ
if os.environ.get('CURL_FAIL') == '1': sys.exit(22)
print(os.environ['MODEL_RESPONSE'])
""")
    claude = root / "claude"
    claude.write_text("""#!/usr/bin/env python3
import os, sys, json
assert os.environ['ANTHROPIC_AUTH_TOKEN'] == 'fixture-secret'
assert 'ANTHROPIC_API_KEY' not in os.environ
assert 'ERAGON_API_KEY' not in os.environ
assert 'eragon_key' not in os.environ
assert 'ERAGON_API_KEY' not in os.environ
assert 'CLAUDE_CODE_DISABLE_THINKING' not in os.environ
assert sys.argv[3] == '--settings'
settings = json.loads(sys.argv[4])
assert settings == {'env': {'ANTHROPIC_BASE_URL': os.environ['EXPECTED_ENDPOINT']}}
assert all('fixture-secret' not in arg for arg in sys.argv)
print('LAUNCHED ' + json.dumps({'model': sys.argv[2], 'url': settings['env']['ANTHROPIC_BASE_URL']}))
""")
    for path in [curl, claude]: path.chmod(0o700)
    environment = dict(os.environ, PATH=directory + os.pathsep + os.environ['PATH'],
        MODEL_RESPONSE=request['models'], CURL_FAIL=str(request.get('curlFail', 0)),
        ANTHROPIC_API_KEY='stale', CLAUDE_CODE_DISABLE_THINKING='1')
    # Do not accidentally use credentials/config from the developer's shell.
    for name in ['ERAGON_API_KEY', 'ERAGON_ENDPOINT', 'ERAGON_MODEL', 'eragon_key', 'endpoint', 'selected']:
        environment.pop(name, None)
    if request.get('provideEndpoint', True):
        environment['ERAGON_ENDPOINT'] = 'https://gateway.example.com/gw'
    environment.update(request.get('environment', {}))
    environment['EXPECTED_ENDPOINT'] = request.get('expectedEndpoint', 'https://gateway.example.com/gw')
    environment['EXPECT_NO_CATALOGUE'] = str(request.get('noCatalogue', 0))
    arguments = ['bash'] + request.get('bashOptions', ['-x']) + ['eragon.sh'] + request.get('args', [])
    if request.get('noninteractive'):
        result = subprocess.run(arguments, cwd=directory, env=environment,
                                input='', capture_output=True, text=True, timeout=8)
        assert sorted(path.name for path in root.iterdir()) == ['claude', 'curl', 'eragon.sh']
        print(json.dumps({'exit': result.returncode, 'output': result.stdout + result.stderr}))
        sys.exit(0)
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(directory)
        os.execvpe('bash', arguments, environment)
    transcript = b''
    sent_key = False
    choices = iter(request.get('choices', ['']))
    prompts_seen = 0
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], .1)
        if not ready: continue
        try: chunk = os.read(fd, 65536)
        except OSError: break
        if not chunk: break
        transcript += chunk
        if b'Personal API Key: ' in transcript and not sent_key:
            os.write(fd, b'\x03' if request.get('interrupt') else b'fixture-secret\n'); sent_key = True
        count = transcript.count(b'Model number [1]: ')
        if count > prompts_seen:
            os.write(fd, (next(choices, '') + '\n').encode()); prompts_seen = count
    else:
        os.kill(pid, 9)
        raise RuntimeError('Launcher timed out')
    _, status = os.waitpid(pid, 0)
    assert termios.tcgetattr(fd)[3] & termios.ECHO, "Terminal echo was not restored"
    os.close(fd)
    assert sorted(path.name for path in root.iterdir()) == ['claude', 'curl', 'eragon.sh']
    print(json.dumps({'exit': os.waitstatus_to_exitcode(status), 'output': transcript.decode()}))
