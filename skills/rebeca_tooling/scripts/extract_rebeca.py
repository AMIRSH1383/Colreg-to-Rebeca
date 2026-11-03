"""Extract a structural inventory, without interpreting Rebeca behavior.

Supported: reactiveclass, knownrebecs, statevars, constructors, message servers,
environment declarations and main instances. Expressions remain source text.
This is a bounded structural reader, not a Rebeca compiler or type checker.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


IDENT = r"[A-Za-z_]\w*"


def mask(source):
    """Hide comments and strings while preserving offsets and line numbers."""
    pattern = r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"'
    return re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m[0]), source)


def blocks(text):
    """Yield top-level brace blocks and reject unbalanced input."""
    depth, start, prefix = 0, 0, 0
    for i, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise ValueError("Unmatched closing brace")
            if depth == 0:
                yield prefix, start, i
                prefix = i + 1
    if depth:
        raise ValueError("Unclosed brace")


def declarations(text):
    result = []
    for declaration in text.split(";"):
        if not declaration.strip():
            continue
        match = re.fullmatch(r"\s*(" + IDENT + r"(?:\s*\[[^\]]+\])*)\s+(.+?)\s*", declaration, re.S)
        if not match:
            raise ValueError("Unsupported declaration: " + declaration.strip())
        for name in match[2].split(","):
            if not re.fullmatch(IDENT, name.strip()):
                raise ValueError("Unsupported variable declaration: " + name.strip())
            result.append({"name": name.strip(), "type": re.sub(r"\s+", "", match[1])})
    return result


def extract(source, source_name="<memory>"):
    clean = mask(source)
    classes, instances, warnings = [], [], []
    for prefix, opening, closing in blocks(clean):
        header = clean[prefix:opening]
        found = re.search(r"\breactiveclass\s+(" + IDENT + r")\s*\(([^()]*)\)\s*$", header)
        if found:
            actor = {"name": found[1], "queue_capacity": found[2].strip(),
                     "line": source.count("\n", 0, prefix + found.start()) + 1,
                     "state_variables": [], "known_rebecs": [], "constructors": [],
                     "message_servers": [], "other_members": [], "source_context": []}
            body = clean[opening + 1:closing]
            for member_start, left, right in blocks(body):
                signature = body[member_start:left].strip()
                signature = re.sub(r"^@priority\s*\([^()]*\)\s*", "", signature)
                content = body[left + 1:right]
                absolute_start = opening + 1 + member_start
                absolute_end = opening + 1 + right + 1
                actor['source_context'].append({
                    'member': signature,
                    'line_start': source.count('\n', 0, absolute_start) + 1,
                    'line_end': source.count('\n', 0, absolute_end) + 1,
                    'source': source[absolute_start:absolute_end],
                    'interpretation': 'Source text only; local names may shadow state fields.'})
                if signature in ("statevars", "knownrebecs"):
                    key = "state_variables" if signature == "statevars" else "known_rebecs"
                    actor[key].extend(declarations(content))
                    continue
                method = re.fullmatch(r"(?:(msgsrv)\s+)?(" + IDENT + r")\s*\((.*?)\)", signature, re.S)
                if method and (method[1] or method[2] == actor["name"]):
                    entry = {"name": method[2], "parameters": method[3].strip(),
                             "line": source.count("\n", 0, opening + 1 + left) + 1}
                    if method[1]:
                        actor["message_servers"].append(entry)
                    else:
                        # Preserve assignments as expressions; branches/loops are not evaluated.
                        names = {v["name"] for v in actor["state_variables"]}
                        entry["assignments"] = []
                        for assignment in re.finditer(r"\b(" + IDENT + r")\s*=(?!=)([^;]+);", content):
                            if assignment[1] in names:
                                offset = opening + 1 + left + 1
                                entry["assignments"].append({"variable": assignment[1],
                                    "expression": source[offset + assignment.start(2):offset + assignment.end(2)].strip()})
                        actor["constructors"].append(entry)
                else:
                    actor["other_members"].append(signature)
                    warnings.append("Uninterpreted member in " + actor["name"] + ": " + signature)
            classes.append(actor)
        elif re.search(r"\bmain\s*$", header):
            for statement in clean[opening + 1:closing].split(";"):
                if not statement.strip():
                    continue
                match = re.fullmatch(r"\s*(?:@priority\s*\([^()]*\)\s*)?(" + IDENT + r")\s+(" + IDENT + r")\s*\(([^()]*)\)\s*:\s*\(([^()]*)\)\s*", statement, re.S)
                if not match:
                    raise ValueError("Unsupported main instance: " + statement.strip())
                instances.append({"class": match[1], "name": match[2],
                                  "known_rebec_arguments": match[3].strip(),
                                  "constructor_arguments": match[4].strip()})
        else:
            raise ValueError("Unsupported top-level block: " + header.strip())
    if not classes:
        raise ValueError("No reactive classes found")
    class_names = [a['name'] for a in classes]
    if len(set(class_names)) != len(class_names):
        raise ValueError('Duplicate reactive class name')
    instance_names = [i['name'] for i in instances]
    if len(set(instance_names)) != len(instance_names):
        raise ValueError('Duplicate actor instance name')
    if any(i['class'] not in class_names for i in instances):
        raise ValueError('Actor instance refers to an undeclared class')
    return {"schema_version": 1, "status": "ok", "source": source_name,
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "environment": [{"type": m[1], "name": m[2], "expression": m[3].strip()}
                for m in re.finditer(r"\benv\s+(" + IDENT + r")\s+(" + IDENT + r")\s*=\s*([^;]+);", clean)],
            "reactive_classes": classes, "instances": instances,
            "warnings": warnings,
            "limitations": ["Expressions are not evaluated; constructor assignments are not proven initial values.",
                            "Method behavior, units, reachability and regulatory meaning are not inferred.",
                            "This inventory does not establish Rebeca syntax or semantic validity."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.model.resolve() == args.output.resolve():
        parser.error("Output must differ from input")
    try:
        result = extract(args.model.read_text(encoding="utf-8-sig"), str(args.model))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
