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
print('FIXTURE_CATALOGUE_REQUEST', file=sys.stderr)
print(os.environ['MODEL_RESPONSE'])
""")
    claude = root / "claude"
    claude.write_text("""#!/usr/bin/env python3
import os, sys, json
if sys.argv[1:] == ['--version']:
    print(os.environ.get('FIXTURE_CLAUDE_VERSION', '2.1.302')); sys.exit(0)
assert os.environ['ANTHROPIC_AUTH_TOKEN'] == 'fixture-secret'
assert 'ANTHROPIC_API_KEY' not in os.environ
assert 'ERAGON_API_KEY' not in os.environ
assert 'eragon_key' not in os.environ
assert 'ERAGON_API_KEY' not in os.environ
assert sys.argv[3] == '--settings'
settings = json.loads(sys.argv[4])
expected = {'ANTHROPIC_BASE_URL': os.environ['EXPECTED_ENDPOINT']}
profile = os.environ.get('EXPECTED_PROFILE') or ('native' if sys.argv[2].startswith('claude-') else 'basic')
compat = {'CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS': '1', 'CLAUDE_CODE_DISABLE_THINKING': '1',
          'CLAUDE_CODE_EFFORT_LEVEL': 'auto', 'DISABLE_PROMPT_CACHING': '1'}
if profile == 'basic':
    expected.update(compat)
    for name, value in compat.items(): assert os.environ.get(name) == value
else:
    for name in compat: assert name not in os.environ
capacity = {'CLAUDE_CODE_AUTO_COMPACT_WINDOW': os.environ['CLAUDE_CODE_AUTO_COMPACT_WINDOW'],
            'CLAUDE_CODE_MAX_OUTPUT_TOKENS': os.environ['CLAUDE_CODE_MAX_OUTPUT_TOKENS'],
            'CLAUDE_AUTOCOMPACT_PCT_OVERRIDE': '90', 'DISABLE_COMPACT': '', 'DISABLE_AUTO_COMPACT': ''}
expected.update(capacity)
assert settings == {'env': expected}
assert 'DISABLE_COMPACT' not in os.environ
assert 'DISABLE_AUTO_COMPACT' not in os.environ
print('CAPACITY ' + json.dumps(capacity))
assert all('fixture-secret' not in arg for arg in sys.argv)
print('LAUNCHED ' + json.dumps({'model': sys.argv[2], 'url': settings['env']['ANTHROPIC_BASE_URL']}))
""")
    codex = root / "codex"
    codex.write_text("""#!/usr/bin/env python3
import os, sys, json
if sys.argv[1:] == ['--version']:
    print(os.environ.get('FIXTURE_CODEX_VERSION', 'codex-cli 0.160.0')); sys.exit(0)
assert os.environ['ERAGON_ROUTER_TOKEN'] == 'fixture-secret'
assert os.environ['ERAGON_API_KEY'] == os.environ['ERAGON_ROUTER_TOKEN']
assert os.environ['ERAGON_GATEWAY_URL'] == os.environ['EXPECTED_ENDPOINT']
for key in ['eragon_key', 'ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY']:
    assert key not in os.environ, key
assert all('fixture-secret' not in arg for arg in sys.argv)
assert sys.argv[1] == '--no-daemon' and sys.argv[2] == '--model'
assert all(sys.argv[i] == '-c' for i in range(4,len(sys.argv),2))
values = dict(arg.split('=', 1) for arg in sys.argv[5::2])
assert values['model_provider'] == '\"eragon_router\"'
provider = values['model_providers.eragon_router']
assert 'base_url=\"' + os.environ['EXPECTED_ENDPOINT'] + '/v1\"' in provider
assert 'env_key=\"ERAGON_ROUTER_TOKEN\"' in provider
assert 'wire_api=\"responses\"' in provider
assert 'requires_openai_auth=false' in provider
assert 'supports_websockets=false' in provider
assert 'fixture-secret' not in provider
assert values['web_search'] == '\"disabled\"'
assert values['model_auto_compact_token_limit_scope'] == '\"total\"'
context = int(values['model_context_window'])
assert int(values['model_auto_compact_token_limit']) == context // 5 * 4
print('CODEX_LAUNCHED ' + json.dumps({'model': sys.argv[3], 'context': context, 'config': values}))
""")
    pi = root / "pi"
    pi.write_text("""#!/usr/bin/env python3
