"""
Skill execution engine for AgentDB v1.5.

Runs skills in sandboxed subprocesses with resource limits, timeout
enforcement, and full execution logging.

Supports four execution types:
- code_procedure: Python or Bash code run as a subprocess
- prompt_template: Inputs interpolated into a template, sent through LLM
- composite: Chained execution of multiple implementation steps
- tool_invocation: HTTP call to an external REST endpoint
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from agentdb import crud


def execute_skill(conn, skill_id, inputs=None, agent_id="default",
                  session_id=None, config=None):
    """
    Execute a skill and log the result.

    Args:
        conn: sqlite3.Connection
        skill_id: ID of the skill to execute
        inputs: dict of input values matching the skill's input_schema
        agent_id: Agent executing the skill
        session_id: Optional session context
        config: dict of meta_config overrides (timeout, memory limit, etc.)

    Returns:
        dict with execution result: {exec_id, status, outputs, stdout, stderr, exit_code, duration_ms}
    """
    if inputs is None:
        inputs = {}
    if config is None:
        config = _load_skill_config(conn)

    skill = crud.get_skill(conn, skill_id)
    if not skill:
        return {"status": "failed", "error": "Skill not found"}

    # Get active implementation
    impls = crud.list_skill_implementations(conn, skill_id, active_only=True)
    if not impls:
        return {"status": "failed", "error": "No active implementation found"}

    impl = impls[0]
    exec_type = skill.get("execution_type", "code_procedure")

    # Create execution log entry
    exec_id = crud.create_skill_execution(
        conn, skill_id, agent_id=agent_id, session_id=session_id,
        implementation_id=impl["id"], inputs=inputs,
    )

    try:
        if exec_type == "code_procedure":
            result = _execute_code_procedure(impl, inputs, config)
        elif exec_type == "prompt_template":
            result = _execute_prompt_template(conn, impl, inputs, agent_id, config)
        elif exec_type == "composite":
            result = _execute_composite(conn, skill_id, inputs, agent_id, config)
        elif exec_type == "tool_invocation":
            result = _execute_tool_invocation(impl, inputs, config)
        else:
            result = {"status": "failed", "error": f"Unknown execution type: {exec_type}"}
    except Exception as e:
        result = {"status": "failed", "error": str(e), "stdout": "", "stderr": str(e)}

    # Complete the execution log
    crud.complete_skill_execution(
        conn, exec_id,
        status=result.get("status", "failed"),
        outputs=result.get("outputs"),
        stdout=result.get("stdout"),
        stderr=result.get("stderr"),
        exit_code=result.get("exit_code"),
        resource_usage=result.get("resource_usage"),
    )

    # Update skill stats
    _update_skill_stats(conn, skill_id, result.get("status") == "success")

    result["exec_id"] = exec_id
    return result


def _load_skill_config(conn):
    """Load skill execution config from meta_config."""
    keys = ["skill_timeout_seconds", "skill_max_memory_mb", "skill_allow_network"]
    config = {}
    for key in keys:
        val = crud.get_config_value(conn, key)
        if val is not None:
            config[key] = val
    return config


def _execute_code_procedure(impl, inputs, config):
    """Execute a Python or Bash code procedure in a sandboxed subprocess."""
    language = impl.get("language", "python")
    code = impl.get("code", "")
    timeout = int(config.get("skill_timeout_seconds", 30))

    # Write code to temp file
    suffix = ".py" if language == "python" else ".sh"
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False,
                                      dir=tempfile.gettempdir()) as f:
        f.write(code)
        temp_path = f.name

    try:
        # Build restricted environment
        env = _build_sandbox_env(config)
        env["AGENTDB_SKILL_INPUTS"] = json.dumps(inputs)

        if language == "python":
            cmd = [sys.executable, temp_path]
        elif language == "bash":
            cmd = ["bash", temp_path]
        else:
            return {"status": "failed", "error": f"Unsupported language: {language}"}

        start_time = time.time()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=tempfile.gettempdir(),
            )
            elapsed_ms = int((time.time() - start_time) * 1000)

            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            exit_code = proc.returncode

            # Try to parse stdout as JSON for structured outputs
            outputs = None
            if stdout.strip():
                try:
                    outputs = json.loads(stdout.strip().split("\n")[-1])
                except (json.JSONDecodeError, IndexError):
                    outputs = {"raw_output": stdout.strip()}

            status = "success" if exit_code == 0 else "failed"
            return {
                "status": status,
                "outputs": outputs,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "duration_ms": elapsed_ms,
                "resource_usage": {"elapsed_ms": elapsed_ms},
            }

        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return {
                "status": "timeout",
                "outputs": None,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout}s",
                "exit_code": -1,
                "duration_ms": elapsed_ms,
            }

    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def _execute_prompt_template(conn, impl, inputs, agent_id, config):
    """Execute a prompt template skill by interpolating inputs and calling the LLM."""
    template = impl.get("code", "")

    # Interpolate inputs into template
    prompt = template
    for key, value in inputs.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))
        prompt = prompt.replace(f"${{{key}}}", str(value))

    # Call the LLM via middleware
    try:
        from agentdb.middleware import execute_chat_pipeline
        result = execute_chat_pipeline(conn, prompt, agent_id=agent_id)
        return {
            "status": "success",
            "outputs": {"response": result.get("response", "")},
            "stdout": result.get("response", ""),
            "stderr": "",
            "exit_code": 0,
        }
    except Exception as e:
        return {
            "status": "failed",
            "outputs": None,
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1,
        }


def _execute_composite(conn, skill_id, inputs, agent_id, config):
    """Execute a composite skill by running implementation steps in order."""
    impls = crud.list_skill_implementations(conn, skill_id, active_only=True)
    # Sort by execution_order
    impls.sort(key=lambda x: x.get("execution_order") or 0)

    if not impls:
        return {"status": "failed", "error": "No implementations found for composite skill"}

    current_inputs = inputs
    all_stdout = []
    all_stderr = []

    for impl in impls:
        language = impl.get("language", "python")

        if language == "prompt_template":
            step_result = _execute_prompt_template(conn, impl, current_inputs, agent_id, config)
        else:
            step_result = _execute_code_procedure(impl, current_inputs, config)

        all_stdout.append(step_result.get("stdout", ""))
        all_stderr.append(step_result.get("stderr", ""))

        if step_result["status"] != "success":
            return {
                "status": "failed",
                "outputs": step_result.get("outputs"),
                "stdout": "\n---\n".join(all_stdout),
                "stderr": "\n---\n".join(all_stderr),
                "exit_code": step_result.get("exit_code", 1),
            }

        # Chain: output of step N becomes input of step N+1
        if step_result.get("outputs") and isinstance(step_result["outputs"], dict):
            current_inputs = {**current_inputs, **step_result["outputs"]}

    return {
        "status": "success",
        "outputs": current_inputs,
        "stdout": "\n---\n".join(all_stdout),
        "stderr": "\n---\n".join(all_stderr),
        "exit_code": 0,
    }


def _execute_tool_invocation(impl, inputs, config):
    """Execute a tool invocation skill by calling an external REST endpoint."""
    import urllib.request
    import urllib.error

    endpoint = impl.get("code", "").strip()
    if not endpoint:
        return {"status": "failed", "error": "No endpoint URL in implementation code"}

    timeout = int(config.get("skill_timeout_seconds", 30))

    try:
        data = json.dumps(inputs).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            elapsed_ms = int((time.time() - start_time) * 1000)

        try:
            outputs = json.loads(body)
        except json.JSONDecodeError:
            outputs = {"raw_response": body}

        return {
            "status": "success",
            "outputs": outputs,
            "stdout": body,
            "stderr": "",
            "exit_code": 0,
            "duration_ms": elapsed_ms,
        }
    except urllib.error.URLError as e:
        return {
            "status": "failed",
            "outputs": None,
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1,
        }
    except Exception as e:
        return {
            "status": "failed",
            "outputs": None,
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1,
        }


def _build_sandbox_env(config):
    """Build a restricted environment for subprocess execution."""
    env = {}

    # Minimal PATH — just system essentials
    if sys.platform == "win32":
        env["PATH"] = os.environ.get("SYSTEMROOT", r"C:\Windows") + r"\system32"
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
        env["TEMP"] = tempfile.gettempdir()
        env["TMP"] = tempfile.gettempdir()
    else:
        env["PATH"] = "/usr/bin:/bin"
        env["HOME"] = tempfile.gettempdir()
        env["TMPDIR"] = tempfile.gettempdir()

    # Python needs these to find stdlib
    env["PYTHONPATH"] = ""
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    # Allow the Python executable to be found
    python_dir = str(Path(sys.executable).parent)
    if sys.platform == "win32":
        env["PATH"] = python_dir + ";" + env["PATH"]
    else:
        env["PATH"] = python_dir + ":" + env["PATH"]

    return env


def _update_skill_stats(conn, skill_id, success):
    """Update skill use_count, success_rate, and last_used."""
    skill = crud.get_skill(conn, skill_id)
    if not skill:
        return

    use_count = (skill.get("use_count") or 0) + 1
    old_rate = skill.get("success_rate") or 0.0
    # Running average of success rate
    new_rate = ((old_rate * (use_count - 1)) + (1.0 if success else 0.0)) / use_count

    conn.execute(
        """UPDATE skills SET use_count = ?, success_rate = ?, last_used = ?
           WHERE id = ?""",
        (use_count, round(new_rate, 4), crud._now(), skill_id),
    )
    conn.commit()
