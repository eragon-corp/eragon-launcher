# Optional integration check: downloads the real bridge; no inference or Memory calls.
import json
import os
import pathlib
import selectors
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="eragon-memory-check-") as taskdir:
    root = pathlib.Path(taskdir)
    bindir = root / "bin"
    bindir.mkdir()
    stub = """#!/usr/bin/env python3
import json, os, pathlib, sys, shutil
name = pathlib.Path(sys.argv[0]).name
if sys.argv[1:] == ['--version']:
    print({'claude':'2.1.302','codex':'codex-cli 0.160.0','pi':'1.0.0','opencode':'1.3.7'}[name]); sys.exit(0)
if sys.argv[1:] == ['--help']:
    print('--no-mcp'); sys.exit(0)
assert all('fixture-secret' not in arg for arg in sys.argv)
if name == 'claude' and sys.argv[1] == 'mcp':
    config = pathlib.Path(os.environ['CLAUDE_CONFIG_DIR']) / 'mcp-check.json'
    if sys.argv[2] == 'add':
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps(sys.argv[1:]))
    sys.exit(0)
if name == 'claude': assert os.environ['ANTHROPIC_AUTH_TOKEN'] == 'fixture-secret'
else: assert os.environ['ERAGON_API_KEY'] == os.environ['ERAGON_ROUTER_TOKEN'] == 'fixture-secret'
assert shutil.which('eragon-context-mcp') is not None
print('CLIENT_STARTED')
"""
    for client in ['claude','codex','pi','opencode']:
        path = bindir / client
        path.write_text(stub)
        path.chmod(0o700)
    env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ['PATH'],
               HOME=str(root), XDG_DATA_HOME=str(root/'data'), XDG_CONFIG_HOME=str(root/'config'),
               CODEX_HOME=str(root/'codex'), PI_CODING_AGENT_DIR=str(root/'pi'),
               CLAUDE_CONFIG_DIR=str(root/'claude'), TMPDIR=str(root), ERAGON_API_KEY='fixture-secret')
    for key in ['ERAGON_COMPATIBILITY_FILE','ERAGON_CONTEXT_WINDOW','ERAGON_MODEL','ERAGON_ENDPOINT','ERAGON_CLIENT','ERAGON_GATEWAY_URL','ERAGON_ROUTER_TOKEN','ANTHROPIC_BASE_URL','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_API_KEY','OPENAI_API_KEY']:
        env.pop(key, None)
    (root/'codex').mkdir()
    (root/'codex'/'config.toml').write_text('model = "keep-model"\n[mcp_servers.keep]\ncommand = "keep-command"\n')
    (root/'pi').mkdir()
    (root/'pi'/'mcp.json').write_text(json.dumps({'mcpServers':{'keep':{'command':'keep-command'}}}))
    (root/'config'/'opencode').mkdir(parents=True)
    (root/'config'/'opencode'/'opencode.json').write_text(json.dumps({'provider':{'keep':{'name':'Keep provider'}}}))
    for client in ['claude','codex','pi','opencode']:
        result = subprocess.run(['/bin/bash',str(ROOT/'eragon.sh'),'--client',client,
            '--endpoint','https://gateway.example.com/gw','--model','coder','--memory'],
            env=env,cwd=root,input='',capture_output=True,text=True,timeout=180)
        assert result.returncode == 0, client + ': ' + (result.stdout + result.stderr).replace('fixture-secret','[REDACTED]')[-2000:]
        assert 'CLIENT_STARTED' in result.stdout
        if client != 'claude': assert 'Installing Eragon Memory locally' not in result.stdout
        print(client + ': real installer registered the selected client; cached bridge reused after first install.')
    skipped = subprocess.run(['/bin/bash',str(ROOT/'eragon.sh'),'--client','codex',
        '--endpoint','https://gateway.example.com/gw','--model','coder'],env=env,cwd=root,
        input='',capture_output=True,text=True,timeout=30)
    assert skipped.returncode == 0 and 'CLIENT_STARTED' in skipped.stdout
    assert 'configured' not in skipped.stdout
    print('Cached bridge remains available on a later launch that skips setup.')
    codex = (root/'codex'/'config.toml').read_text()
    assert '[mcp_servers.eragon]' in codex and 'env_vars = ["ERAGON_API_KEY"]' in codex
    assert 'model = "keep-model"' in codex and '[mcp_servers.keep]' in codex
    pi = json.loads((root/'pi'/'mcp.json').read_text())
    assert pi['mcpServers']['eragon']['exposure'] == 'direct'
    assert pi['mcpServers']['keep']['command'] == 'keep-command'
    opencode = json.loads((root/'config'/'opencode'/'opencode.json').read_text())
    assert opencode['mcp']['eragon']['enabled'] is True
    assert opencode['provider'] == {'keep':{'name':'Keep provider'}}
    assert not (root/'pi'/'models.json').exists()
    for path in [root/'codex'/'config.toml',root/'pi'/'mcp.json',root/'config'/'opencode'/'opencode.json',root/'claude'/'mcp-check.json']:
        assert 'fixture-secret' not in path.read_text()
    reconnect = subprocess.run(['/bin/bash',str(ROOT/'eragon.sh'),'--client','codex',
        '--endpoint','https://other.example/gw','--model','coder','--memory'],env=env,cwd=root,
        input='',capture_output=True,text=True,timeout=30)
    assert reconnect.returncode == 0
    updated = (root/'codex'/'config.toml').read_text()
    assert 'https://other.example/gw' in updated and 'https://gateway.example.com/gw' not in updated
    assert '[mcp_servers.keep]' in updated and 'fixture-secret' not in updated
    assert (root/'codex'/'config.toml.eragon-backup').exists()
    print('Existing configuration preserved; reconnect refreshed the Gateway URL with a backup.')
    binary = root/'data' /'eragon-router'/'memory'/'node_modules'/'.bin'/'eragon-context-mcp'
    process = subprocess.Popen([str(binary),'--url','https://gateway.example.com/gw'],env=env,cwd=root,
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout,selectors.EVENT_READ)
    def send(message):
        process.stdin.write(json.dumps(message)+'\n'); process.stdin.flush()
    def receive():
        assert selector.select(15), 'MCP response timeout'
        return json.loads(process.stdout.readline())
    try:
        send({'jsonrpc':'2.0','id':1,'method':'initialize','params':{
            'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'router-check','version':'1'}}})
        reply = receive()
        assert reply['id'] == 1 and 'result' in reply
        send({'jsonrpc':'2.0','method':'notifications/initialized'})
        send({'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}})
        reply = receive()
        assert {tool['name'] for tool in reply['result']['tools']} == {'memory_search','memory_save','memory_share'}
        print('Real MCP bridge initialized and exposed all three tools. No Memory data or inference requests sent.')
    finally:
        selector.close(); process.terminate(); process.communicate(timeout=10)
