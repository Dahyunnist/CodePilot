"""Small strict validator for run manifest v1; rejects credential-bearing fields."""
import json,re
SENSITIVE=re.compile(r"api[_-]?key|token|secret|password|authorization|credential",re.I)
REQUIRED={"schema_version","run_id","git_sha","dataset_id","dataset_sha256","split","model_id","prompt_sha256","tool_schema_sha256","scorer_sha256","runtime","budget","gold_source","cost_usd","started_at","finished_at","status"}
SHA=re.compile(r"^[a-f0-9]{64}$")
def validate(data):
    if not isinstance(data,dict): return ["root:not_object"]
    errors=[]
    for key in REQUIRED-data.keys(): errors.append(f"missing:{key}")
    for key in data:
        if SENSITIVE.search(key): errors.append(f"sensitive_field:{key}")
    if data.get("schema_version") != 1: errors.append("invalid:schema_version")
    for key in ("git_sha","dataset_sha256","prompt_sha256","tool_schema_sha256","scorer_sha256"):
        if key in data and (not isinstance(data[key],str) or not SHA.fullmatch(data[key])): errors.append(f"invalid:{key}")
    if data.get("status") not in {"fixture","running","success","failed","blocked","cancelled"}: errors.append("invalid:status")
    budget=data.get("budget")
    if not isinstance(budget,dict) or not {"max_cost_usd","max_tokens"}<=budget.keys(): errors.append("invalid:budget")
    return errors
def load(path): return validate(json.loads(open(path,encoding="utf-8-sig").read()))
