import json
from pathlib import Path
import sys
import shutil
import subprocess

import pytest

from harness.pilots import CodexPilot, PilotPaused
from harness.pilots.codex import isolated_command


@pytest.fixture
def fake(tmp_path):
    script = tmp_path / "fake.py"
    script.write_text('''import json,sys
for line in sys.stdin:
 r=json.loads(line); m=r['method']; p=r.get('params',{}); i=r.get('id')
 mode=__import__('pathlib').Path(__file__).with_suffix('.mode').read_text()
 if m=='thread/resume' and mode=='missing':
  print(json.dumps({'id':i,'error':{'code':-32600,'message':'no rollout found for thread id thread-1'}}),flush=True)
  continue
 if m=='initialized': continue
 if m=='initialize': result={}
 elif m in ('thread/start','thread/resume'): result={'thread':{'id':'thread-1'}}
 elif m=='turn/start':
  d=json.loads(p['input'][0]['text'])
  result={'turn':{'id':'turn-'+d['decision_id']}}
 elif m=='thread/turns/list':
  a=dict(game_id='g1',seat=0,decision_id='d1',state_revision=1,action_id='pass',parameters={})
  result={'data':[{'id':'turn-d1','status':'completed','items':[{'type':'agentMessage','text':json.dumps(a)}]}],'nextCursor':None}
 else: result={}
 print(json.dumps({'id':i,'result':result}),flush=True)
 if m=='turn/start':
  a={k:d[k] for k in ('game_id','seat','decision_id','state_revision')}
  a.update(action_id=d['legal_actions'][0]['action_id'],parameters={})
  mode=__import__('pathlib').Path(__file__).with_suffix('.mode').read_text()
  if mode=='loss': sys.exit(0)
  if mode=='tool-request':
   print(json.dumps({'id':99,'method':'item/tool/call','params':{'name':'exec'}}),flush=True)
   continue
  if mode=='tool-start':
   print(json.dumps({'method':'item/started','params':{'threadId':'thread-1','item':{'type':'commandExecution'}}}),flush=True)
   continue
  if mode=='stale': a['state_revision']+=1
  print(json.dumps({'method':'item/completed','params':{'threadId':'thread-1','item':{'type':'agentMessage','text':json.dumps(a)}}}),flush=True)
  print(json.dumps({'method':'turn/completed','params':{'threadId':'thread-1','turn':{'id':result['turn']['id'],'status':'completed'}}}),flush=True)
''')
    script.with_suffix(".mode").write_text("ok")
    return script


def decision(number="d1", seat=0):
    return dict(protocol_version=1, game_id="g1", seat=seat, decision_id=number,
                state_revision=1, view=dict(public={}, private={}), playbook_version="v1",
                legal_actions=[dict(action_id="pass", label="Pass", parameters_schema=dict(type="object", properties={}, additionalProperties=False))])


def pilot(tmp_path, fake):
    return CodexPilot(tmp_path / "seat", "g1", 0, playbook="Own strategy", playbook_version="v1",
                      command=[sys.executable, str(fake)], timeout=2)


def test_persistent_turns_and_cached_identity(tmp_path, fake):
    with pilot(tmp_path, fake) as seat:
        pid = seat.process.pid
        answer = seat.decide(decision())
        assert seat.decide(decision()) == answer
        seat.decide(decision("d2"))
        assert seat.process.pid == pid
        with pytest.raises(ValueError, match="outside"):
            seat.decide(decision(seat=1))
        changed = decision()
        changed["state_revision"] = 2
        with pytest.raises(ValueError, match="reused"):
            seat.decide(changed)
    with pilot(tmp_path, fake) as seat:
        assert seat.decide(decision()) == answer


@pytest.mark.parametrize("mode", ["loss", "stale", "tool-request", "tool-start"])
def test_failure_preserves_pending_without_retry(tmp_path, fake, mode):
    fake.with_suffix(".mode").write_text(mode)
    with pilot(tmp_path, fake) as seat:
        with pytest.raises(PilotPaused):
            seat.decide(decision())
        assert seat.state["pending"] == decision()
        assert not seat.state["answers"]
    with pilot(tmp_path, fake) as seat:
        with pytest.raises(PilotPaused, match="unresolved"):
            seat.decide(decision())


def test_isolation_mounts_only_own_runtime(tmp_path):
    command = isolated_command(tmp_path)
    assert "--unshare-pid" in command
    assert "--clearenv" in command
    assert command[command.index("--bind") + 1] == str(tmp_path / ".codex")
    assert str(tmp_path) not in command
    assert "/home" not in command
    assert "/proc" in command


def test_uncertain_turn_recovers_from_history_without_new_turn(tmp_path, fake):
    fake.with_suffix(".mode").write_text("loss")
    with pilot(tmp_path, fake) as seat:
        with pytest.raises(PilotPaused):
            seat.decide(decision())
    fake.with_suffix(".mode").write_text("ok")
    with pilot(tmp_path, fake) as seat:
        answer = seat.recover_pending()
        assert answer["decision_id"] == "d1"
        assert seat.state["pending"] is None
        assert seat.decide(decision()) == answer


def test_actual_sandbox_denies_host_sibling_and_referee(tmp_path):
    if not shutil.which("gcc") or not shutil.which("bwrap"):
        pytest.skip("requires static C compiler and rootless bwrap")
    runtime = tmp_path / "own"
    runtime.mkdir()
    (runtime / "work").mkdir()
    (runtime / ".codex").mkdir()
    (runtime / "work/visible").write_text("own")
    (runtime / "pilot.json").write_text("host-controlled")
    sibling = tmp_path / "sibling-secret"
    sibling.write_text("hidden")
    source = tmp_path / "probe.c"
    source.write_text('#include <unistd.h>\nint main(){return access("/pilot/work/visible",R_OK)!=0 || access("'
                      + str(sibling) + '",R_OK)==0 || access("/home/aiden/Projects/deckAI",R_OK)==0 || access("/pilot/pilot.json",R_OK)==0;}')
    binary = tmp_path / "probe"
    build = subprocess.run(["gcc", "-static", str(source), "-o", str(binary)], capture_output=True)
    if build.returncode:
        pytest.skip("static compilation unavailable")
    result = subprocess.run(isolated_command(runtime, str(binary)), capture_output=True)
    assert result.returncode == 0, result.stderr.decode()


def test_empty_missing_thread_replaced_but_submitted_thread_preserved(tmp_path, fake):
    with pilot(tmp_path, fake):
        pass
    fake.with_suffix(".mode").write_text("missing")
    with pilot(tmp_path, fake) as seat:
        assert seat.state["thread_id"] == "thread-1"
        seat.state["submitted_turn"] = True
        seat._save()
    with pytest.raises(PilotPaused, match="no rollout"):
        pilot(tmp_path, fake)


def test_new_pending_clears_previous_turn_id_before_response_loss(tmp_path, fake):
    with pilot(tmp_path, fake) as seat:
        seat.decide(decision())
        fake.with_suffix(".mode").write_text("loss")
        with pytest.raises(PilotPaused):
            seat.decide(decision("d2"))
        assert seat.state["pending_turn_id"] != "turn-d1"


def test_production_stays_closed_until_credential_boundary_verified(tmp_path):
    with pytest.raises(PilotPaused, match="credential/tool"):
        CodexPilot(tmp_path / "production", "g1", 0, playbook="p", playbook_version="v1")
    assert not (tmp_path / "production").exists()
