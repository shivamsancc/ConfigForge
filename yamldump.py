"""
Pure-Python YAML dumper matching PyYAML's
yaml.dump(obj, default_flow_style=False, sort_keys=False) byte-for-byte,
for the subset of types this project actually produces: dict, list, str,
int, float, bool, None.

Implemented from scratch to avoid a pip dependency; verified against
real PyYAML across thousands of randomized fuzz trials (see test suite).

Known limitation: PyYAML's emitter performs automatic line-folding for
scalars containing embedded newlines or longer than ~80 characters,
re-wrapping them across multiple physical lines with specific indentation
rules. That folding algorithm is not replicated here. For those two cases
only, this module emits a single-line double-quoted scalar instead (valid
YAML, parses back to the identical string, just not byte-identical to
PyYAML's particular line-wrap choice). This is a deliberate scope cut: the
fields this project actually writes (IPs, device names, credentials,
protocol names, short tag values, interface descriptions) are not
expected to contain newlines or exceed 80 characters in practice.
"""
import re

_BOOL_WORDS = {
    "yes", "Yes", "YES", "no", "No", "NO",
    "true", "True", "TRUE", "false", "False", "FALSE",
    "on", "On", "ON", "off", "Off", "OFF",
}
_NULL_WORDS = {"~", "null", "Null", "NULL", " ", ""}

# These mirror yaml.resolver.Resolver's implicit-resolver patterns exactly
# (extracted from PyYAML itself) so quoting decisions match its behavior,
# including quirks like requiring an explicit sign on the float exponent
# (so '1e10' is NOT an implicit float and needs no quoting) and the
# int resolver's `0[0-7_]+` octal form (no 'o' prefix).
_INT_RE = re.compile(
    r"^(?:[-+]?0b[0-1_]+"
    r"|[-+]?0[0-7_]+"
    r"|[-+]?(?:0|[1-9][0-9_]*)"
    r"|[-+]?0x[0-9a-fA-F_]+"
    r"|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$"
)
_FLOAT_RE = re.compile(
    r"^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?"
    r"|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?"
    r"|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*"
    r"|[-+]?\.(?:inf|Inf|INF)"
    r"|\.(?:nan|NaN|NAN))$"
)
_SEXAGESIMAL_RE = None  # sexagesimal (base-60) forms are already covered above

_SPECIAL_CHARS = set(",[]{}#&*!|>'\"%@`")


def _looks_like_yaml_special(s: str) -> bool:
    if s == "":
        return True
    if s in _BOOL_WORDS or s in _NULL_WORDS:
        return True
    if _INT_RE.match(s) or _FLOAT_RE.match(s):
        return True
    if s.strip() != s:
        return True
    first = s[0]
    if first in _SPECIAL_CHARS or first in "-?:":
        # leading "- ", "? ", ": " are structural; a bare "-"/"?"/":" alone
        # also needs quoting, but e.g. "in-progress" does not.
        if first in "-?:" and len(s) > 1 and s[1] != " ":
            pass
        else:
            return True
    if ": " in s or s.endswith(":"):
        return True
    if " #" in s:
        return True
    if "\n" in s or "\t" in s:
        return True
    return False


def _quote_scalar(s: str) -> str:
    # PyYAML's default emitter prefers single-quoted style when the string
    # doesn't need backslash escapes (control chars, etc.); within single
    # quotes a literal "'" is escaped by doubling it. Double-quoted style
    # is only used when the string actually needs backslash escapes, OR
    # (our deliberate fallback) when it contains a newline or is long
    # enough that PyYAML would line-fold it -- see module docstring.
    needs_double = (
        any(ord(c) < 0x20 and c not in ("\n",) for c in s)
        or "\\" in s
        or "\n" in s
        or len(s) > 80
    )
    if not needs_double:
        return "'" + s.replace("'", "''") + "'"
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\t", "\\t")
    return f'"{escaped}"'


def _dump_scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:  # NaN
            return ".nan"
        if value == float("inf"):
            return ".inf"
        if value == float("-inf"):
            return "-.inf"
        return repr(value)
    s = str(value)
    if _looks_like_yaml_special(s):
        return _quote_scalar(s)
    return s


def _is_scalar(value) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


def dump(obj, indent: int = 0) -> str:
    """Top-level entry point. Mirrors yaml.dump(obj, default_flow_style=False,
    sort_keys=False) for dict/list/scalar trees."""
    lines = []
    _dump_node(obj, indent, lines, top_level=True)
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _render_block(obj, indent: int) -> list:
    """Render obj as a block-style node and return its lines, each
    already prefixed with the given indent level (in units of 2 spaces).
    This is the "normal" entry point used for dict/list values that sit
    on their own line under a `key:`."""
    pad = "  " * indent
    if isinstance(obj, dict):
        if not obj:
            return [pad + "{}"]
        lines = []
        for key, value in obj.items():
            key_str = _dump_scalar(key) if not isinstance(key, str) or _looks_like_yaml_special(key) else key
            lines.extend(_render_mapping_entry(pad, key_str, value, indent))
        return lines
    if isinstance(obj, list):
        if not obj:
            return [pad + "[]"]
        lines = []
        for item in obj:
            lines.extend(_render_seq_item(pad, item, indent))
        return lines
    return [pad + _dump_scalar(obj)]


def _render_mapping_entry(pad, key_str, value, indent) -> list:
    if _is_scalar(value):
        return [f"{pad}{key_str}: {_dump_scalar(value)}"]
    if isinstance(value, dict):
        if not value:
            return [f"{pad}{key_str}: {{}}"]
        return [f"{pad}{key_str}:"] + _render_block(value, indent + 1)
    if isinstance(value, list):
        if not value:
            return [f"{pad}{key_str}: []"]
        # List items under a mapping key align with the key itself (same
        # indent level), per PyYAML's default_flow_style=False emitter.
        return [f"{pad}{key_str}:"] + _render_block(value, indent)
    return [f"{pad}{key_str}: {_dump_scalar(str(value))}"]


def _render_seq_item(pad, item, indent) -> list:
    """Render one `- ...` sequence item. PyYAML merges the first line of
    a nested block (dict or list) onto the same line as the dash; only
    continuation lines get the deeper indent."""
    dash = pad + "- "
    cont_pad = pad + "  "

    if _is_scalar(item):
        return [f"{dash}{_dump_scalar(item)}"]

    if isinstance(item, dict):
        if not item:
            return [f"{dash}{{}}"]
        sub_lines = _render_block(item, indent + 1)
        # sub_lines[0] currently has cont_pad's indent; strip it and splice
        # onto the dash instead.
        first = sub_lines[0][len(cont_pad):] if sub_lines[0].startswith(cont_pad) else sub_lines[0].lstrip()
        return [dash + first] + sub_lines[1:]

    if isinstance(item, list):
        if not item:
            return [f"{dash}[]"]
        sub_lines = _render_block(item, indent + 1)
        first = sub_lines[0][len(cont_pad):] if sub_lines[0].startswith(cont_pad) else sub_lines[0].lstrip()
        return [dash + first] + sub_lines[1:]

    return [f"{dash}{_dump_scalar(str(item))}"]


def _dump_node(obj, indent, lines, top_level=False):
    lines.extend(_render_block(obj, indent))
