import json

schema_path = r"G:\University\Research\Research projects\COLREG Project\02-Codes\New work\schemas\colreg_extraction_schema.json"
data_path = r"G:\University\Research\Research projects\COLREG Project\02-Codes\New work\output\Rule22\colreg_extraction.json"

with open(schema_path, "r", encoding="utf-8") as f:
    schema = json.load(f)

with open(data_path, "r", encoding="utf-8") as f:
    data = json.load(f)

def validate_schema(data, schema):
    assert isinstance(data, dict), "Root must be object"
    for req in schema["required"]:
        assert req in data, f"Missing required field: {req}"
    
    for k, v in data.items():
        assert k in schema["properties"], f"Unexpected property: {k}"
        prop_schema = schema["properties"][k]
        t = prop_schema["type"]
        if t == "string":
            assert isinstance(v, str), f"{k} must be string"
        elif t == "array":
            assert isinstance(v, list), f"{k} must be list"
            item_schema = prop_schema["items"]
            for item in v:
                if item_schema.get("type") == "string":
                    assert isinstance(item, str), f"Item in {k} must be string"
                elif item_schema.get("type") == "object":
                    assert isinstance(item, dict), f"Item in {k} must be object"
                    if item_schema.get("additionalProperties") is False:
                        for ik in item:
                            assert ik in item_schema["properties"], f"Unexpected property {ik} in {k}"
                    for irq in item_schema["required"]:
                        assert irq in item, f"Missing required field {irq} in {k}"
                    for ik, iv in item.items():
                        iprop = item_schema["properties"][ik]
                        ptypes = iprop["type"]
                        if isinstance(ptypes, str):
                            ptypes = [ptypes]
                        matched = False
                        for pt in ptypes:
                            if pt == "string" and isinstance(iv, str):
                                matched = True
                            elif pt == "number" and (isinstance(iv, (int, float)) and not isinstance(iv, bool)):
                                matched = True
                            elif pt == "boolean" and isinstance(iv, bool):
                                matched = True
                            elif pt == "null" and iv is None:
                                matched = True
                            elif pt == "array" and isinstance(iv, list):
                                matched = True
                                for sub_item in iv:
                                    if "items" in iprop:
                                        sub_item_type = iprop["items"]["type"]
                                        if sub_item_type == "string":
                                            assert isinstance(sub_item, str)
                        assert matched, f"Type mismatch for {ik} in {k}: {iv}"
                        if "enum" in iprop:
                            assert iv in iprop["enum"], f"Value {iv} not in enum for {ik} in {k}"

validate_schema(data, schema)
print("Validation passed successfully!")
