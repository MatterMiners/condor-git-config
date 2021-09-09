import subprocess
import tempfile
import shutil
import pathlib
import sys
import json


REPO_URL = "https://github.com/MatterMiners/condor-git-config.git"
EXECUTABLE = [shutil.which("condor-git-config")]
if EXECUTABLE[0] is None:
    EXECUTABLE = [
        sys.executable,
        str(pathlib.Path(__file__).parent.parent.parent / "condor_git_config.py"),
    ]


def test_checkout():
    with tempfile.TemporaryDirectory() as cache:
        subprocess.check_call([*EXECUTABLE, REPO_URL, "--cache-path", cache])
        subprocess.check_call([*EXECUTABLE, REPO_URL, "--cache-path", cache])


def test_includes():
    with tempfile.TemporaryDirectory() as cache:
        command = [
            *EXECUTABLE,
            REPO_URL,
            "--cache-path",
            cache,
            "--pattern",
            r".*\.py",
            "--path-key",
            "CHECKOUT_ROOT",
        ]
        initial = subprocess.check_output(command).splitlines()
        refresh = subprocess.check_output(command).splitlines()
        assert initial[:1] != refresh[:1]
        assert initial[1:] == refresh[1:]
        assert b"CHECKOUT_ROOT" in b"\n".join(initial)
        root = next(
            line.partition(b"=")[-1].strip()
            for line in initial[1:]
            if b"CHECKOUT_ROOT" in line
        )
        expected_include = b"include : %s/condor_git_config.py" % root
        assert expected_include in initial[1:]


def test_refresh():
    with tempfile.TemporaryDirectory() as cache:
        command = [
            *EXECUTABLE,
            REPO_URL,
            "--cache-path",
            cache,
            "--pattern",
            r".*\.py",
            "--path-key",
            "CHECKOUT_ROOT",
        ]
        previous_meta = json.loads(subprocess.check_output(command).splitlines()[0][1:])
        for _ in range(5):
            new_meta = json.loads(subprocess.check_output(command).splitlines()[0][1:])
            assert new_meta["age"] > previous_meta["age"]
            assert new_meta["reads"] == previous_meta["reads"] + 1
            assert new_meta["pulls"] == previous_meta["pulls"]
            previous_meta = new_meta
