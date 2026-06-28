import os

import pytest
from click.testing import CliRunner

from tools.bin import keepalived_status as ks

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "keepalived.data")
FIXTURE_V2 = os.path.join(os.path.dirname(__file__), "fixtures", "keepalived-v2.data")


@pytest.fixture
def instances():
    with open(FIXTURE, "r") as f:
        return ks.parse(f.read())


@pytest.fixture
def instances_v2():
    with open(FIXTURE_V2, "r") as f:
        return ks.parse(f.read())


def test_parse_counts(instances):
    assert [i.name for i in instances] == ["DNS", "mysql", "netdata"]


def test_parse_backup_instance(instances):
    dns = instances[0]
    assert dns.state == "BACKUP"
    assert dns.vrid == 222
    assert dns.priority == 80
    assert dns.master_router == "192.168.19.132"
    assert dns.src_ip == "192.168.19.120"
    assert dns.vips == ["192.168.19.222/24"]
    assert dns.last_transition_human == "Tue Jun 23 22:40:31 2026"


def test_parse_master_instance(instances):
    mysql = instances[1]
    assert mysql.is_master
    assert mysql.owner == "192.168.19.120"  # local src_ip
    assert mysql.scripts[0].name == "chk_mysql"
    assert mysql.scripts[0].is_ok


def test_failing_script_detected(instances):
    netdata = instances[2]
    assert [s.name for s in netdata.failing_scripts] == ["chk_netdata"]
    assert netdata.scripts[0].status == "BAD"


def test_degraded_priority(instances):
    netdata = instances[2]
    assert netdata.is_degraded
    assert netdata.effective_priority == -20


def test_backup_owner_is_master_router(instances):
    assert instances[0].owner == "192.168.19.132"
    assert instances[2].owner == "192.168.19.226"


def test_parse_empty():
    assert ks.parse("") == []


def test_cli_runs():
    runner = CliRunner()
    result = runner.invoke(ks.main, [FIXTURE, "--no-resolve"])
    assert result.exit_code == 0
    assert "VRRP instances" in result.output
    assert "chk_netdata" in result.output


def test_cli_json():
    runner = CliRunner()
    result = runner.invoke(ks.main, [FIXTURE, "--json", "--no-resolve"])
    assert result.exit_code == 0
    assert '"netdata"' in result.output
    assert '"is_degraded": true' in result.output


def test_cli_missing_file():
    runner = CliRunner()
    result = runner.invoke(ks.main, ["/no/such/file.data"])
    assert result.exit_code == 1


def test_resolver_disabled_returns_ip():
    resolve = ks.make_resolver(enabled=False)
    assert resolve("192.168.19.132") == "192.168.19.132"


def test_resolver_resolves_short_name(monkeypatch):
    calls = []

    def fake_gethostbyaddr(ip):
        calls.append(ip)
        return ("router.home.lan", [], [ip])

    monkeypatch.setattr(ks.socket, "gethostbyaddr", fake_gethostbyaddr)
    resolve = ks.make_resolver(enabled=True)
    assert resolve("192.168.19.132") == "router"
    # Second call is served from the cache (no extra lookup).
    assert resolve("192.168.19.132") == "router"
    assert calls == ["192.168.19.132"]


def test_resolver_falls_back_on_failure(monkeypatch):
    def boom(ip):
        raise OSError("no PTR")

    monkeypatch.setattr(ks.socket, "gethostbyaddr", boom)
    resolve = ks.make_resolver(enabled=True)
    assert resolve("10.0.0.1") == "10.0.0.1"


def test_resolver_ignores_non_ip():
    resolve = ks.make_resolver(enabled=True)
    assert resolve("unknown") == "unknown"


def test_label_with_name(monkeypatch):
    monkeypatch.setattr(ks.socket, "gethostbyaddr", lambda ip: ("nas.home.lan", [], [ip]))
    resolve = ks.make_resolver(enabled=True)
    assert ks._label("192.168.19.226", resolve) == "nas (192.168.19.226)"


