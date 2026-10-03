import json

rubric_filepath = "rubric.json"

with open(rubric_filepath, 'r', encoding='utf-8') as f:
    rubric_dict = json.load(f)

items = rubric_dict["rubric_items"]

for rubric_item in items:
    for k, v in rubric_item.items():
        print("key", k)
        print("value",v)

