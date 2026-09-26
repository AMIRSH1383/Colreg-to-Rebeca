import json
import argparse
import sys
import os

class RuleStatusClassifier:
    def classify(self, path):
        if not path or not os.path.exists(path):
            return {"status": "not-formalized", "defects": [], "evidence": "file not found", "clause_count": 0}
        content = open(path).read()
        clause_count = content.count("clause[")
        if "TODO" in content: return {"status": "todo-placeholder", "defects": [], "evidence": "found TODO", "clause_count": clause_count}
        if "clause" in content and "condition" in content and "assure" in content: return {"status": "formalized", "defects": [], "evidence": "all fields present", "clause_count": clause_count}
        if "condition" in content and "assure" in content: return {"status": "incomplete", "defects": ["missing exclude"], "evidence": "partial", "clause_count": clause_count}
        if "condition" in content: return {"status": "incorrect", "defects": ["too minimal"], "evidence": "too minimal", "clause_count": clause_count}
        return {"status": "not-formalized", "defects": [], "evidence": "empty", "clause_count": clause_count}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--legata-path")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()
    classifier = RuleStatusClassifier()
    print(json.dumps(classifier.classify(args.legata_input)))