import os, sys, json, pathlib
if sys.argv[1:] == ['--version']:
    print(os.environ.get('FIXTURE_PI_VERSION', '0.73.1'), file=sys.stderr); sys.exit(0)
assert os.environ['ERAGON_ROUTER_TOKEN'] == 'fixture-secret'
assert os.environ['ERAGON_API_KEY'] == os.environ['ERAGON_ROUTER_TOKEN']
assert os.environ['ERAGON_GATEWAY_URL'] == os.environ['EXPECTED_ENDPOINT']
for name in ['eragon_key','ANTHROPIC_BASE_URL','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_API_KEY','OPENAI_API_KEY']:
    assert name not in os.environ, name
assert all('fixture-secret' not in arg for arg in sys.argv)
assert sys.argv[1] == '--extension' and sys.argv[3:5] == ['--provider','eragon_router']
source = pathlib.Path(sys.argv[2]).read_text()
assert 'fixture-secret' not in source and 'registerProvider' in source
assert 'process.env.ERAGON_ROUTER_PI_CONFIG' in source
config = json.loads(os.environ['ERAGON_ROUTER_PI_CONFIG'])
assert 'fixture-secret' not in json.dumps(config)
assert config['baseUrl'] == os.environ['EXPECTED_ENDPOINT'] + '/v1'
assert config['api'] == 'openai-completions'
assert config['apiKey'] == ('$ERAGON_ROUTER_TOKEN' if int(os.environ.get('FIXTURE_PI_VERSION','0.73.1').split('.')[0]) >= 1 else 'ERAGON_ROUTER_TOKEN')
assert config['models'][0]['id'] == sys.argv[6]
assert sys.argv[7:] == ['--thinking', 'off']
print('PI_LAUNCHED ' + json.dumps(config))
sys.exit(int(os.environ.get('FIXTURE_PI_EXIT', '0')))
""")
    opencode = root / "opencode"
    opencode.write_text("""#!/usr/bin/env python3
import os, sys, json
if sys.argv[1:] == ['--version']:
    print(os.environ.get('FIXTURE_OPENCODE_VERSION', '1.3.7')); sys.exit(0)
assert os.environ['ERAGON_ROUTER_TOKEN'] == 'fixture-secret'
assert os.environ['ERAGON_API_KEY'] == os.environ['ERAGON_ROUTER_TOKEN']
assert os.environ['ERAGON_GATEWAY_URL'] == os.environ['EXPECTED_ENDPOINT']
for name in ['eragon_key','ANTHROPIC_BASE_URL','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_API_KEY','OPENAI_API_KEY']:
    assert name not in os.environ, name
assert all('fixture-secret' not in arg for arg in sys.argv)
config = json.loads(os.environ['OPENCODE_CONFIG_CONTENT'])
assert 'fixture-secret' not in json.dumps(config)
assert sys.argv[1] == '--model' and sys.argv[2] == config['model'] == config['small_model']
p = config['provider']['eragon_router']
assert p['npm'] == '@ai-sdk/openai-compatible'
assert p['options'] == {'baseURL':os.environ['EXPECTED_ENDPOINT'] + '/v1','apiKey':'{env:ERAGON_ROUTER_TOKEN}'}
model = p['models'][sys.argv[2].split('/',1)[1]]
assert model['limit']['output'] <= model['limit']['context'] // 4
assert config['compaction']['auto'] is True
assert config['compaction']['reserved'] == model['limit']['context'] - model['limit']['context'] // 5 * 4
print('OPENCODE_LAUNCHED ' + json.dumps(config))
""")
    memory_bridge = root / 'memory-bridge.py'
    memory_bridge.write_text("import os, sys\nassert os.environ['ERAGON_API_KEY'] == 'fixture-secret'\nassert sys.argv[1] == '--url'\nassert sys.argv[2] == " + repr(request.get('expectedEndpoint', 'https://gateway.example.com/gw')) + "\nassert 'ANTHROPIC_BASE_URL' not in os.environ\nprint('MEMORY_CHILD_AUTH_MATCHED')\n")
    for client_path in [codex, pi, opencode]:
        source = client_path.read_text()
        # Exercise a real subprocess; Codex forwards only the installed bridge's
        # env_vars allowlist, while the Gateway URL is an explicit --url argument.
        check = """
