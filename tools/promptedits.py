# -*- coding: utf-8 -*-
"""Edits of prompts.txt: save a prompt, attach references, create a prompt block."""
import re
from kitcore import Conflict
from story import prompt_ranges


def upsert_prompt(lines, id_, old, new):
    """Like replace_prompt, but a picture that has no block yet gets a new one at the end (old must then be empty)."""
    if id_ in prompt_ranges(lines):
        return replace_prompt(lines, id_, old, new)
    if old.strip():
        raise Conflict("این پرامپت بیرون از مرورگر پاک شده؛ صفحه را دوباره بارگذاری کن.")
    body = new.replace("\r\n", "\n").strip()
    if not body:
        return False
    while lines and not lines[-1].strip():
        lines.pop()
    lines += ["", f"=== {id_} ===", *body.split("\n"), ""]
    return True


def replace_prompt(lines, id_, old, new):
    r = prompt_ranges(lines)
    if id_ not in r:
        raise ValueError("prompt not found")
    s, e = r[id_]
    if "\n".join(lines[s + 1:e]).strip() != old.replace("\r\n", "\n").strip():
        raise Conflict("این پرامپت بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
    body = new.replace("\r\n", "\n").strip().split("\n")
    lines[s + 1:e] = body + [""]
    return "\n".join(body).strip() != old.replace("\r\n", "\n").strip()


REFS_LINE = re.compile(r"\[REFS TO ATTACH:[^\]]*\]")


def set_prompt_refs(lines, id_, names):
    """Rewrite only the «[REFS TO ATTACH: A| B]» line at the top of one prompt (added when missing, removed when empty).
    A prompt that does not exist yet is created. Returns True when something changed."""
    line = "[REFS TO ATTACH: " + "| ".join(names) + "]" if names else ""
    r = prompt_ranges(lines)
    if id_ not in r:
        if line:
            while lines and not lines[-1].strip():
                lines.pop()
            lines += ([""] if lines else []) + [f"=== {id_} ===", line, ""]
        return bool(line)
    s, e = r[id_]
    i = next((k for k in range(s + 1, e) if lines[k].strip()), None)
    if i is not None and REFS_LINE.fullmatch(lines[i].strip()):
        if lines[i].strip() == line:
            return False
        lines[i:i + 1] = [line] if line else []
    elif line:
        lines[s + 1:s + 1] = [line]
    else:
        return False
    return True
