"""
Sandboxed runner for user-defined Python tool code.

This module is intentionally self-contained: it MUST NOT import anything from the
``app`` package (in particular ``app.config``). It is executed as a standalone
script in an isolated subprocess or in a throwaway, hardened Docker container
that has no access to backend configuration, secrets, network, or filesystem.

Protocol: read a JSON payload from stdin

    {"code": str, "function_name": str, "arguments": dict}

validate the code, execute it with a restricted set of builtins and an import
allowlist, call the requested function, then write a JSON result to stdout

    {"success": true, "result": ...}   or   {"success": false, "error": "..."}

The in-process restrictions below are DEFENSE IN DEPTH only. In-process Python
sandboxing is not a hard security boundary (allowed modules can re-export
dangerous ones, and new escapes are found over time). The real boundary for
multi-user / production deployments is OS-level isolation; see
``python_tool_executor.py`` (Docker backend).
"""

import json
import sys

# Builtins removed from the execution namespace: these enable code execution,
# file access, or introspection escapes.
BLACKLIST_BUILTINS = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "__import__",
        "open",
        "input",
        "globals",
        "locals",
        "vars",
        "dir",
        "delattr",
        "setattr",
        "getattr",
        "breakpoint",
        "exit",
        "quit",
        "help",
        "memoryview",
        "bytearray",
        "super",
        "property",
        "staticmethod",
        "classmethod",
        "__build_class__",
        "object",
        "type",
    }
)

# Import allowlist: safe, pure-computation standard-library modules only. An
# allowlist (instead of a blacklist) prevents importing modules that reach OS /
# filesystem / network capabilities. The root package name is matched, so
# ``collections.abc`` is allowed via ``collections`` while ``os.path`` is not
# (``os`` is not listed). ``enum`` is excluded because it re-exports
# ``builtins`` under an alias that attribute-name filtering cannot catch, and
# ``operator`` is excluded because ``operator.attrgetter`` is a dynamic getattr
# that bypasses the static attribute checks.
ALLOWLIST_MODULES = frozenset(
    {
        "array",
        "base64",
        "binascii",
        "bisect",
        "calendar",
        "cmath",
        "collections",
        "copy",
        "csv",
        "dataclasses",
        "datetime",
        "decimal",
        "difflib",
        "fractions",
        "functools",
        "hashlib",
        "heapq",
        "hmac",
        "html",
        "io",
        "itertools",
        "json",
        "math",
        "numbers",
        "pprint",
        "random",
        "re",
        "secrets",
        "statistics",
        "string",
        "struct",
        "textwrap",
        "time",
        "typing",
        "unicodedata",
        "uuid",
        "zlib",
        "zoneinfo",
    }
)

# Attribute names that are blocked even when they do not start with "_". Several
# allowlisted modules re-export dangerous modules as public attributes (e.g.
# ``uuid.os``, ``datetime.sys``, ``typing.sys``). Blocking these names closes
# the "import an allowed module, then reach os/sys through it" escape and is
# version independent.
FORBIDDEN_ATTRIBUTE_NAMES = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "socket",
        "builtins",
        "importlib",
        "ctypes",
        "marshal",
        "pickle",
        "shutil",
        "glob",
        "pathlib",
        "tempfile",
        "asyncio",
        "inspect",
        "warnings",
        "ast",
        "threading",
        "multiprocessing",
        "posix",
        "nt",
    }
)

# Substrings that indicate an attempt to reach interpreter internals or perform
# an object-graph escape. Checked against the raw source and string constants.
FORBIDDEN_CODE_FRAGMENTS = frozenset(
    {
        "__",
        "catch_warnings",
        "_module",
        "func_globals",
        "f_globals",
        "gi_frame",
        "cr_frame",
        "tb_frame",
    }
)

_real_import = __import__


def _validate_code_safety(code: str) -> None:
    """Reject tool code that attempts to escape the sandbox. Raises ValueError."""
    import ast

    for fragment in FORBIDDEN_CODE_FRAGMENTS:
        if fragment in code:
            raise ValueError("Tool code contains a restricted Python introspection primitive")

    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWLIST_MODULES:
                    raise ValueError(f"Import of module '{alias.name}' is not allowed in tool code")
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            if not root or root not in ALLOWLIST_MODULES:
                raise ValueError(f"Import of module '{module or '.'}' is not allowed in tool code")
            # Block "from <allowed_module> import os" style submodule/attribute imports
            # that would otherwise reach a dangerous module without an attribute access.
            for alias in node.names:
                if alias.name in FORBIDDEN_ATTRIBUTE_NAMES:
                    raise ValueError(
                        f"Importing '{alias.name}' from '{module}' is not allowed in tool code"
                    )
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ValueError("Tool code may not access private Python attributes")
            if node.attr in FORBIDDEN_ATTRIBUTE_NAMES:
                raise ValueError(f"Tool code may not access the restricted attribute '{node.attr}'")
        if isinstance(node, ast.Name) and node.id in BLACKLIST_BUILTINS:
            raise ValueError(f"Builtin '{node.id}' is not allowed")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for fragment in FORBIDDEN_CODE_FRAGMENTS:
                if fragment in node.value:
                    raise ValueError(
                        "Tool code contains a restricted Python introspection primitive"
                    )


def _safe_import(name: str, *args: object, **kwargs: object) -> object:
    """Import hook that only permits allowlisted standard-library modules."""
    root = name.split(".")[0]
    if root not in ALLOWLIST_MODULES:
        raise ImportError(f"Import of module '{name}' is not allowed in tool code")
    return _real_import(name, *args, **kwargs)


def _create_safe_builtins() -> dict:
    import builtins

    safe = {}
    for key, value in vars(builtins).items():
        if key not in BLACKLIST_BUILTINS:
            safe[key] = value
    safe["__import__"] = _safe_import
    return safe


def run(payload: dict) -> object:
    """Validate and execute a tool payload, returning the function result."""
    code = payload["code"]
    function_name = payload["function_name"]
    arguments = payload.get("arguments") or {}

    _validate_code_safety(code)

    namespace: dict = {"__builtins__": _create_safe_builtins()}
    exec(code, namespace)

    fn = namespace.get(function_name)
    if fn is None:
        raise NameError(f"Function '{function_name}' not found in code")

    return fn(**arguments)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        result = run(payload)
        output = {"success": True, "result": result}
    except Exception as exc:  # noqa: BLE001 - any failure is reported as structured output
        output = {"success": False, "error": str(exc)}
    sys.stdout.write(json.dumps(output, default=str))
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    main()
