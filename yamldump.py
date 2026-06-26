"""
Hand-written YAML serializer, stdlib only -- NOT a generic YAML library.

Built specifically to match PyYAML's:
    yaml.dump(obj, default_flow_style=False, sort_keys=False, allow_unicode=True)
byte-for-byte: 2-space indent, insertion-order dict keys, "- " list markers,
auto-quoting of numeric-looking strings (so "54.200" doesn't get read back
as a float and lose its trailing zero), lowercase booleans, "[]" for empty
lists. This is a direct port of yaml-dump.js from the original browser tool,
which was itself verified against real PyYAML output during development.

We don't depend on the third-party `pyyaml` package here because this
server must run with zero `pip install` on whatever machine hosts it.
"""

import re

# These are PyYAML's actual implicit-resolver patterns (introspected from
# yaml.resolver.Resolver.yaml_implicit_resolvers) for bool/null/int/float,
# used verbatim so our quoting decisions match exactly -- including
# YAML 1.1 oddities like "0b10" (binary), "048" (octal-looking), leading
# "." floats, and the full yes/no/on/off boolean set.
_BOOL_RE = re.compile(
    r"^(?:yes|Yes|YES|no|No|NO"
    r"|true|True|TRUE|false|False|FALSE"
    r"|on|On|ON|off|Off|OFF)$"
)
_NULL_RE = re.compile(r"^(?: ~|null|Null|NULL| )$")
_FLOAT_RE = re.compile(
    r"^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?"
    r"|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?"
    r"|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*"
    r"|[-+]?\.(?:inf|Inf|INF)"
    r"|\.(?:nan|NaN|NAN))$"
)
_INT_RE = re.compile(
    r"^(?:[-+]?0b[0-1_]+"
    r"|[-+]?0[0-7_]+"
    r"|[-+]?(?:0|[1-9][0-9_]*)"
    r"|[-+]?0x[0-9a-fA-F_]+"
    r"|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$"
)


def _needs_quotes(s: str) -> bool:
    if s == "":
        return True
    if s != s.strip():
        return True
    # Anything matching YAML 1.1's implicit int/float/bool/null grammar
    # must be quoted, or a PyYAML-compatible reader resolves it as that
    # type instead of a string (e.g. "54.200" -> float 54.2, dropping the
    # trailing zero; "048" -> parsed as octal-looking and misread).
    if _BOOL_RE.match(s) or _NULL_RE.match(s) or _FLOAT_RE.match(s) or _INT_RE.match(s):
        return True
    if s[0] in "!&*?|>%@`\"'#," or s[0] == " ":
        return True
    if s[0] == "-" and (len(s) == 1 or s[1] == " "):
        return True
    if ": " in s or s.endswith(":"):
        return True
    if " #" in s:
        return True
    if "\n" in s or "\t" in s:
        return True
    return False


def _quote_scalar(s: str) -> str:
    # PyYAML's default emitter prefers single-quoted style for strings that
    # don't need escapes; apostrophes are escaped by doubling them.
    if "\n" in s or "\t" in s or "\\" in s:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        escaped = escaped.replace("\n", "\\n").replace("\t", "\\t")
        return f'"{escaped}"'
    return "'" + s.replace("'", "''") + "'"


def _dump_scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            sign = "-" if (v == 0.0 and str(v)[0] == "-") else ""
            return sign + str(int(abs(v) if sign else v)) + ".0"
        return repr(v)
    s = str(v)
    if _needs_quotes(s):
        return _quote_scalar(s)
    return s


def _is_scalar(v) -> bool:
    return v is None or isinstance(v, (bool, int, float, str))


def _dump_node(v, indent: int, lines: list, key_prefix: str = ""):
    pad = "  " * indent
    if isinstance(v, dict):
        if not v:
            lines.append(f"{pad}{key_prefix}{{}}" if key_prefix else f"{pad}{{}}")
            return
        first = True
        for k, val in v.items():
            key_str = str(k)
            if _is_scalar(val):
                lines.append(f"{pad}{key_str}: {_dump_scalar(val)}")
            elif isinstance(val, dict):
                if not val:
                    lines.append(f"{pad}{key_str}: {{}}")
                else:
                    lines.append(f"{pad}{key_str}:")
                    _dump_node(val, indent + 1, lines)
            elif isinstance(val, list):
                if not val:
                    lines.append(f"{pad}{key_str}: []")
                else:
                    lines.append(f"{pad}{key_str}:")
                    _dump_list(val, indent, lines)
            else:
                lines.append(f"{pad}{key_str}: {_dump_scalar(val)}")
            first = False
    elif isinstance(v, list):
        _dump_list(v, indent - 1 if indent > 0 else 0, lines)
    else:
        lines.append(f"{pad}{_dump_scalar(v)}")


def _dump_list(items: list, indent: int, lines: list):
    pad = "  " * indent
    for item in items:
        if _is_scalar(item):
            lines.append(f"{pad}- {_dump_scalar(item)}")
        elif isinstance(item, dict):
            if not item:
                lines.append(f"{pad}- {{}}")
                continue
            keys = list(item.items())
            first_k, first_v = keys[0]
            if _is_scalar(first_v):
                lines.append(f"{pad}- {first_k}: {_dump_scalar(first_v)}")
            elif isinstance(first_v, list):
                if not first_v:
                    lines.append(f"{pad}- {first_k}: []")
                else:
                    lines.append(f"{pad}- {first_k}:")
                    _dump_list(first_v, indent + 1, lines)
            elif isinstance(first_v, dict):
                if not first_v:
                    lines.append(f"{pad}- {first_k}: {{}}")
                else:
                    lines.append(f"{pad}- {first_k}:")
                    _dump_node(first_v, indent + 2, lines)
            for k, val in keys[1:]:
                sub_pad = "  " * (indent + 1)
                if _is_scalar(val):
                    lines.append(f"{sub_pad}{k}: {_dump_scalar(val)}")
                elif isinstance(val, list):
                    if not val:
                        lines.append(f"{sub_pad}{k}: []")
                    else:
                        lines.append(f"{sub_pad}{k}:")
                        _dump_list(val, indent + 1, lines)
                elif isinstance(val, dict):
                    if not val:
                        lines.append(f"{sub_pad}{k}: {{}}")
                    else:
                        lines.append(f"{sub_pad}{k}:")
                        _dump_node(val, indent + 2, lines)
        elif isinstance(item, list):
            lines.append(f"{pad}-")
            _dump_list(item, indent + 1, lines)


def dump(obj) -> str:
    """
    Serialize a Python dict/list/scalar tree to a YAML string matching
    PyYAML's yaml.dump(obj, default_flow_style=False, sort_keys=False,
    allow_unicode=True) formatting.
    """
    lines = []
    if isinstance(obj, dict):
        _dump_node(obj, 0, lines)
    elif isinstance(obj, list):
        if not obj:
            lines.append("[]")
        else:
            _dump_list(obj, 0, lines)
    else:
        lines.append(_dump_scalar(obj))
    return "\n".join(lines) + "\n"
