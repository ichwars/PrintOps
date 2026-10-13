"""Exercise native signing with disposable interpreters and a codesign double."""

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "install/macos_python_signature.sh"


def _executable(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    path.chmod(0o755)
    return path


@pytest.fixture
def signing(tmp_path):
    base = _executable(tmp_path / "Python Framework/Versions/3.13/bin/python3.13", "#!/bin/sh\nexit 0\n")
    app = base.parent.parent / "Resources/Python.app"
    app.mkdir(parents=True)
    link = tmp_path / "python link"
    link.symlink_to(base)
    python = _executable(
        tmp_path / "PrintOps Install/venv/bin/python",
        f"#!{sys.executable}\nimport os, sys\n"
        "sys._base_executable = os.environ.get('TEST_BASE') or None\n"
        "sys.executable = os.environ['TEST_FALLBACK']\n"
        "if os.environ.get('TEST_PYTHON_FAILURE'): sys.exit(1)\n"
        "exec(sys.argv[2])\n",
    )
    state = tmp_path / "signatures.json"
    state.write_text(json.dumps({str(base): "unsigned", str(app): "unsigned"}))
    log = tmp_path / "commands.jsonl"
    tools = tmp_path / "tools"
    _executable(
        tools / "codesign",
        f"#!{sys.executable}\n"
        "import json, os, sys\nfrom pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "with Path(os.environ['TEST_LOG']).open('a') as out:\n"
        "    out.write(json.dumps(['codesign', *args]) + '\\n')\n"
        "path = Path(os.environ['TEST_STATE'])\nstate = json.loads(path.read_text())\n"
        "target = args[-1]\nstatus = state[target]\n"
        "if args[0] == '-dv':\n"
        "    if status in ('adhoc', 'developer'): sys.exit(0)\n"
        "    message = 'code object is not signed at all' if status == 'unsigned' else 'Permission denied'\n"
        "    print(target + ': ' + message, file=sys.stderr)\n    sys.exit(1)\n"
        "if args != ['--sign', '-', target]: sys.exit(9)\n"
        "if os.environ.get('TEST_SIGN_FAILURE'): sys.exit(1)\n"
        "if status != 'unsigned': sys.exit(1)\n"
        "state[target] = 'adhoc'\npath.write_text(json.dumps(state))\n",
    )
    return {
        "base": base,
        "app": app,
        "python": python,
        "state": state,
        "log": log,
        "tools": tools,
        "env": {
            **os.environ,
            "PATH": str(tools),
            "TEST_BASE": str(link),
            "TEST_FALLBACK": str(base),
            "TEST_LOG": str(log),
            "TEST_STATE": str(state),
        },
    }


def _run(signing, platform="macos", **env):
    return subprocess.run(
        ["/bin/bash", "-e", "-u", "-o", "pipefail", str(HELPER), platform, str(signing["python"])],
        env={**signing["env"], **env},
        text=True,
        capture_output=True,
        timeout=10,
    )


def _commands(signing):
    return [json.loads(line) for line in signing["log"].read_text().splitlines()] if signing["log"].exists() else []


def test_unsigned_base_and_framework_with_spaces_are_signed_once(signing):
    result = _run(signing)
    assert result.returncode == 0, result.stderr
    assert json.loads(signing["state"].read_text()) == {
        str(signing["base"]): "adhoc",
        str(signing["app"]): "adhoc",
    }
    assert _commands(signing) == [
        ["codesign", "-dv", str(signing["base"])],
        ["codesign", "--sign", "-", str(signing["base"])],
        ["codesign", "-dv", str(signing["app"])],
        ["codesign", "--sign", "-", str(signing["app"])],
    ]
    result = _run(signing)
    assert result.returncode == 0
    assert len([args for args in _commands(signing) if args[1] == "--sign"]) == 2


@pytest.mark.parametrize("status", ["adhoc", "developer", "unknown"])
def test_existing_or_unknown_signatures_are_never_rewritten(signing, status):
    initial = {str(signing["base"]): status, str(signing["app"]): status}
    signing["state"].write_text(json.dumps(initial))
    result = _run(signing)
    assert result.returncode == 0, result.stderr
    assert json.loads(signing["state"].read_text()) == initial
    assert _commands(signing) == [
        ["codesign", "-dv", str(signing["base"])],
        ["codesign", "-dv", str(signing["app"])],
    ]
    assert ("WARNING" in result.stderr) == (status == "unknown")


def test_linux_returns_before_python_or_codesign(signing):
    result = _run(signing, "linux", TEST_PYTHON_FAILURE="1")
    assert result.returncode == 0
    assert _commands(signing) == []
    assert result.stdout == result.stderr == ""


def test_missing_codesign_warns_without_failing(signing):
    (signing["tools"] / "codesign").unlink()
    result = _run(signing)
    assert result.returncode == 0
    assert "codesign" in result.stderr and "xcode-select --install" in result.stderr
    assert _commands(signing) == []


@pytest.mark.parametrize("missing", ["venv", "base", "not_executable", "resolution"])
def test_missing_interpreter_is_a_quiet_skip(signing, missing):
    env = {}
    if missing == "venv":
        signing["python"].unlink()
    elif missing == "base":
        signing["base"].unlink()
    elif missing == "not_executable":
        signing["base"].chmod(0o644)
    else:
        env["TEST_PYTHON_FAILURE"] = "1"
    result = _run(signing, **env)
    assert result.returncode == 0
    assert _commands(signing) == []
    assert result.stdout == result.stderr == ""


def test_fallback_executable_without_framework_is_signed(signing):
    signing["app"].rmdir()
    result = _run(signing, TEST_BASE="")
    assert result.returncode == 0
    assert _commands(signing) == [
        ["codesign", "-dv", str(signing["base"])],
        ["codesign", "--sign", "-", str(signing["base"])],
    ]


def test_sign_failure_warns_and_continues_with_other_targets(signing):
    result = _run(signing, TEST_SIGN_FAILURE="1")
    assert result.returncode == 0
    assert set(json.loads(signing["state"].read_text()).values()) == {"unsigned"}
    assert len(_commands(signing)) == 4
    assert "WARNING" in result.stderr and "PrintOps" in result.stderr
    assert "update_macos.sh" in result.stderr


@pytest.mark.parametrize("helper_missing", [False, True])
def test_install_signs_after_venv_dependencies(signing, helper_missing):
    install = signing["python"].parents[2]
    (install / "install").mkdir()
    if HELPER.exists() and not helper_missing:
        (install / "install" / HELPER.name).write_bytes(HELPER.read_bytes())
    _executable(
        signing["python"].with_name("pip"),
        f"#!{sys.executable}\nimport json, os, sys\n"
        "with open(os.environ['TEST_LOG'], 'a') as out: out.write(json.dumps(['pip', *sys.argv[1:]]) + '\\n')\n",
    )
    definitions = (ROOT / "install/install.sh").read_text().rsplit('main "$@"', 1)[0]
    script = (
        definitions
        + f"\nOS_TYPE=macos\nINSTALL_PATH={shlex.quote(str(install))}\nPYTHON_CMD=/bin/true\nsetup_virtualenv\n"
    )
    result = subprocess.run(
        ["/bin/bash", "-c", script],
        env={**signing["env"], "PATH": f"{signing['tools']}:/usr/bin:/bin"},
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    if helper_missing:
        assert "branch" in result.stdout and "WARN" in result.stdout
        assert set(json.loads(signing["state"].read_text()).values()) == {"unsigned"}
        return
    assert json.loads(signing["state"].read_text())[str(signing["base"])] == "adhoc"
    assert [args[0] for args in _commands(signing)] == ["pip", "pip", "codesign", "codesign", "codesign", "codesign"]


@pytest.mark.parametrize("override_pip", [False, True, "older_branch"])
def test_update_rechecks_new_python_after_preparation_before_restart(signing, override_pip):
    install = signing["python"].parents[2]
    (install / ".git").mkdir()
    (install / "install").mkdir()
    if HELPER.exists() and override_pip != "older_branch":
        (install / "install" / HELPER.name).write_bytes(HELPER.read_bytes())
    (install / "requirements.lock.txt").touch()
    plist = install / "printops.plist"
    plist.touch()
    _executable(signing["python"].with_name("pip"), "#!/bin/sh\nexit 0\n")
    stub = (
        f"#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\n"
        "name = Path(sys.argv[0]).name\nargs = sys.argv[1:]\n"
        "with open(os.environ['TEST_LOG'], 'a') as out: out.write(json.dumps([name, *args]) + '\\n')\n"
        "if name == 'git':\n"
        "    if args[0] == 'diff': sys.exit(1)\n"
        "    if args[0] == 'rev-parse': print('fixture')\n"
    )
    for name in ("git", "launchctl", "curl"):
        _executable(signing["tools"] / name, stub)
    # The disposable Python wrapper also runs the updater's runtime script.
    python_source = (
        signing["python"]
        .read_text()
        .replace(
            "exec(sys.argv[2])",
            "exec(sys.argv[2]) if sys.argv[1] == '-c' else exec(open(sys.argv[1]).read())",
        )
    )
    signing["python"].write_text(python_source)
    _executable(
        install / "scripts/vendor_pdf_runtime.py",
        "import json, os\nwith open(os.environ['TEST_LOG'], 'a') as out: out.write(json.dumps(['runtime']) + '\\n')\n",
    )
    env = {
        **signing["env"],
        "PATH": f"{signing['tools']}:/usr/bin:/bin",
        "INSTALL_DIR": str(install),
        "PLIST_PATH": str(plist),
        "BACKUP_MODE": "skip",
        "BRANCH": "main",
        "FORCE": "1",
    }
    if override_pip is True:
        other_base = _executable(install / "Other Python/bin/python3", "#!/bin/sh\nexit 0\n")
        state = json.loads(signing["state"].read_text())
        state[str(other_base)] = "unsigned"
        signing["state"].write_text(json.dumps(state))
        other_pip = _executable(install / "Other Toolchain/bin/pip", "#!/bin/sh\nexit 0\n")
        _executable(
            other_pip.with_name("python"),
            f'#!/bin/bash\nif [[ "$1" == "-c" ]]; then printf "%s\\n" {shlex.quote(str(other_base))}; '
            f'else exec {shlex.quote(str(signing["python"]))} "$@"; fi\n',
        )
        env["VENV_PIP"] = str(other_pip)
    for _ in range(2):
        result = subprocess.run(
            ["/bin/bash", str(ROOT / "install/update_macos.sh")],
            input="y\n",
            env=env,
            text=True,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
    commands = _commands(signing)
    if override_pip == "older_branch":
        assert "branch" in result.stderr and "WARNING" in result.stderr
        assert ["launchctl", "load", str(plist)] in commands
        assert set(json.loads(signing["state"].read_text()).values()) == {"unsigned"}
        return
    assert json.loads(signing["state"].read_text())[str(signing["base"])] == "adhoc"
    assert commands.index(["runtime"]) < commands.index(["codesign", "--sign", "-", str(signing["base"])])
    assert commands.index(["codesign", "--sign", "-", str(signing["app"])]) < commands.index(
        ["launchctl", "load", str(plist)]
    )
    assert len([args for args in commands if args[1:2] == ["--sign"]]) == 2
    # A Homebrew upgrade selects a new unsigned version; the old grants survive.
    upgraded = _executable(install / "Python Framework/Versions/3.14/bin/python3.14", "#!/bin/sh\nexit 0\n")
    state = json.loads(signing["state"].read_text())
    state[str(upgraded)] = "unsigned"
    signing["state"].write_text(json.dumps(state))
    result = subprocess.run(
        ["/bin/bash", str(ROOT / "install/update_macos.sh")],
        input="y\n",
        env={**env, "TEST_BASE": str(upgraded)},
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(signing["state"].read_text()) == {**state, str(upgraded): "adhoc"}
    assert _commands(signing).count(["codesign", "--sign", "-", str(upgraded)]) == 1


def _bootstrap_fixture(signing, mode="success", platform="darwin", external=False):
    install = signing["python"].parents[2]
    (install / ".git").mkdir()
    old = ROOT / "backend/tests/fixtures/install/update_macos_pre_o09.sh"
    updater = install / "install/update_macos.sh"
    updater.parent.mkdir()
    updater.write_bytes(old.read_bytes())
    checkout = install.parent / "checkout"
    for relative in ("scripts/vendor_pdf_runtime.py", "install/update_macos.sh", "install/macos_python_signature.sh"):
        target = checkout / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    if mode == "helper_exit":
        (checkout / "install/macos_python_signature.sh").write_text("#!/bin/bash\nexit 17\n")
    if mode == "missing_tool":
        (signing["tools"] / "codesign").unlink()
    plist = install / "printops.plist"
    plist.touch()
    (install / "requirements.lock.txt").touch()
    _executable(signing["python"].with_name("pip"), "#!/bin/sh\nexit 0\n")
    wrapper = (
        f"#!{sys.executable}\nimport importlib.util, json, os, sys\nfrom pathlib import Path\n"
        "if sys.argv[1] == '-c':\n"
        "    sys._base_executable = os.environ['TEST_BASE']\n    exec(sys.argv[2])\n    sys.exit(0)\n"
        "script = sys.argv[1]\nsys.argv = sys.argv[1:]\n"
        "spec = importlib.util.spec_from_file_location('vendor', script)\n"
        "vendor = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(vendor)\n"
        "vendor._load_manifest = lambda: {'verapdf': {'version': 'fixture', 'url': 'https://fixture/archive', 'signature_url': 'https://fixture/signature', 'sha256': '', 'signature_sha256': ''}}\n"
        "vendor._obtain = lambda *args: Path('fixture.zip')\n"
        "vendor._verify_signature = lambda *args: None\n"
        "def stage(archive, candidate, version):\n"
        "    if os.environ['TEST_MODE'] == 'staging': raise vendor.VendorError('verification failed')\n"
        "    candidate.mkdir()\n    (candidate / 'verapdf').touch()\n"
        "    with open(os.environ['TEST_LOG'], 'a') as out: out.write(json.dumps(['runtime']) + '\\n')\n"
        "vendor._install_cli = stage\nsys.platform = os.environ['TEST_PLATFORM']\nsys.exit(vendor.main())\n"
    )
    _executable(signing["python"], wrapper)
    stub = (
        f"#!{sys.executable}\nimport json, os, shutil, sys\nfrom pathlib import Path\n"
        "name = Path(sys.argv[0]).name\nargs = sys.argv[1:]\n"
        "with open(os.environ['TEST_LOG'], 'a') as out: out.write(json.dumps([name, *args]) + '\\n')\n"
        "if name == 'git':\n"
        "    if args[0] == 'diff': sys.exit(1)\n"
        "    if args[0] == 'rev-parse': print('fixture')\n"
        "    if args[:2] == ['reset', '--hard'] and args[-1].startswith('origin/'):\n"
        "        checkout = Path(os.environ['TEST_CHECKOUT'])\n"
        "        for source in checkout.rglob('*'):\n"
        "            if not source.is_file(): continue\n"
        "            target = Path.cwd() / source.relative_to(checkout)\n"
        "            target.parent.mkdir(parents=True, exist_ok=True)\n"
        "            target.unlink(missing_ok=True)\n            shutil.copy2(source, target)\n"
    )
    for name in ("git", "launchctl", "curl"):
        _executable(signing["tools"] / name, stub)
    env = {
        **signing["env"],
        "PATH": f"{signing['tools']}:/usr/bin:/bin",
        "INSTALL_DIR": str(install),
        "PLIST_PATH": str(plist),
        "BACKUP_MODE": "skip",
        "BRANCH": "main",
        "FORCE": "1",
        "TEST_CHECKOUT": str(checkout),
        "TEST_PLATFORM": platform,
        "TEST_MODE": mode,
    }
    if mode == "sign":
        env["TEST_SIGN_FAILURE"] = "1"
    if external:
        other_base = _executable(install / "External Python/bin/python3", "#!/bin/sh\nexit 0\n")
        state = json.loads(signing["state"].read_text())
        state[str(other_base)] = "unsigned"
        signing["state"].write_text(json.dumps(state))
        env["TEST_OTHER_BASE"] = str(other_base)
        other_pip = _executable(install / "External Toolchain/bin/pip", "#!/bin/sh\nexit 0\n")
        _executable(
            other_pip.with_name("python"), wrapper.replace("os.environ['TEST_BASE']", "os.environ['TEST_OTHER_BASE']")
        )
        env["VENV_PIP"] = str(other_pip)
    return install, updater, env


@pytest.mark.parametrize("mode", ["success", "sign", "helper_exit", "missing_tool", "staging"])
@pytest.mark.parametrize("external", [False, True])
def test_pre_o09_updater_bootstraps_before_first_restart(signing, mode, external):
    install, updater, env = _bootstrap_fixture(signing, mode, external=external)
    result = subprocess.run(
        ["/bin/bash", str(updater)],
        input="y\n",
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
    )
    commands = _commands(signing)
    state = json.loads(signing["state"].read_text())
    if external:
        assert state[str(install / "External Python/bin/python3")] == "unsigned"
    if mode == "staging":
        assert result.returncode != 0
        assert not any(args[0] == "codesign" for args in commands)
        return
    assert result.returncode == 0, result.stderr
    restart = commands.index(["launchctl", "load", str(install / "printops.plist")])
    assert commands.index(["runtime"]) < restart
    if mode == "success":
        assert state[str(signing["base"])] == state[str(signing["app"])] == "adhoc"
        assert commands.index(["codesign", "--sign", "-", str(signing["app"])]) < restart
    else:
        assert set(state.values()) == {"unsigned"}
        assert "[PrintOps] WARNING" in result.stderr


@pytest.mark.parametrize("case", ["linux", "packaging", "no_backup", "foreign_backup", "verify_only", "import"])
def test_vendor_cli_does_not_sign_outside_native_macos_update(signing, case):
    install, _updater, env = _bootstrap_fixture(signing, platform="linux" if case == "linux" else "darwin")
    shutil.copytree(install.parent / "checkout", install, dirs_exist_ok=True)
    script = install / "scripts/vendor_pdf_runtime.py"
    if case == "import":
        args = ["-c", f"import runpy; runpy.run_path({str(script)!r}, run_name='vendor_import')"]
    else:
        destination = install / ("package/verapdf" if case == "packaging" else "runtime/verapdf")
        args = [str(script), "--destination", str(destination)]
        if case != "no_backup":
            backup = install / (
                "foreign/verapdf" if case == "foreign_backup" else "runtime/.verapdf-backup.fixture/verapdf"
            )
            args += ["--backup-dir", str(backup)]
        if case == "verify_only":
            args += ["--verify-only"]
    result = subprocess.run(
        [str(signing["python"]), *args],
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert not any(args[0] == "codesign" for args in _commands(signing))
    assert set(json.loads(signing["state"].read_text()).values()) == {"unsigned"}
