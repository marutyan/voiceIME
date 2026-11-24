import json, os
model = haas_asr.load_model("third-intelligence/Haas-ja-v1.0", dtype=torch.float32)
out = model.transcribe(audio, batch_size=1)
results["float32"] = {os.path.basename(f): h.text.strip() for f, h in zip(files, out)}
json.dump(results, open("/content/haas_official.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(results["float32"], ensure_ascii=False, indent=1))