def test_label_without_name():
    resolve = ks.make_resolver(enabled=False)
    assert ks._label("192.168.19.226", resolve) == "192.168.19.226"


def test_find_pid_from_pidfile(tmp_path, monkeypatch):
    pidfile = tmp_path / "keepalived.pid"
    pidfile.write_text("4321\n")
    monkeypatch.setattr(ks, "PIDFILE_CANDIDATES", (str(pidfile),))
    assert ks.find_keepalived_pid() == 4321


def test_find_pid_from_pgrep(monkeypatch):
    monkeypatch.setattr(ks, "PIDFILE_CANDIDATES", ())
    monkeypatch.setattr(ks.subprocess, "check_output", lambda *a, **k: "777\n778\n")
    assert ks.find_keepalived_pid() == 777


def test_find_pid_none(monkeypatch):
    monkeypatch.setattr(ks, "PIDFILE_CANDIDATES", ())

    def boom(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(ks.subprocess, "check_output", boom)
    assert ks.find_keepalived_pid() is None


def test_refresh_data_file_signals(monkeypatch, tmp_path):
    data = tmp_path / "k.data"
    data.write_text("old")
    monkeypatch.setattr(ks, "find_keepalived_pid", lambda: 99)
    times = iter([100.0, 200.0])
    monkeypatch.setattr(ks.os.path, "getmtime", lambda p: next(times))
    sent = {}

    def fake_kill(pid, sig):
        sent["pid"] = pid
        sent["sig"] = sig

    monkeypatch.setattr(ks.os, "kill", fake_kill)
    assert ks.refresh_data_file(str(data), wait=1.0) is True
    assert sent == {"pid": 99, "sig": ks.signal.SIGUSR1}


def test_refresh_no_pid(monkeypatch):
    monkeypatch.setattr(ks, "find_keepalived_pid", lambda: None)
    assert ks.refresh_data_file("/tmp/whatever") is False


def test_refresh_permission_denied(monkeypatch, tmp_path):
    data = tmp_path / "k.data"
    data.write_text("x")
    monkeypatch.setattr(ks, "find_keepalived_pid", lambda: 5)

    def denied(pid, sig):
        raise PermissionError()

    monkeypatch.setattr(ks.os, "kill", denied)
    assert ks.refresh_data_file(str(data)) is False


def test_cli_signal_invokes_refresh(monkeypatch):
    called = {}

    def fake_refresh(path, **kwargs):
        called["path"] = path
        return True

    monkeypatch.setattr(ks, "refresh_data_file", fake_refresh)
    runner = CliRunner()
    result = runner.invoke(ks.main, [FIXTURE, "--signal", "--no-resolve"])
    assert result.exit_code == 0
    assert called["path"] == FIXTURE


def test_cli_signal_failure_exits(monkeypatch):
    monkeypatch.setattr(ks, "refresh_data_file", lambda path, **kwargs: False)
    runner = CliRunner()
    result = runner.invoke(ks.main, [FIXTURE, "--signal"])
    assert result.exit_code == 1


def test_render_simple_basic(instances, capsys):
    resolve = ks.make_resolver(enabled=False)
    candidates = {"DNS": ["raspym2", "phoenix"], "mysql": ["phoenix", "raspy3"]}
    ks.render_simple(instances, resolve, candidates)
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "DNS (192.168.19.222/24): 192.168.19.132 (raspym2, phoenix)"
    assert out[1] == "mysql (192.168.19.72/24): 192.168.19.120 (phoenix, raspy3)"
    # netdata is a BACKUP whose master_router is the owner; no candidates given.
    assert out[2] == "netdata (192.168.19.71/24): 192.168.19.226"


def test_render_simple_resolves_owner(instances, capsys, monkeypatch):
    names = {
        "192.168.19.132": "raspym2",
        "192.168.19.120": "phoenix",
        "192.168.19.226": "clickypi",
    }
    monkeypatch.setattr(ks.socket, "gethostbyaddr", lambda ip: (names.get(ip, ip), [], [ip]))
    resolve = ks.make_resolver(enabled=True)
    ks.render_simple(instances, resolve, {"DNS": ["raspym2", "phoenix"]})
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "DNS (192.168.19.222/24): raspym2 (raspym2, phoenix)"
    assert out[1] == "mysql (192.168.19.72/24): phoenix"


def test_render_simple_no_active_host(capsys):
    insts = [ks.Instance(name="orphan", state="BACKUP", vips=["192.168.19.99/24"])]
    ks.render_simple(insts, ks.make_resolver(enabled=False))
    assert capsys.readouterr().out.strip() == "orphan (192.168.19.99/24): no active host"


def test_load_candidate_hosts(tmp_path):
    conf = tmp_path / "FLASK.conf"
    conf.write_text(
        '# {"vrrp": ["phoenix", "raspy2"], "id": 69}\n' "vrrp_instance FLASK {\n" "  virtual_router_id 69\n" "}\n"
    )
    result = ks.load_candidate_hosts(str(tmp_path))
    assert result == {"FLASK": ["phoenix", "raspy2"]}


def test_load_candidate_hosts_missing_dir():
    assert ks.load_candidate_hosts("/no/such/keepalived/dir") == {}


def test_cli_simple(monkeypatch):
    monkeypatch.setattr(ks, "load_candidate_hosts", lambda: {"mysql": ["phoenix", "raspy3"]})
    runner = CliRunner()
    result = runner.invoke(ks.main, [FIXTURE, "--simple", "--no-resolve"])
    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert "DNS (192.168.19.222/24): 192.168.19.132" in lines
    assert "mysql (192.168.19.72/24): 192.168.19.120 (phoenix, raspy3)" in lines


# ---- keepalived v2.2.7 format --------------------------------------------


def test_v2_instance_names(instances_v2):
    assert [i.name for i in instances_v2] == ["ezarr", "www"]


def test_v2_state_not_clobbered_by_interface_lines(instances_v2):
    # "State = UP, RUNNING" (Interfaces) and "State = idle" (Scripts) must be ignored.
    ezarr, www = instances_v2
    assert ezarr.state == "MASTER"
    assert www.state == "BACKUP"


def test_v2_virtual_ip_paren_format(instances_v2):
    # v2 uses "Virtual IP (1):" instead of "Virtual IP = 1".
    assert instances_v2[0].vips == ["192.168.19.64/24"]
    assert instances_v2[1].vips == ["192.168.19.66/24"]


def test_v2_float_epoch_parsed(instances_v2):
    www = instances_v2[1]
    assert www.last_transition_epoch == 1782548189
    assert www.last_transition_human == "Sat Jun 27 09:16:29.096089 2026"


def test_v2_script_status_mapped_from_scripts_section(instances_v2):
    ezarr, www = instances_v2
    assert [s.name for s in ezarr.scripts] == ["chk_ezarr"]
    assert ezarr.scripts[0].status == "GOOD"
    assert [s.name for s in www.scripts] == ["chk_www"]
    assert www.scripts[0].status == "BAD"
    assert www.failing_scripts


def test_v2_degraded_priority(instances_v2):
    www = instances_v2[1]
    assert www.priority == 100
    assert www.effective_priority == 1
    assert www.is_degraded


def test_v2_owner(instances_v2):
    ezarr, www = instances_v2
    assert ezarr.owner == "192.168.19.226"  # MASTER -> local src_ip
    assert www.owner == "192.168.19.120"  # BACKUP -> master_router


def test_v2_cli_runs():
    runner = CliRunner()
    result = runner.invoke(ks.main, [FIXTURE_V2, "--no-resolve"])
    assert result.exit_code == 0
    assert "chk_www is BAD" in result.output
    assert "UP, RUNNING" not in result.output