if os.environ.get('CHECK_MEMORY_CHILD') == '1':
    import subprocess, pathlib
    child_env = ({'ERAGON_API_KEY':os.environ['ERAGON_API_KEY']} if pathlib.Path(__file__).name == 'codex' else dict(os.environ))
    subprocess.run([sys.executable, str(pathlib.Path(__file__).with_name('memory-bridge.py')),
                    '--url', os.environ['ERAGON_GATEWAY_URL']], env=child_env, check=True)
"""
        source = source.replace("assert os.environ['ERAGON_ROUTER_TOKEN'] == 'fixture-secret'", "assert os.environ['ERAGON_ROUTER_TOKEN'] == 'fixture-secret'\n" + check, 1)
        client_path.write_text(source)
    for path in [curl, claude, codex, pi, opencode]: path.chmod(0o700)
    environment = dict(os.environ, PATH=directory + os.pathsep + os.environ['PATH'],
        MODEL_RESPONSE=request['models'], CURL_FAIL=str(request.get('curlFail', 0)),
        ANTHROPIC_API_KEY='stale', CLAUDE_CODE_DISABLE_THINKING='1')
    # Do not accidentally use credentials/config from the developer's shell.
    for name in ['ERAGON_API_KEY', 'ERAGON_ENDPOINT', 'ERAGON_MODEL', 'eragon_key', 'endpoint', 'selected', 'ERAGON_COMPATIBILITY_FILE', 'ERAGON_CONTEXT_WINDOW', 'CLAUDE_CODE_AUTO_COMPACT_WINDOW', 'CLAUDE_CODE_MAX_OUTPUT_TOKENS', 'CLAUDE_AUTOCOMPACT_PCT_OVERRIDE', 'FIXTURE_CLAUDE_VERSION', 'FIXTURE_CODEX_VERSION', 'ERAGON_CLIENT', 'ERAGON_ROUTER_TOKEN', 'ERAGON_GATEWAY_URL', 'CHECK_MEMORY_CHILD', 'ERAGON_ROUTER_PI_CONFIG', 'OPENCODE_CONFIG_CONTENT', 'FIXTURE_PI_VERSION', 'FIXTURE_OPENCODE_VERSION', 'FIXTURE_PI_EXIT']:
        environment.pop(name, None)
    if request.get('provideEndpoint', True):
        environment['ERAGON_ENDPOINT'] = 'https://gateway.example.com/gw'
    environment.update(request.get('environment', {}))
    environment['EXPECTED_ENDPOINT'] = request.get('expectedEndpoint', 'https://gateway.example.com/gw')
    environment['CHECK_MEMORY_CHILD'] = '1' if request.get('checkMemoryChild') else '0'
    environment['EXPECT_NO_CATALOGUE'] = str(request.get('noCatalogue', 0))
    environment['EXPECTED_PROFILE'] = request.get('expectedProfile', '')
    environment['TMPDIR'] = directory
    environment['XDG_CONFIG_HOME'] = str(root / 'config')
    credential_dir = root / 'config' / 'eragon-router'
    credential_file = credential_dir / 'credentials.json'
    if 'savedCredentials' in request:
        credential_dir.mkdir(parents=True, mode=0o700)
        credential_file.write_text(json.dumps(request['savedCredentials']))
        credential_file.chmod(0o600)
    if request.get('symlinkCredentials'):
        credential_dir.mkdir(parents=True, mode=0o700)
        credential_file.symlink_to(root / 'eragon.sh')
    def inspect_storage():
        result = {}
        if credential_file.exists() and not credential_file.is_symlink():
            saved = json.loads(credential_file.read_text())
            if 'expectedSavedKeys' in request:
                assert saved['keys'] == request['expectedSavedKeys']
            else:
                assert all(value == 'fixture-secret' for value in saved['keys'].values())
            assert credential_file.stat().st_mode & 0o777 == 0o600
            assert credential_dir.stat().st_mode & 0o777 == 0o700
            result['savedEndpoints'] = sorted(saved['keys'])
            result['lastEndpoint'] = saved['last_endpoint']
        if request.get('relaunch'):
            again = subprocess.run(arguments, cwd=directory, env=environment,
                                   input='', capture_output=True, text=True, timeout=8)
            assert again.returncode == 0, again.stdout + again.stderr
            assert 'Personal API Key' not in again.stdout
            result['reloaded'] = True
        return result

    expected_files = ['claude', 'codex', 'curl', 'eragon.sh', 'pi', 'opencode', 'memory-bridge.py']
    if request.get('expectStorage') or 'savedCredentials' in request or request.get('symlinkCredentials'):
        expected_files.append('config')
    if 'manifest' in request:
        manifest_path = root / 'compatibility.json'
        manifest_path.write_text(json.dumps(request['manifest']))
        environment['ERAGON_COMPATIBILITY_FILE'] = str(manifest_path)
        expected_files.append('compatibility.json')
    arguments = ['/bin/bash'] + request.get('bashOptions', ['-x']) + ['eragon.sh'] + request.get('args', [])
    if request.get('noninteractive'):
        result = subprocess.run(arguments, cwd=directory, env=environment,
                                input='', capture_output=True, text=True, timeout=8)
        assert sorted(path.name for path in root.iterdir()) == sorted(expected_files)
        print(json.dumps({'exit': result.returncode, 'output': result.stdout + result.stderr, **inspect_storage()}))
        sys.exit(0)
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(directory)
        os.execvpe(arguments[0], arguments, environment)
    transcript = b''
    sent_key = False
    choices = iter(request.get('choices', ['']))
    prompts_seen = 0
    client_choices = iter(request.get('clientChoices', ['']))
    client_prompts_seen = 0
    sent_gateway = False
    sent_remember = False
    key_actions = iter(request.get("keyActions", [""]))
    key_prompts_seen = 0
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], .1)
        if not ready: continue
        try: chunk = os.read(fd, 65536)
        except OSError: break
        if not chunk: break
        transcript += chunk
        if not sent_gateway and (b'Gateway URL: ' in transcript or b'Gateway URL [saved]: ' in transcript):
            os.write(fd, (request.get('gatewayInput', '') + '\n').encode()); sent_gateway = True
        if not sent_remember and b'Remember API key locally (owner-only plaintext file)? [y/N]: ' in transcript:
            os.write(fd, (request.get('rememberChoice', '') + '\n').encode()); sent_remember = True
        key_count = transcript.count(b'Key action [1]: ')
        if key_count > key_prompts_seen:
            action = next(key_actions, '')
            os.write(fd, b'\x03' if action == 'INTERRUPT' else (action + '\n').encode())
            key_prompts_seen = key_count
        client_count = transcript.count(b'Client number [1]: ')
        if client_count > client_prompts_seen:
            os.write(fd, (next(client_choices, '') + '\n').encode()); client_prompts_seen = client_count
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
    assert sorted(path.name for path in root.iterdir()) == sorted(expected_files)
    print(json.dumps({'exit': os.waitstatus_to_exitcode(status), 'output': transcript.decode(), **inspect_storage()}))
