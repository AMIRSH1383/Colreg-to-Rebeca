#!/usr/bin/env python3
"""Read-only, dependency-free structural extractor for Rebeca source files.

The result is a compact binding-oriented JSON snapshot, NOT a full Rebeca AST.
No LLM, external handbook, model evaluation, or code modification is involved.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ID = r"[A-Za-z_]\w*"
DECL = re.compile(rf"^\s*(?P<type>{ID})(?P<dims>(?:\s*\[[^\]]*\])*)\s+(?P<names>.+?)\s*$", re.S)
HEADER = re.compile(rf"^\s*(?:@priority\s*\(\s*(?P<priority>\d+)\s*\)\s*)?(?P<msgsrv>msgsrv\s+)?(?:(?P<rtype>{ID}(?:\s*\[[^\]]+\])*)\s+)?(?P<name>{ID})\s*\((?P<params>.*?)\)\s*$", re.S)
MAIN_INSTANCE = re.compile(
    rf"^\s*(?:@priority\s*\(\s*(?P<priority>\d+)\s*\)\s*)?"
    rf"(?P<class>{ID})\s+(?P<name>{ID})\s*"
    r"\((?P<known>.*)\)\s*:\s*\((?P<args>.*)\)\s*$", re.S
)
ASSIGN = re.compile(rf"(?<![\w.])(?P<name>{ID})\s*(?P<indices>(?:\[[^\]]+\]\s*)*)(?P<op>\+\+|--|\+=|-=|\*=|/=|%=|(?<![=<>!])=(?!=))")


class ExtractionError(ValueError):
    pass


def mask_source(text: str) -> tuple[str, str]:
    """Return (comments removed, comments and strings removed), with offsets intact."""
    no_comments = list(text)
    structure = list(text)
    i, n = 0, len(text)
    while i < n:
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                if text[k] != "\n":
                    no_comments[k] = structure[k] = " "
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise ExtractionError("Unterminated block comment")
            j += 2
            for k in range(i, j):
                if text[k] != "\n":
                    no_comments[k] = structure[k] = " "
            i = j
        elif text[i] in ('"', "'"):
            quote = text[i]
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                elif text[j] == quote:
                    j += 1
                    break
                else:
                    j += 1
            else:
                raise ExtractionError("Unterminated string literal")
            for k in range(i, min(j, n)):
                if text[k] != "\n":
                    structure[k] = " "
            i = j
        else:
            i += 1
    return "".join(no_comments), "".join(structure)


def matching(s: str, pos: int, opening: str, closing: str) -> int:
    if pos >= len(s) or s[pos] != opening:
        raise ExtractionError(f"Expected '{opening}' at offset {pos}")
    depth = 0
    for i in range(pos, len(s)):
        if s[i] == opening:
            depth += 1
        elif s[i] == closing:
            depth -= 1
            if depth == 0:
                return i
    raise ExtractionError(f"Unmatched '{opening}' at offset {pos}")


def split_top_level(s: str, delim: str = ",") -> list[str]:
    """Split commas/semicolons while respecting nested parentheses and arrays."""
    out: list[str] = []
    start = 0
    par = br = curl = 0
    in_string = None
    i = 0
    while i < len(s):
        c = s[i]
        if in_string:
            if c == "\\":
                i += 2
                continue
            if c == in_string:
                in_string = None
        elif c in ('"', "'"):
            in_string = c
        elif c == "(":
            par += 1
        elif c == ")":
            par -= 1
        elif c == "[":
            br += 1
        elif c == "]":
            br -= 1
        elif c == "{":
            curl += 1
        elif c == "}":
            curl -= 1
        elif c == delim and par == br == curl == 0:
            if s[start:i].strip():
                out.append(s[start:i].strip())
            start = i + 1
        i += 1
    if s[start:].strip():
        out.append(s[start:].strip())
    return out


def at_line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def simplified(s: str) -> str:
    return " ".join(s.split())


def parse_declarations(s: str, *, line: int | None = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if s.strip() and not s.rstrip().endswith(";"):
        raise ExtractionError("Unterminated declaration")
    cursor = 0
    for part in split_top_level(s, ";"):
        part_offset = s.find(part, cursor)
        cursor = part_offset + len(part)
        part_line = line + s.count("\n", 0, part_offset) if line is not None else None
        m = DECL.fullmatch(part)
        if not m:
            raise ExtractionError(f"Unrecognized declaration: {simplified(part)[:110]}")
        type_name = m.group("type")
        array_dimensions = re.findall(r"\[\s*([^\]]*)\s*\]", m.group("dims"))
        for item in split_top_level(m.group("names")):
            x = re.fullmatch(rf"\s*({ID})\s*(?:=\s*(.*))?", item, re.S)
            if not x:
                raise ExtractionError(f"Unrecognized declared name: {simplified(item)[:110]}")
            obj: dict[str, Any] = {"name": x.group(1), "type": type_name, "array_dimensions": [q.strip() for q in array_dimensions]}
            if x.group(2) is not None:
                obj["declaration_initializer"] = simplified(x.group(2))
            if part_line is not None:
                obj["line"] = part_line
            result.append(obj)
    return result


def parse_parameters(s: str) -> list[dict[str, Any]]:
    if not s.strip():
        return []
    result = []
    for p in split_top_level(s):
        items = parse_declarations(p + ";")
        if len(items) != 1:
            raise ExtractionError(f"Invalid parameter: {simplified(p)}")
        result.append(items[0])
    return result


def parse_literal(expr: str) -> Any:
    e = expr.strip()
    if e == "true":
        return True
    if e == "false":
        return False
    if re.fullmatch(r"[-+]?\d+", e):
        return int(e)
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\.\d+)(?:[eE][-+]?\d+)?", e):
        return float(e)
    return None


def evaluate_simple(expr: str, bindings: dict[str, str], env: dict[str, Any]) -> dict[str, Any]:
    """Resolve only direct identifiers and literals; never evaluate arbitrary code."""
    e = expr.strip()
    seen: set[str] = set()
    while re.fullmatch(ID, e) and e not in {"true", "false"}:
        if e in seen:
            break
        seen.add(e)
        if e in bindings:
            e = bindings[e].strip()
        elif e in env:
            e = str(env[e]["expression"]).strip()
        else:
            break
    val = parse_literal(e)
    if val is not None:
        return {"resolved": True, "value": val}
    return {"resolved": False, "expression": simplified(expr)}


def find_top_level_blocks(text: str, structure: str, begin: int, end: int) -> list[dict[str, Any]]:
    """Find direct children introduced by a { ... } block within an enclosing body."""
    blocks = []
    p = begin
    while p < end:
        match = re.search(r"[{}]", structure[p:end])
        if not match:
            break
        b = p + match.start()
        if structure[b] == "}":
            raise ExtractionError(f"Unexpected closing brace at line {at_line(text,b)}")
        close = matching(structure, b, "{", "}")
        if close >= end:
            raise ExtractionError("Nested block extends past parent")
        # The current header starts after the preceding direct-child closing brace.
        raw_header = text[p:b]
        header = raw_header.strip()
        header_start = p + len(raw_header) - len(raw_header.lstrip())
        blocks.append({"header": header, "begin": b, "end": close, "header_start": header_start})
        p = close + 1
    return blocks


def extract_writes(method_text: str, structure: str, declared: set[str], shadowed: set[str], offset: int, fulltext: str) -> list[dict[str, Any]]:
    """Syntactic state-variable writes; expressions may be conditional/within loops."""
    # Filter string and comment tokens, then skip shadowed local variables and parameters.
    by_name: dict[str, dict[str, Any]] = {}
    for m in ASSIGN.finditer(structure):
        name = m.group("name")
        if name not in declared or name in shadowed:
            continue
        d = by_name.setdefault(name, {"variable": name, "count": 0, "lines": [], "operators": []})
        d["count"] += 1
        line = at_line(fulltext, offset + m.start())
        if line not in d["lines"] and len(d["lines"]) < 5:
            d["lines"].append(line)
        if m.group("op") not in d["operators"]:
            d["operators"].append(m.group("op"))
    return list(by_name.values())


def collect_assertions(fragment: str, structure: str, offset: int, fulltext: str) -> list[dict[str, Any]]:
    results = []
    for m in re.finditer(r"\bassertion\s*\(", structure):
        op = structure.find("(", m.start(), m.end())
        ed = matching(structure, op, "(", ")")
        args = split_top_level(fragment[op + 1:ed])
        results.append({"line": at_line(fulltext, offset + m.start()), "condition": simplified(args[0]) if args else "", "message": (args[1].strip().strip('"') if len(args) > 1 else None)})
    return results


def parse_method(block: dict[str, Any], source: str, structure: str, class_name: str, vars_set: set[str]) -> dict[str, Any]:
    # The header is taken from comment-free source, not raw text.
    h = HEADER.fullmatch(simplified(block["header"]))
    if not h:
        raise ExtractionError(f"Unrecognized class member near line {at_line(source,block['header_start'])}: {simplified(block['header'])[:100]}")
    name = h.group("name")
    kind = "message_server" if h.group("msgsrv") else "constructor" if name == class_name else "helper_method"
    params = parse_parameters(h.group("params"))
    body_start, body_end = block["begin"] + 1, block["end"]
    body = source[body_start:body_end]
    body_structure = structure[body_start:body_end]
    # Detect simple local variables; exclude variables shadowing the class state.
    local_decls = re.finditer(
        rf"\b(?:int|byte|double|boolean|float|long|short|char|String)\b"
        rf"(?:\s*\[[^\]]*\])*\s*({ID}\b[^;]*);", body_structure
    )
    shadowed = {p["name"] for p in params}
    for declaration in local_decls:
        for item in split_top_level(declaration.group(1)):
            local_name = re.match(ID, item.strip())
            if local_name:
                shadowed.add(local_name.group())
    writes = extract_writes(body, body_structure, vars_set, shadowed, body_start, source)
    out: dict[str, Any] = {"name": name, "kind": kind, "line": at_line(source, block["header_start"]), "parameters": params, "priority": int(h.group("priority")) if h.group("priority") is not None else None, "state_writes": writes}
    if h.group("rtype"):
        out["return_type"] = h.group("rtype").replace(" ", "")
    if kind == "constructor":
        # Record top-level assignments only, to avoid treating loop/branch writes as fixed initializations.
        inits: dict[str, dict[str, Any]] = {}
        depth = 0
        statement_start = 0
        for i, ch in enumerate(body_structure):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    statement_start = i + 1
            elif ch == ";" and depth == 0:
                st = body_structure[statement_start:i].strip()
                match = re.fullmatch(rf"({ID})\s*(=(?!=))\s*(.*)", st, re.S)
                if match and match.group(1) in vars_set and match.group(1) not in shadowed:
                    namevar = match.group(1)
                    # When a simple assignment is repeated, last unconditional assignment wins.
                    st_raw = body[statement_start:i].strip()
                    x = re.fullmatch(rf"{ID}\s*=\s*(.*)", st_raw, re.S)
                    expr = simplified(x.group(1)) if x else simplified(match.group(3))
                    raw_piece = body[statement_start:i]
                    statement_pos = body_start + statement_start + len(raw_piece) - len(raw_piece.lstrip())
                    inits[namevar] = {"expression": expr, "line": at_line(source, statement_pos), "offset": statement_pos - body_start}
                statement_start = i + 1
        # A later conditional/indexed/compound write invalidates an earlier
        # candidate. Do not represent it as a guaranteed constructor value.
        for write in ASSIGN.finditer(body_structure):
            candidate = inits.get(write.group("name"))
            if candidate and write.start() > candidate["offset"]:
                del inits[write.group("name")]
        for candidate in inits.values():
            del candidate["offset"]
        out["direct_initializations"] = inits
    asserts = collect_assertions(body, body_structure, body_start, source)
    if asserts:
        out["inline_assertions"] = asserts
    return out


def parse_model(text: str, input_path: str) -> dict[str, Any]:
    clean, structure = mask_source(text)
    env: dict[str, dict[str, Any]] = {}
    for m in re.finditer(rf"\benv\s+({ID})\s+({ID})\s*=\s*([^;]+);", structure):
        env[m.group(2)] = {"type": m.group(1), "expression": simplified(clean[m.start(3):m.end(3)]), "line": at_line(text, m.start())}

    classes: list[dict[str, Any]] = []
    # Top-level class matches; reject nested results using a top-level brace check below.
    cmatches = list(re.finditer(rf"\breactiveclass\s+({ID})\s*\(\s*([^)]*)\s*\)\s*\{{", structure))
    last_end = 0
    for cm in cmatches:
        if cm.start() < last_end:
            continue
        copen = structure.find("{", cm.start(), cm.end())
        cend = matching(structure, copen, "{", "}")
        last_end = cend + 1
        name = cm.group(1)
        class_data: dict[str, Any] = {
            "name": name,
            "queue_size_expression": cm.group(2).strip(),
            "line": at_line(text, cm.start()),
            "known_rebecs": [],
            "state_variables": [],
            "constructor": None,
            "message_servers": [],
            "helper_methods": [],
        }
        children = find_top_level_blocks(clean, structure, copen + 1, cend)
        for member in children:
            head = simplified(member["header"])
            if head in ("knownrebecs", "statevars"):
                decls = parse_declarations(clean[member["begin"] + 1:member["end"]], line=at_line(text, member["begin"] + 1))
                class_data["known_rebecs" if head == "knownrebecs" else "state_variables"] = decls
        state_set = {x["name"] for x in class_data["state_variables"]}
        for member in children:
            head = simplified(member["header"])
            if head in ("knownrebecs", "statevars"):
                continue
            method = parse_method(member, clean, structure, name, state_set)
            if method["kind"] == "constructor":
                if class_data["constructor"] is not None:
                    raise ExtractionError(f"Multiple constructors for {name} not supported")
                class_data["constructor"] = method
            elif method["kind"] == "message_server":
                class_data["message_servers"].append(method)
            else:
                compact_helper: dict[str, Any] = {
                    "name": method["name"], "line": method["line"],
                    "state_writes": sorted(x["variable"] for x in method["state_writes"]),
                }
                if "inline_assertions" in method:
                    compact_helper["inline_assertions"] = method["inline_assertions"]
                class_data["helper_methods"].append(compact_helper)
        classes.append(class_data)
    if not classes:
        raise ExtractionError("No reactiveclass declaration found")

    mains = list(re.finditer(r"\bmain\s*\{", structure))
    if len(mains) != 1:
        raise ExtractionError(f"Expected one main block, found {len(mains)}")
    main_start = structure.find("{", mains[0].start(), mains[0].end())
    main_end = matching(structure, main_start, "{", "}")
    classmap = {c["name"]: c for c in classes}
    instances: list[dict[str, Any]] = []
    # Split statements and preserve source offsets so that source-line anchors are correct.
    main_text = clean[main_start + 1:main_end]
    for stmt in split_top_level(main_text, ";"):
        m = MAIN_INSTANCE.fullmatch(simplified(stmt))
        if not m:
            raise ExtractionError(f"Unrecognized main declaration: {simplified(stmt)[:120]}")
        c = m.group("class")
        if c not in classmap:
            raise ExtractionError(f"Undefined reactive class '{c}' in main")
        constructor = classmap[c]["constructor"]
        params = constructor["parameters"] if constructor else []
        args = split_top_level(m.group("args"))
        if len(params) != len(args):
            raise ExtractionError(f"Constructor argument count mismatch for {m.group('name')}: {len(args)} versus {len(params)}")
        linked = split_top_level(m.group("known"))
        known_decls = classmap[c]["known_rebecs"]
        if len(known_decls) != len(linked):
            raise ExtractionError(f"Knownrebecs count mismatch for {m.group('name')}")
        known_map = {known_decls[i]["name"]: linked[i] for i in range(len(linked))}
        instance = {
            "name": m.group("name"), "class": c,
            "priority": int(m.group("priority")) if m.group("priority") is not None else None,
            "known_rebec_bindings": known_map,
            "constructor_arguments": {params[i]["name"]: args[i] for i in range(len(args))},
            "line": at_line(text, main_start + 1 + main_text.find(stmt)),
        }
        instances.append(instance)
    inst_names = {ins["name"] for ins in instances}
    for ins in instances:
        for alias, target in ins["known_rebec_bindings"].items():
            if target not in inst_names:
                raise ExtractionError(f"Unknown instance '{target}' bound to {ins['name']}.{alias}")

    for cl in classes:
        ctor = cl["constructor"]
        direct = ctor["direct_initializations"] if ctor else {}
        for var in cl["state_variables"]:
            if var["name"] in direct:
                iv = direct[var["name"]]
                var["constructor_initialization"] = {
                    "expression": iv["expression"], "line": iv["line"],
                    "per_instance": {ins["name"]: evaluate_simple(iv["expression"], ins["constructor_arguments"], env) for ins in instances if ins["class"] == cl["name"]},
                }
        if ctor:
            del ctor["direct_initializations"]
        # Drop redundant per-method empty state write arrays? Keep consistent for consumers.

    counts = {"reactive_classes": len(classes), "instances": len(instances), "state_variables": sum(len(x["state_variables"]) for x in classes), "message_servers": sum(len(x["message_servers"]) for x in classes), "helper_methods": sum(len(x["helper_methods"]) for x in classes), "env_constants": len(env)}
    warnings = [
        "State writes are a syntactic index, not a control-flow or data-flow analysis. Local shadowing is conservatively applied across each entire method.",
        "Only direct scalar constructor assignments are considered candidate initial values; nontrivial expressions and indexed/conditional initializations remain unresolved.",
    ]
    return {
        "schema_version": "1.0",
        "source": {"path": input_path, "line_count": len(text.splitlines())},
        "environment_constants": [{"name": k, **v} for k, v in env.items()],
        "reactive_classes": classes,
        "instances": instances,
        "summary": counts,
        "limitations": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Extract a compact structural JSON snapshot from a Rebeca model (no LLM or dependencies).")
    ap.add_argument("--input", required=True, type=Path, help="Path to the source .rebeca file")
    ap.add_argument("--output", required=True, type=Path, help="JSON output path")
    args = ap.parse_args(argv)
    try:
        if not args.input.is_file():
            raise ExtractionError(f"Input file does not exist: {args.input}")
        text = args.input.read_text(encoding="utf-8-sig")
        data = parse_model(text, args.input.as_posix())
        if (args.output.resolve() == args.input.resolve()
                or (args.output.exists() and args.output.samefile(args.input))):
            raise ExtractionError("Output would overwrite the source model")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "output": str(args.output), **data["summary"]}))
        return 0
    except (OSError, ExtractionError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
